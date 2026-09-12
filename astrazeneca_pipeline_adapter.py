"""Read-only AstraZeneca official pipeline source adapter.

The adapter parses AstraZeneca's public pipeline page into deterministic
therapy-area / phase / program rows. It never writes to Airtable or any master
intelligence table. Full-row output is protected by the existing adapter key;
a count-only probe is public so deployments can be validated without exposing
arbitrary-fetch capability.
"""

import hashlib
import re
from collections import Counter
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional

import httpx
from fastapi import Header, HTTPException, Query
from pydantic import BaseModel, Field

from main import _auth, app
from html_fetch_extension import _assert_public_http_url


AZ_PIPELINE_VERSION = "V1.0.0 ASTRAZENECA OFFICIAL PIPELINE READ ONLY"
AZ_PIPELINE_URL = "https://www.astrazeneca.com/our-therapy-areas/pipeline.html"
AZ_SOURCE_FAMILY = "AstraZeneca Official Pipeline"
AZ_COMPANY = "AstraZeneca"

AREA_NAMES = {
    "oncology": "Oncology",
    "cardiovascular, renal and metabolism": "Cardiovascular, Renal and Metabolism",
    "respiratory & immunology": "Respiratory & Immunology",
    "respiratory and immunology": "Respiratory & Immunology",
    "rare disease": "Rare Disease",
    "infectious disease": "Infectious Disease",
    "other": "Other",
}

PHASE_MAP = {
    "phase i": "Phase 1",
    "phase 1": "Phase 1",
    "phase ii": "Phase 2",
    "phase 2": "Phase 2",
    "phase iii": "Phase 3",
    "phase 3": "Phase 3",
    "lcm projects": "LCM",
    "lcm project": "LCM",
    "under review": "Registration",
    "registration": "Registration",
}

CODE_RE = re.compile(
    r"\b(?:AZD\d+|ALXN\d+|MEDI[- ]?\d+|IPH\d+|JAB-[A-Za-z0-9]+|NT-\d+|FPI-\d+|PT\d+|ZS-\d+)\b",
    flags=re.I,
)

STUDY_TOKEN_RE = re.compile(
    r"^(?:[A-Z][A-Za-z0-9]*[-]?[A-Za-z]*\d+[A-Za-z0-9-]*|"
    r"(?:ARTEMIDE|SERENA|CAMBRIA|DESTINY|TROPION|PACIFIC|CAPItello|EvoPAR|"
    r"SOUNDTRACK|CLARITY|eVOLVE|BaxHTN|BaxPA|CLEAR|TULIP|NAVIGATOR|OBERON|"
    r"TITANIA|PROSPERO|MIRANDA|CALYPSO|PREVAIL|CARES|DepleTTR|AUTUMN|CONCORD|"
    r"TRANSCEND|DURGA|TREVI|VECTRA|ESCALADE|AMPLIFY|ECHO|KALOS|LOGOS|THARROS|"
    r"DAISY|IRIS|JASMINE|LAVENDER|CROSSING|EMBARK|JOURNEY|WAYPOINT|AWAKE)"
    r"(?:[-_][A-Za-z0-9]+|\d+)*)$",
    flags=re.I,
)

TWO_WORD_DRUG_SUFFIX_RE = re.compile(
    r"(?:mab|zumab|limab|imab|tecan|vedotin|paratide|guraxetan|samrotecan|"
    r"estrant|stat|renone|glipron|mirsen|limab|cept)$",
    flags=re.I,
)


def _clean(value: Any) -> str:
    if value is None:
        return ""
    value = str(value).replace("\u00a0", " ").replace("\u2013", "-").replace("\u2014", "-")
    return re.sub(r"\s+", " ", value).strip()


def _norm(value: Any) -> str:
    return _clean(value).lower()


def _source_record_id(area: str, phase: str, text: str) -> str:
    raw = f"{area}|{phase}|{text}".encode("utf-8")
    return "AZPIPE-" + hashlib.sha1(raw).hexdigest()[:16].upper()


def _area_from_heading(text: str) -> tuple[Optional[str], Optional[str], bool]:
    cleaned = _clean(text)
    if not cleaned:
        return None, None, False
    if _norm(cleaned) == "removed since last quarter":
        return "Removed since last quarter", None, True

    match = re.match(r"(.+?)\s*\(as of\s+([^)]+)\)\s*$", cleaned, flags=re.I)
    if match:
        raw_area, as_of = _clean(match.group(1)), _clean(match.group(2))
    else:
        raw_area, as_of = cleaned, None

    canonical = AREA_NAMES.get(_norm(raw_area))
    return canonical, as_of, False


def _phase_from_heading(text: str) -> Optional[str]:
    return PHASE_MAP.get(_norm(text))


def _looks_like_pipeline_item(text: str) -> bool:
    t = _clean(text)
    if not t or len(t) < 4:
        return False
    low = _norm(t)
    if low in {"back to top", "back to top↑"}:
        return False
    if low.startswith("jump to"):
        return False
    return True


class _PipelineHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._heading_tag: Optional[str] = None
        self._heading_buf: List[str] = []
        self._li_depth = 0
        self._li_buf: List[str] = []
        self.current_area: Optional[str] = None
        self.current_as_of: Optional[str] = None
        self.current_phase: Optional[str] = None
        self.in_removed = False
        self.rows: List[Dict[str, Any]] = []

    def handle_starttag(self, tag: str, attrs: List[tuple[str, Optional[str]]]) -> None:
        tag = tag.lower()
        if tag in {"h2", "h3"}:
            self._heading_tag = tag
            self._heading_buf = []
        if tag == "li":
            self._li_depth += 1
            if self._li_depth == 1:
                self._li_buf = []

    def handle_data(self, data: str) -> None:
        if self._heading_tag:
            self._heading_buf.append(data)
        if self._li_depth > 0:
            self._li_buf.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self._heading_tag == tag:
            text = _clean(" ".join(self._heading_buf))
            if tag == "h2":
                area, as_of, removed = _area_from_heading(text)
                if area:
                    self.current_area = area
                    self.current_as_of = as_of
                    self.current_phase = None
                    self.in_removed = removed
            elif tag == "h3":
                phase = _phase_from_heading(text)
                if phase:
                    self.current_phase = phase
            self._heading_tag = None
            self._heading_buf = []

        if tag == "li" and self._li_depth > 0:
            if self._li_depth == 1:
                text = _clean(" ".join(self._li_buf))
                if self.current_area and _looks_like_pipeline_item(text):
                    if self.in_removed:
                        self.rows.append({
                            "therapyArea": self.current_area,
                            "sourceAsOf": self.current_as_of,
                            "phase": "Removed",
                            "programText": text,
                            "removedSinceLastQuarter": True,
                        })
                    elif self.current_phase:
                        self.rows.append({
                            "therapyArea": self.current_area,
                            "sourceAsOf": self.current_as_of,
                            "phase": self.current_phase,
                            "programText": text,
                            "removedSinceLastQuarter": False,
                        })
                self._li_buf = []
            self._li_depth -= 1


def _split_program_text(text: str) -> Dict[str, Optional[str]]:
    text = _clean(text)
    result: Dict[str, Optional[str]] = {
        "asset": None,
        "molecule": None,
        "developmentCode": None,
        "brand": None,
        "indication": None,
        "parseStatus": "REVIEW",
        "parseNotes": None,
    }
    if not text:
        result["parseNotes"] = "Blank program text"
        return result

    code_match = CODE_RE.search(text)
    if code_match:
        result["developmentCode"] = _clean(code_match.group(0))

    # Development code is the displayed asset.
    if code_match and code_match.start() == 0:
        result["asset"] = _clean(code_match.group(0))
        rest = _clean(text[code_match.end():])
        result["indication"] = rest or None
        result["parseStatus"] = "PASS" if rest else "REVIEW"
        result["parseNotes"] = "Leading development-code identity"
        return result

    # Named molecule followed by a development code in parentheses.
    paren_code = re.match(r"^(.+?)\s*\(([^)]+)\)\s+(.+)$", text)
    if paren_code and CODE_RE.fullmatch(_clean(paren_code.group(2))):
        named = _clean(paren_code.group(1))
        result["asset"] = named
        result["molecule"] = named
        result["developmentCode"] = _clean(paren_code.group(2))
        result["indication"] = _clean(paren_code.group(3))
        result["parseStatus"] = "PASS"
        result["parseNotes"] = "Named molecule with parenthetical development code"
        return result

    # Brand / pipeline name with molecule in parentheses.
    brand_molecule = re.match(r"^([^()+/]+?)\s*\(([^)]+)\)\s+(.+)$", text)
    if brand_molecule:
        brand = _clean(brand_molecule.group(1))
        molecule = _clean(brand_molecule.group(2))
        result["asset"] = brand
        result["brand"] = brand
        result["molecule"] = molecule
        result["indication"] = _clean(brand_molecule.group(3))
        result["parseStatus"] = "PASS"
        result["parseNotes"] = "Brand/pipeline name with parenthetical molecule"
        return result

    tokens = text.split()
    if not tokens:
        result["parseNotes"] = "No tokens"
        return result

    take = 1
    if len(tokens) >= 2:
        first, second = tokens[0], tokens[1]
        if (
            first[:1].islower()
            and second[:1].islower()
            and TWO_WORD_DRUG_SUFFIX_RE.search(second)
            and not STUDY_TOKEN_RE.match(second)
        ):
            take = 2

    asset = _clean(" ".join(tokens[:take]))
    rest = _clean(" ".join(tokens[take:]))
    result["asset"] = asset or None
    if asset and asset[:1].isupper() and not CODE_RE.fullmatch(asset):
        result["brand"] = asset
    elif asset:
        result["molecule"] = asset

    # Study/program token immediately after the asset is kept in source-facing
    # indication text. Comparator V1.2 treats it as qualifier evidence and does
    # not rely on fuzzy matching.
    result["indication"] = rest or None
    result["parseStatus"] = "PASS" if asset and rest else "REVIEW"
    result["parseNotes"] = "Conservative leading-identity parse"
    return result


class AZPipelineRow(BaseModel):
    company: str = AZ_COMPANY
    sourceFamily: str = AZ_SOURCE_FAMILY
    sourceRecordId: str
    sourceUrl: str = AZ_PIPELINE_URL
    sourceAsOf: Optional[str] = None
    therapyArea: str
    phase: str
    programText: str
    removedSinceLastQuarter: bool = False
    commercialInScope: bool
    importantLabelExpansion: bool = False
    asset: Optional[str] = None
    molecule: Optional[str] = None
    developmentCode: Optional[str] = None
    brand: Optional[str] = None
    indication: Optional[str] = None
    parseStatus: str
    parseNotes: Optional[str] = None


class AZPipelineResponse(BaseModel):
    version: str
    readOnly: bool
    sourceUrl: str
    sourceAsOfValues: List[str]
    totalParsedRows: int
    returnedRows: int
    summaryByPhase: Dict[str, int]
    summaryByTherapyArea: Dict[str, int]
    parseStatusSummary: Dict[str, int]
    rows: List[AZPipelineRow] = Field(default_factory=list)


async def _fetch_source_html() -> str:
    await _assert_public_http_url(AZ_PIPELINE_URL)
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; PharmaIntelligenceAdapter/1.0)",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-GB,en;q=0.9",
    }
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(35.0, connect=12.0), headers=headers, follow_redirects=True) as client:
            response = await client.get(AZ_PIPELINE_URL)
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="AstraZeneca pipeline fetch timed out") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"AstraZeneca pipeline fetch failed: {exc}") from exc

    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"AstraZeneca pipeline returned HTTP {response.status_code}")
    if len(response.content) > 5_000_000:
        raise HTTPException(status_code=413, detail="AstraZeneca pipeline HTML exceeds adapter size limit")
    return response.text


def parse_pipeline_html(raw_html: str) -> List[AZPipelineRow]:
    parser = _PipelineHTMLParser()
    parser.feed(raw_html or "")
    parser.close()

    out: List[AZPipelineRow] = []
    seen = set()
    for raw in parser.rows:
        phase = raw["phase"]
        text = raw["programText"]
        key = (raw["therapyArea"], phase, text)
        if key in seen:
            continue
        seen.add(key)
        parsed = _split_program_text(text)
        commercial = phase in {"Phase 2", "Phase 3", "Registration", "LCM"}
        out.append(AZPipelineRow(
            sourceRecordId=_source_record_id(raw["therapyArea"], phase, text),
            sourceAsOf=raw.get("sourceAsOf"),
            therapyArea=raw["therapyArea"],
            phase=phase,
            programText=text,
            removedSinceLastQuarter=bool(raw.get("removedSinceLastQuarter")),
            commercialInScope=commercial and not bool(raw.get("removedSinceLastQuarter")),
            importantLabelExpansion=(phase == "LCM"),
            asset=parsed["asset"],
            molecule=parsed["molecule"],
            developmentCode=parsed["developmentCode"],
            brand=parsed["brand"],
            indication=parsed["indication"],
            parseStatus=str(parsed["parseStatus"]),
            parseNotes=parsed["parseNotes"],
        ))
    return out


def _summarize(rows: List[AZPipelineRow]) -> Dict[str, Any]:
    as_of = sorted({r.sourceAsOf for r in rows if r.sourceAsOf})
    return {
        "sourceAsOfValues": as_of,
        "summaryByPhase": dict(sorted(Counter(r.phase for r in rows).items())),
        "summaryByTherapyArea": dict(sorted(Counter(r.therapyArea for r in rows).items())),
        "parseStatusSummary": dict(sorted(Counter(r.parseStatus for r in rows).items())),
    }


def _self_test() -> Dict[str, Any]:
    fixture = """
    <h2>Oncology (as of 27 July 2026)</h2>
    <h3>Phase I</h3><ul><li>AZD0240 solid tumours</li></ul>
    <h3>Phase II</h3><ul><li>AZD0120 multiple myeloma</li><li>Etcamah (camizestrant) HR+ HER2- breast cancer</li></ul>
    <h3>Phase III</h3><ul><li>zadavotide guraxetan (AZD2265) VECTRA-01 prostate cancer (mCRPC)</li></ul>
    <h3>LCM Projects</h3><ul><li>Tagrisso ADAURA2 EGFRm NSCLC stage Ia2-Ia3 following complete tumour resection</li></ul>
    <h2>Removed since last quarter</h2><ul><li>AZD2068 solid tumours</li></ul>
    """
    rows = parse_pipeline_html(fixture)
    by_text = {r.programText: r for r in rows}
    checks = {
        "phase1_parsed": by_text["AZD0240 solid tumours"].phase == "Phase 1",
        "phase2_commercial": by_text["AZD0120 multiple myeloma"].commercialInScope,
        "brand_molecule": (
            by_text["Etcamah (camizestrant) HR+ HER2- breast cancer"].brand == "Etcamah"
            and by_text["Etcamah (camizestrant) HR+ HER2- breast cancer"].molecule == "camizestrant"
        ),
        "parenthetical_code": (
            by_text["zadavotide guraxetan (AZD2265) VECTRA-01 prostate cancer (mCRPC)"].developmentCode == "AZD2265"
        ),
        "lcm_commercial": (
            by_text["Tagrisso ADAURA2 EGFRm NSCLC stage Ia2-Ia3 following complete tumour resection"].phase == "LCM"
            and by_text["Tagrisso ADAURA2 EGFRm NSCLC stage Ia2-Ia3 following complete tumour resection"].importantLabelExpansion
        ),
        "removed_not_commercial": not by_text["AZD2068 solid tumours"].commercialInScope,
    }
    return {"ok": all(checks.values()), "checks": checks, "rowCount": len(rows)}


SELF_TEST = _self_test()
if not SELF_TEST["ok"]:
    raise RuntimeError(f"AstraZeneca pipeline adapter self-test failed: {SELF_TEST}")


@app.get("/discover/astrazeneca/pipeline/health")
async def astrazeneca_pipeline_health() -> Dict[str, Any]:
    return {
        "ok": True,
        "version": AZ_PIPELINE_VERSION,
        "readOnly": True,
        "sourceUrl": AZ_PIPELINE_URL,
        "selfTest": SELF_TEST,
    }


@app.get("/discover/astrazeneca/pipeline/probe")
async def astrazeneca_pipeline_probe() -> Dict[str, Any]:
    raw_html = await _fetch_source_html()
    rows = parse_pipeline_html(raw_html)
    summary = _summarize(rows)
    in_scope = [r for r in rows if r.commercialInScope]
    return {
        "ok": bool(rows),
        "version": AZ_PIPELINE_VERSION,
        "readOnly": True,
        "sourceUrl": AZ_PIPELINE_URL,
        "totalParsedRows": len(rows),
        "commercialInScopeRows": len(in_scope),
        **summary,
    }


@app.get("/discover/astrazeneca/pipeline", response_model=AZPipelineResponse)
async def astrazeneca_pipeline(
    include_phase1: bool = Query(default=False),
    include_removed: bool = Query(default=False),
    x_adapter_key: Optional[str] = Header(default=None),
) -> AZPipelineResponse:
    _auth(x_adapter_key)
    raw_html = await _fetch_source_html()
    all_rows = parse_pipeline_html(raw_html)
    selected = [
        r for r in all_rows
        if (include_phase1 or r.phase != "Phase 1")
        and (include_removed or not r.removedSinceLastQuarter)
    ]
    summary = _summarize(all_rows)
    return AZPipelineResponse(
        version=AZ_PIPELINE_VERSION,
        readOnly=True,
        sourceUrl=AZ_PIPELINE_URL,
        sourceAsOfValues=summary["sourceAsOfValues"],
        totalParsedRows=len(all_rows),
        returnedRows=len(selected),
        summaryByPhase=summary["summaryByPhase"],
        summaryByTherapyArea=summary["summaryByTherapyArea"],
        parseStatusSummary=summary["parseStatusSummary"],
        rows=selected,
    )
