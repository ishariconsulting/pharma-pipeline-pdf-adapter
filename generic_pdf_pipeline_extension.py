"""Reusable read-only semantic PDF pipeline table adapter.

Targets official pipeline PDFs that expose semantic table columns such as
Development code, Indications and Stage. Column positions are inferred from
page headers; no company-specific coordinates or Portfolio state are used.
"""

from __future__ import annotations

import io
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import fitz
import httpx
from fastapi import Header, HTTPException, Query
from pydantic import BaseModel

from main import _auth, app
from html_fetch_extension import _assert_public_http_url


ADAPTER_PROFILE = "PIPELINE_GENERIC_PDF_TABLE_V1"
ROUTE_VERSION = "GENERIC_PDF_PIPELINE_TABLE_V1.0_READ_ONLY"
MAX_BYTES = 15_000_000
MIN_ROWS = 4


class GenericPdfPipelineResponse(BaseModel):
    version: str
    routeVersion: str
    company: str
    sourceUrl: str
    finalUrl: str
    retrievalMode: str
    readOnly: bool
    readyForDiscovery: bool
    rowCount: int
    rows: List[Dict[str, Any]]
    summary: Dict[str, Any]
    issues: List[Dict[str, Any]]
    validation: Dict[str, Any]
    diagnostics: Dict[str, Any]
    guardrails: Dict[str, Any]


def clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", clean(value).lower()).strip()


def phase_canonical(value: Any) -> str:
    s = clean(value)
    n = norm(s)
    if not n:
        return ""
    if "approved" in n:
        return "Approved"
    if any(x in n for x in ("filed", "registration", "regulatory review")):
        return "Filed / Registration"
    if "preclinical" in n or "pre clinical" in n:
        return "Preclinical"

    # Common source forms: P-I, P-II, P-III, Phase 1/2, Phase III.
    m = re.search(r"\bP\s*[-–]?\s*(I{1,3}|IV|[1-4])\b", s, re.I)
    if not m:
        m = re.search(r"\bPhase\s*(I{1,3}|IV|[1-4])\b", s, re.I)
    if m:
        token = m.group(1).upper()
        roman = {"I": 1, "II": 2, "III": 3, "IV": 4}
        number = int(token) if token.isdigit() else roman.get(token)
        if number:
            return f"Phase {number}"
    return ""


def _word_center_y(word: Tuple[Any, ...]) -> float:
    return (float(word[1]) + float(word[3])) / 2.0


def _join_words(words: List[Tuple[Any, ...]]) -> str:
    return clean(" ".join(str(w[4]) for w in sorted(words, key=lambda x: (x[1], x[0]))))


def _find_header(words: List[Tuple[Any, ...]]) -> Optional[Dict[str, float]]:
    """Infer semantic PDF-table columns from header labels.

    A production pipeline table must expose Development, Indication,
    Country/Region and Stage/Phase semantics. Optional Type/Modality headers
    tighten the left-column boundary but are not required.
    """
    dev = [w for w in words if norm(w[4]) == "development"]
    indications = [w for w in words if norm(w[4]) in {"indications", "indication"}]
    stages = [w for w in words if norm(w[4]) in {"stage", "phase"}]
    regions = [w for w in words if norm(w[4]) in {"country", "country region", "region", "country/"}]
    type_words = [w for w in words if norm(w[4]) == "type"]
    modalities = [w for w in words if norm(w[4]) == "modality"]

    if not dev or not indications or not stages or not regions:
        return None

    best = None
    best_span = 9999.0
    for d in dev:
        dy = _word_center_y(d)
        for i in indications:
            iy = _word_center_y(i)
            if abs(dy - iy) > 40:
                continue
            for rg in regions:
                ry = _word_center_y(rg)
                if abs(dy - ry) > 45:
                    continue
                for st in stages:
                    sy = _word_center_y(st)
                    if abs(dy - sy) > 45:
                        continue
                    if not (float(d[0]) < float(i[0]) < float(rg[0]) < float(st[0])):
                        continue
                    span = max(dy, iy, ry, sy) - min(dy, iy, ry, sy)
                    if span < best_span:
                        best_span = span
                        left_boundaries = [
                            float(w[0]) for w in [*type_words, *modalities]
                            if float(d[0]) < float(w[0]) < float(i[0])
                            and abs(_word_center_y(w) - dy) <= 45
                        ]
                        best = {
                            "headerY": max(dy, iy, ry, sy),
                            "assetX": float(d[0]),
                            "assetRightX": min(left_boundaries) if left_boundaries else float(i[0]),
                            "indicationX": float(i[0]),
                            "regionX": float(rg[0]),
                            "stageX": float(st[0]),
                        }
    return best


def _is_code_like(text: str) -> bool:
    s = clean(text)
    n = norm(s)
    if not s or len(s) > 70:
        return False
    if n in {"development code", "generic name", "brand name", "type of drug", "modality"}:
        return False
    if s.startswith("*"):
        return False
    # Require at least one number plus an alphabetic component, which captures
    # development codes such as TAK-861, RG6102, BNT122, BI 456906, etc.
    return bool(re.search(r"[A-Za-z]", s) and re.search(r"\d", s))


def _stage_candidates(words: List[Tuple[Any, ...]], header: Dict[str, float]) -> List[Tuple[float, str, str]]:
    out: List[Tuple[float, str, str]] = []
    stage_x = header["stageX"]
    for w in words:
        x0 = float(w[0])
        if x0 < stage_x - 18:
            continue
        raw = clean(w[4])
        phase = phase_canonical(raw)
        if not phase:
            continue
        y = _word_center_y(w)

        # Include date/qualifier words on the same visual line as the stage.
        same = [
            x for x in words
            if abs(_word_center_y(x) - y) <= 4.5
            and float(x[0]) >= stage_x - 18
        ]
        stage_text = _join_words(same)
        out.append((y, phase, stage_text))

    # Avoid duplicate word-level hits on the same line.
    dedup: List[Tuple[float, str, str]] = []
    for row in sorted(out, key=lambda x: x[0]):
        if dedup and abs(dedup[-1][0] - row[0]) <= 3.5:
            continue
        dedup.append(row)
    return dedup


def _code_anchors(words: List[Tuple[Any, ...]], header: Dict[str, float]) -> List[Tuple[float, str]]:
    """Return candidate development-code anchors from the semantic code column."""
    left_min = max(0.0, header["assetX"] - 20.0)
    left_max = header.get("assetRightX", header["indicationX"]) - 5.0
    by_line: Dict[int, List[Tuple[Any, ...]]] = {}

    for w in words:
        x0 = float(w[0])
        cy = _word_center_y(w)
        if cy <= header["headerY"] + 8:
            continue
        if not (left_min <= x0 < left_max):
            continue
        by_line.setdefault(int(round(cy / 3.0) * 3), []).append(w)

    anchors: List[Tuple[float, str]] = []
    for _, line_words in sorted(by_line.items()):
        text = _join_words(line_words)
        if not text:
            continue
        # Explicit generic-name lines are evidence, not development codes.
        if "<" in text or ">" in text:
            continue
        # Country/region suffixes often identify a brand presentation.
        if re.search(r"\((?:US|U\.S\.|EU|Japan|China|Global)\)", text, re.I):
            continue
        if _is_code_like(text):
            y = sum(_word_center_y(w) for w in line_words) / len(line_words)
            anchors.append((y, text))
    return anchors


def _active_code(anchors: List[Tuple[float, str]], y: float) -> Tuple[Optional[float], str]:
    """Associate a stage row to the nearest plausible development-code anchor.

    PDF tables often place the stage a few points above the code/indication
    baseline, so a small forward allowance is required. Prefer geometric
    proximity rather than blindly carrying the previous code forward.
    """
    eligible = [
        (cy, text)
        for cy, text in anchors
        if (cy <= y + 24.0 and y - cy <= 140.0)
    ]
    if not eligible:
        return None, ""
    return min(eligible, key=lambda item: (abs(item[0] - y), 0 if item[0] <= y else 1))


def _generic_name_for_code(
    words: List[Tuple[Any, ...]],
    header: Dict[str, float],
    code_y: Optional[float],
    next_code_y: Optional[float],
) -> str:
    if code_y is None:
        return ""
    left_min = max(0.0, header["assetX"] - 20.0)
    left_max = header.get("assetRightX", header["indicationX"]) - 5.0
    upper = next_code_y if next_code_y is not None else code_y + 90.0
    selected = [
        w for w in words
        if left_min <= float(w[0]) < left_max
        and code_y - 2.0 <= _word_center_y(w) < upper - 2.0
    ]
    text = _join_words(selected)
    matches = re.findall(r"<([^>]{2,100})>", text)
    return clean(matches[0]) if matches else ""


def parse_semantic_pdf(company: str, source_url: str, data: bytes) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid PDF: {exc}") from exc

    rows: List[Dict[str, Any]] = []
    page_diags: List[Dict[str, Any]] = []
    active_header: Optional[Dict[str, float]] = None

    for page_idx in range(len(doc)):
        page = doc[page_idx]
        words = page.get_text("words")
        page_text = clean(page.get_text("text", sort=True))

        # Do not treat pipeline-change/removal appendices as the current-state
        # table even when they contain similar vocabulary.
        appendix = bool(re.search(
            r"\brecent\s+pipeline\s+progress\b|\bprojects?\s+removed\s+from\s+pipeline\b|\bdiscontinued\b",
            page_text[:1800],
            re.I,
        ))
        if appendix:
            active_header = None
            continue

        detected = _find_header(words)
        inherited = False
        if detected:
            active_header = detected
        elif active_header:
            # Pipeline tables commonly continue onto the next page without
            # repeating headers. Reuse only the X-axis geometry; headerY from
            # the previous page must not suppress top-of-page code anchors.
            inherited_header = dict(active_header)
            inherited_header["headerY"] = 0.0
            probe = _stage_candidates(words, inherited_header)
            if len(probe) >= 2:
                detected = inherited_header
                inherited = True

        if not detected:
            continue

        header = detected
        stages = _stage_candidates(words, header)
        anchors = _code_anchors(words, header)
        anchor_ys = [y for y, _ in anchors]
        parsed_here = 0
        rejected_here = 0
        inherited_indication_by_code: Dict[str, str] = {}

        for y, phase, stage_text in stages:
            code_y, development_code = _active_code(anchors, y)
            if not development_code:
                rejected_here += 1
                continue

            indication_words = [
                w for w in words
                if header["indicationX"] - 6 <= float(w[0]) < header["regionX"] - 3
                and abs(_word_center_y(w) - y) <= 19.0
            ]
            indication = _join_words(indication_words)

            # If a market/stage continuation line omits the indication, inherit
            # the most recent indication for the same development code.
            if indication:
                inherited_indication_by_code[development_code] = indication
            else:
                indication = inherited_indication_by_code.get(development_code, "")

            region_words = [
                w for w in words
                if header["regionX"] - 3 <= float(w[0]) < header["stageX"] - 3
                and abs(_word_center_y(w) - y) <= 7.0
            ]
            region = _join_words(region_words)
            if region == "-":
                region = ""

            if not indication:
                rejected_here += 1
                continue

            next_code_y = None
            if code_y is not None:
                future = [ay for ay in anchor_ys if ay > code_y + 2.0]
                next_code_y = min(future) if future else None
            molecule = _generic_name_for_code(
                words,
                header,
                code_y,
                next_code_y,
            )

            rows.append({
                "company": company,
                "sourceFamily": "Company Pipeline",
                "sourceRecordId": f"pdf:p{page_idx+1}:y{int(round(y))}",
                "sourceUrl": source_url,
                "asset": molecule or development_code,
                "molecule": molecule,
                "developmentCode": development_code,
                "brand": "",
                "indication": indication,
                "phase": phase,
                "phaseEvidence": "SOURCE_PDF_TABLE",
                "programStatus": "",
                "sponsorOwner": company,
                "partners": [],
                "study": "",
                "trialIds": [],
                "therapeuticArea": "",
                "marketRegion": region,
                "sourceStageText": stage_text,
                "sourcePage": page_idx + 1,
                "sourceOrdinal": len(rows) + 1,
                "parserMethod": "SEMANTIC_PDF_TABLE",
                "sourceAdapter": ADAPTER_PROFILE,
            })
            parsed_here += 1

        page_diags.append({
            "page": page_idx + 1,
            "headerInherited": inherited,
            "header": {k: round(v, 1) for k, v in header.items()},
            "codeAnchors": len(anchors),
            "stageRows": len(stages),
            "parsedRows": parsed_here,
            "rejectedRows": rejected_here,
        })

    # Exact source-grain de-duplication only.
    deduped: List[Dict[str, Any]] = []
    seen = set()
    for row in rows:
        key = (
            norm(row["developmentCode"]),
            norm(row["molecule"]),
            norm(row["indication"]),
            norm(row["phase"]),
            norm(row["marketRegion"]),
        )
        if key in seen:
            continue
        seen.add(key)
        row["sourceOrdinal"] = len(deduped) + 1
        deduped.append(row)

    diagnostics = {
        "pageCount": len(doc),
        "semanticTablePages": len(page_diags),
        "pages": page_diags,
        "candidateRows": len(rows),
        "dedupedRows": len(deduped),
        "exactDuplicatesRemoved": len(rows) - len(deduped),
        "exactDuplicates": 0,
        "phaseUnresolved": 0,
        "rowFailures": 0,
        "boundaryWarnings": 0,
        "companySpecificParserBranch": False,
        "portfolioDependentValidation": False,
        "writes": 0,
    }
    return deduped, diagnostics


async def download_pdf(url: str, timeout_seconds: float) -> Tuple[bytes, str]:
    await _assert_public_http_url(url)
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise HTTPException(status_code=400, detail="Only public http/https URLs are allowed")

    headers = {
        "User-Agent": "Mozilla/5.0 SemanticPipelinePdf/1.0",
        "Accept": "application/pdf,*/*;q=0.8",
    }
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds, connect=12.0),
            follow_redirects=True,
            headers=headers,
        ) as client:
            response = await client.get(url)
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="Pipeline PDF fetch timed out") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Pipeline PDF fetch failed: {exc}") from exc

    if response.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Pipeline PDF source returned HTTP {response.status_code}")
    if len(response.content) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="Pipeline PDF exceeds size limit")
    if not response.content.startswith(b"%PDF"):
        raise HTTPException(status_code=502, detail="Pipeline source did not return a PDF")

    final_url = str(response.url)
    await _assert_public_http_url(final_url)
    return response.content, final_url


async def extract_generic_pdf(
    company: str,
    source_url: str,
    timeout_seconds: float = 35.0,
) -> GenericPdfPipelineResponse:
    data, final_url = await download_pdf(source_url, timeout_seconds)
    rows, diagnostics = parse_semantic_pdf(company, final_url, data)

    incomplete = [r["sourceRecordId"] for r in rows if not (r.get("asset") and r.get("indication") and r.get("phase"))]
    issues: List[str] = []
    if len(rows) < MIN_ROWS:
        issues.append(f"too few structured rows: {len(rows)} < {MIN_ROWS}")
    if incomplete:
        issues.append(f"{len(incomplete)} parsed rows missing core fields")

    ready = not issues
    summary = {
        "structuralValidationPass": ready,
        "actual": {"Total": len(rows)},
        "productionStatus": "READY FOR AIRTABLE DELTA COMPARISON" if ready else "FAIL CLOSED - PARSER/STRUCTURE REVIEW REQUIRED",
        "selectedMethod": "SEMANTIC_PDF_TABLE",
        "portfolioDependentValidation": False,
        "companySpecificParserBranch": False,
        "writeMode": "READ_ONLY",
    }
    validation = {
        "pass": ready,
        "rowCount": len(rows),
        "issues": issues,
        "allCoreRowsComplete": not incomplete,
        "semanticTableFound": diagnostics["semanticTablePages"] > 0,
    }

    return GenericPdfPipelineResponse(
        version=ADAPTER_PROFILE,
        routeVersion=ROUTE_VERSION,
        company=company,
        sourceUrl=source_url,
        finalUrl=final_url,
        retrievalMode="STATIC_DOCUMENT",
        readOnly=True,
        readyForDiscovery=ready,
        rowCount=len(rows),
        rows=rows,
        summary=summary,
        issues=[{"issue": x} for x in issues],
        validation=validation,
        diagnostics={**diagnostics, "documentBytes": len(data)},
        guardrails={
            "airtableWrites": False,
            "portfolioWrites": False,
            "masterDataWrites": False,
            "companySpecificParserBranch": False,
            "portfolioDependentValidation": False,
            "fuzzyIdentityResolution": False,
            "publicHttpOnly": True,
        },
    )


@app.get("/extract/generic/pdf-pipeline-table/health")
async def generic_pdf_health() -> Dict[str, Any]:
    return {"ok": True, "version": ADAPTER_PROFILE, "routeVersion": ROUTE_VERSION, "retrievalMode": "STATIC_DOCUMENT", "readOnly": True}


@app.get("/extract/generic/pdf-pipeline-table", response_model=GenericPdfPipelineResponse)
async def generic_pdf_pipeline(
    company: str = Query(..., min_length=1, max_length=160),
    source_url: str = Query(..., min_length=8),
    timeout_seconds: float = Query(default=35.0, ge=5.0, le=35.0),
    x_adapter_key: Optional[str] = Header(default=None),
) -> GenericPdfPipelineResponse:
    _auth(x_adapter_key)
    return await extract_generic_pdf(company, source_url, timeout_seconds)
