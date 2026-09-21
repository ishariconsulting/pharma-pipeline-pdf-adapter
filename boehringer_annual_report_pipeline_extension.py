"""Read-only Boehringer Ingelheim annual-report pipeline snapshot adapter.

Boehringer's live pipeline site is currently protected by Imperva/Incapsula in
our server/browser runtimes. This adapter is intentionally a *dated static
snapshot* path over the company's published annual-report pipeline table.

The default machine URL is a third-party mirror of the Boehringer Ingelheim
2025 Highlights PDF. The document itself identifies Boehringer Ingelheim and
states that the table is the development status at the end of 2025. The mirror
must never be treated as a live first-party endpoint; provenance is surfaced in
every response.

No Airtable or master-data writes.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, List, Optional, Tuple

import fitz
import httpx
from fastapi import Header, HTTPException, Query
from pydantic import BaseModel

from main import _auth, app
from html_fetch_extension import _assert_public_http_url


ADAPTER_PROFILE = "PIPELINE_BOEHRINGER_ANNUAL_REPORT_V1"
ROUTE_VERSION = "BOEHRINGER_ANNUAL_REPORT_PIPELINE_V1.0_STATIC_READ_ONLY"
DEFAULT_SOURCE_URL = (
    "https://flcube.com/wp-content/uploads/2026/03/"
    "Boehringer-Ingelheim-Annual-Report-Highlights-2025.pdf"
)
DOCUMENT_TITLE = "Boehringer Ingelheim — 2025 Highlights"
DOCUMENT_AS_OF = "2025-12-31"
DOCUMENT_PROVENANCE = "THIRD_PARTY_MIRROR_OF_FIRST_PARTY_BOEHRINGER_2025_HIGHLIGHTS"
MAX_BYTES = 8_000_000
MIN_ROWS = 30

PHASE_RE = re.compile(r"(Registration|Phase\s+(?:I{1,3}|IV|[1-4]))\s*$", re.I)
SECTION_RE = re.compile(r"^(.+?)\s+Phase\s*$", re.I)
BI_CODE_RE = re.compile(r"\bBI\s*[- ]?\d{5,8}\b", re.I)
OTHER_CODE_RE = re.compile(r"\bCT[- ]?\d{2,5}\b", re.I)


class BoehringerAnnualPipelineResponse(BaseModel):
    version: str
    routeVersion: str
    company: str
    sourceUrl: str
    finalUrl: str
    sourceDate: str
    sourceDocumentTitle: str
    sourceProvenance: str
    retrievalMode: str
    readOnly: bool
    readyForDiscovery: bool
    rowCount: int
    rows: List[Dict[str, Any]]
    summary: Dict[str, Any]
    issues: List[Dict[str, Any]]
    diagnostics: Dict[str, Any]
    guardrails: Dict[str, Any]


def clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _norm_code(value: str) -> str:
    value = clean(value).upper().replace("-", " ")
    value = re.sub(r"\s+", " ", value)
    if value.startswith("BI "):
        return value
    if value.startswith("CT "):
        return value.replace("CT ", "CT-")
    return clean(value)


def _phase(value: str) -> str:
    n = clean(value).lower()
    if n == "registration":
        return "Filed / Registration"
    roman = {"i": "1", "ii": "2", "iii": "3", "iv": "4"}
    m = re.search(r"phase\s+(i{1,3}|iv|[1-4])", n, re.I)
    if not m:
        return ""
    token = m.group(1).lower()
    return "Phase " + roman.get(token, token)


def _line_groups(page: fitz.Page, col: int) -> List[Dict[str, Any]]:
    width = float(page.rect.width)
    mid = width / 2.0
    words = page.get_text("words", sort=False)
    selected = []
    for w in words:
        x0, y0, x1, y1, text = w[:5]
        cx = (float(x0) + float(x1)) / 2.0
        if col == 0 and cx >= mid:
            continue
        if col == 1 and cx < mid:
            continue
        selected.append((float(x0), float(y0), float(x1), float(y1), clean(text)))

    # Group words by visual baseline rather than PDF block order. This joins
    # the left-hand row text with the phase printed at the far right.
    buckets: List[List[Tuple[float, float, float, float, str]]] = []
    for word in sorted(selected, key=lambda x: (x[1], x[0])):
        cy = (word[1] + word[3]) / 2.0
        placed = False
        for bucket in reversed(buckets[-4:]):
            bcy = sum((x[1] + x[3]) / 2.0 for x in bucket) / len(bucket)
            if abs(cy - bcy) <= 2.8:
                bucket.append(word)
                placed = True
                break
        if not placed:
            buckets.append([word])

    lines: List[Dict[str, Any]] = []
    for bucket in buckets:
        bucket.sort(key=lambda x: x[0])
        text = clean(" ".join(x[4] for x in bucket if x[4]))
        if not text:
            continue
        lines.append({
            "text": text,
            "x0": min(x[0] for x in bucket),
            "x1": max(x[2] for x in bucket),
            "y0": min(x[1] for x in bucket),
            "y1": max(x[3] for x in bucket),
        })
    return sorted(lines, key=lambda x: (x["y0"], x["x0"]))


def _strip_markers(value: str) -> Tuple[str, bool, bool]:
    raw = clean(value)
    progressed = raw.startswith(">")
    partnered = "*" in raw
    raw = raw.lstrip("> ").strip()
    raw = raw.replace("*", " ")
    raw = raw.replace("🔍", " ")
    raw = raw.replace("®", "")
    raw = clean(raw)
    return raw, progressed, partnered


def _identity(asset_line: str) -> Dict[str, str]:
    asset_line, _, _ = _strip_markers(asset_line)
    development_code = ""

    m = BI_CODE_RE.search(asset_line)
    if m:
        development_code = _norm_code(m.group(0))
    else:
        m2 = OTHER_CODE_RE.search(asset_line)
        if m2:
            development_code = _norm_code(m2.group(0))

    # Parenthetical BI code is metadata, not the display asset.
    asset = clean(BI_CODE_RE.sub("", asset_line))
    asset = clean(re.sub(r"\(\s*\)", "", asset))
    if not asset and development_code:
        asset = development_code

    # If the whole asset is itself a code, preserve code as the asset.
    if BI_CODE_RE.fullmatch(asset_line) or OTHER_CODE_RE.fullmatch(asset_line):
        asset = development_code or asset_line

    molecule = ""
    if asset and not BI_CODE_RE.fullmatch(asset) and not OTHER_CODE_RE.fullmatch(asset):
        if "/" not in asset and " + " not in asset:
            molecule = asset

    return {
        "asset": asset,
        "molecule": molecule,
        "developmentCode": development_code,
        "brand": "",
    }


def _is_annotation(text: str) -> bool:
    n = clean(text).lower()
    return (
        n.startswith("fast track designation")
        or n.startswith("btd or equivalent")
        or n.startswith("being investigated only")
        or "clinical phase progress in 2025" in n
        or n.startswith("anchored in external partnership")
        or n.startswith("indication abbreviations")
    )


def _emit_row(
    company: str,
    source_url: str,
    therapeutic_area: str,
    buffer: List[str],
    phase_text: str,
) -> Optional[Dict[str, Any]]:
    meaningful = [clean(x) for x in buffer if clean(x) and not _is_annotation(x)]
    if not meaningful:
        return None

    asset_raw = meaningful[0]
    asset_line, progressed, partnered = _strip_markers(asset_raw)
    if not asset_line:
        return None

    identity = _identity(asset_line)
    detail = ""
    for line in meaningful[1:]:
        if "|" in line:
            detail = line
            break

    modality = ""
    indication = ""
    if detail:
        left, right = detail.rsplit("|", 1)
        modality = clean(left)
        indication = clean(right)

    phase = _phase(phase_text)
    if not phase:
        return None

    key = "|".join([
        company,
        therapeutic_area,
        identity["asset"],
        identity["developmentCode"],
        indication,
        phase,
    ])
    source_record_id = "BIAR25-" + hashlib.sha1(key.lower().encode("utf-8")).hexdigest()[:16].upper()

    return {
        "company": company,
        "sourceFamily": "Boehringer Ingelheim 2025 Highlights",
        "sourceRecordId": source_record_id,
        "sourceUrl": source_url,
        "sourceDate": DOCUMENT_AS_OF,
        "asset": identity["asset"],
        "molecule": identity["molecule"],
        "developmentCode": identity["developmentCode"],
        "brand": identity["brand"],
        "indication": indication,
        "phase": phase,
        "programStatus": "Active",
        "sponsorOwner": company,
        "partners": [],
        "therapeuticArea": therapeutic_area,
        "modality": modality,
        "clinicalPhaseProgress2025": progressed,
        "externallyPartneredOrAcquired": partnered,
        "parserMethod": "BOEHRINGER_ANNUAL_REPORT_ROW_END_PHASE",
        "sourceAdapter": ADAPTER_PROFILE,
    }


def parse_boehringer_annual_report(
    company: str,
    source_url: str,
    data: bytes,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any], List[str]]:
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid Boehringer annual-report PDF: {exc}") from exc

    marker = "overview of our projects and their development status at the end of 2025"
    pipeline_pages = []
    for idx in range(len(doc)):
        text = clean(doc[idx].get_text("text", sort=True)).lower()
        if marker in text:
            pipeline_pages.append(idx)

    issues: List[str] = []
    if not pipeline_pages:
        return [], {"pageCount": len(doc), "pipelinePages": []}, ["2025 pipeline table marker not found"]

    rows: List[Dict[str, Any]] = []
    page_diags: List[Dict[str, Any]] = []
    carry_ta = ""

    for pidx in pipeline_pages:
        page = doc[pidx]
        last_ta_this_page = ""
        for col in (0, 1):
            lines = _line_groups(page, col)
            current_ta = carry_ta if col == 0 else ""
            buffer: List[str] = []
            emitted = 0
            section_count = 0

            for line in lines:
                text = clean(line["text"])
                if not text:
                    continue

                # Ignore running headers / page furniture.
                low = text.lower()
                if (
                    "boehringer ingelheim" in low
                    and ("highlights" in low or "information about the group" in low)
                ):
                    continue
                if marker in low:
                    continue

                sec = SECTION_RE.match(text)
                if sec and not PHASE_RE.search(text):
                    title = clean(sec.group(1))
                    if title and len(title) <= 80:
                        current_ta = title
                        last_ta_this_page = title
                        buffer = []
                        section_count += 1
                        continue

                pm = PHASE_RE.search(text)
                if pm and current_ta:
                    prefix = clean(text[: pm.start()])
                    if prefix:
                        buffer.append(prefix)
                    row = _emit_row(
                        company,
                        source_url,
                        current_ta,
                        buffer,
                        pm.group(1),
                    )
                    if row:
                        rows.append(row)
                        emitted += 1
                    buffer = []
                    continue

                if current_ta:
                    # Stop table parsing within a column once prose clearly
                    # begins; table rows are short and phase-terminated.
                    if len(text) > 220 and "|" not in text:
                        buffer = []
                        current_ta = ""
                        continue
                    buffer.append(text)

            page_diags.append({
                "page": pidx + 1,
                "column": col + 1,
                "lineCount": len(lines),
                "sectionCount": section_count,
                "rowsEmitted": emitted,
            })

            if current_ta:
                last_ta_this_page = current_ta

        if last_ta_this_page:
            carry_ta = last_ta_this_page

    # Exact dedupe only. Distinct indications/phases are legitimate programme rows.
    deduped: List[Dict[str, Any]] = []
    seen = set()
    for row in rows:
        key = (
            clean(row.get("therapeuticArea")).lower(),
            clean(row.get("asset")).lower(),
            clean(row.get("developmentCode")).lower(),
            clean(row.get("indication")).lower(),
            clean(row.get("phase")).lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)

    sentinel_terms = {
        "survodutide": False,
        "vicadrostat": False,
        "zongertinib": False,
        "nerandomilast": False,
        "ct-155": False,
        "bi 764524": False,
    }
    universe = " ".join(
        clean(x)
        for row in deduped
        for x in [row.get("asset"), row.get("developmentCode")]
        if clean(x)
    ).lower()
    for term in sentinel_terms:
        sentinel_terms[term] = term in universe

    if len(deduped) < MIN_ROWS:
        issues.append(f"too few annual-report pipeline rows: {len(deduped)} < {MIN_ROWS}")
    missing = [k for k, ok in sentinel_terms.items() if not ok]
    if missing:
        issues.append("missing sentinel assets: " + ", ".join(missing))
    if any(not row.get("phase") for row in deduped):
        issues.append("one or more rows have unresolved phase")

    phase_counts: Dict[str, int] = {}
    ta_counts: Dict[str, int] = {}
    for row in deduped:
        phase_counts[row["phase"]] = phase_counts.get(row["phase"], 0) + 1
        ta = row["therapeuticArea"]
        ta_counts[ta] = ta_counts.get(ta, 0) + 1

    diagnostics = {
        "pageCount": len(doc),
        "pipelinePages": [x + 1 for x in pipeline_pages],
        "pageColumns": page_diags,
        "rawRows": len(rows),
        "dedupedRows": len(deduped),
        "exactDuplicatesRemoved": len(rows) - len(deduped),
        "phaseCounts": phase_counts,
        "therapeuticAreaCounts": ta_counts,
        "sentinels": sentinel_terms,
        "documentAsOf": DOCUMENT_AS_OF,
        "documentProvenance": DOCUMENT_PROVENANCE,
        "portfolioDependentValidation": False,
        "writes": 0,
    }
    return deduped, diagnostics, issues


async def _fetch_pdf(url: str, timeout_seconds: float) -> Tuple[bytes, str]:
    await _assert_public_http_url(url)
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; PharmaPipelineResearch/1.0)",
        "Accept": "application/pdf,*/*",
    }
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds, connect=min(12.0, timeout_seconds)),
            follow_redirects=True,
            headers=headers,
        ) as client:
            response = await client.get(url)
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="Boehringer annual-report PDF fetch timed out") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Boehringer annual-report PDF fetch failed: {exc}") from exc

    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"Boehringer annual-report PDF returned HTTP {response.status_code}")
    if len(response.content) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="Boehringer annual-report PDF exceeds size limit")
    if not response.content.startswith(b"%PDF"):
        raise HTTPException(status_code=422, detail="Boehringer annual-report source is not a PDF")
    await _assert_public_http_url(str(response.url))
    return response.content, str(response.url)


async def extract_boehringer_annual_pipeline(
    company: str = "Boehringer Ingelheim",
    source_url: str = DEFAULT_SOURCE_URL,
    timeout_seconds: float = 35.0,
) -> BoehringerAnnualPipelineResponse:
    data, final_url = await _fetch_pdf(source_url, timeout_seconds)
    rows, diagnostics, issues = parse_boehringer_annual_report(company, final_url, data)
    ready = not issues

    return BoehringerAnnualPipelineResponse(
        version=ADAPTER_PROFILE,
        routeVersion=ROUTE_VERSION,
        company=company,
        sourceUrl=source_url,
        finalUrl=final_url,
        sourceDate=DOCUMENT_AS_OF,
        sourceDocumentTitle=DOCUMENT_TITLE,
        sourceProvenance=DOCUMENT_PROVENANCE,
        retrievalMode="STATIC_DOCUMENT",
        readOnly=True,
        readyForDiscovery=ready,
        rowCount=len(rows),
        rows=rows,
        summary={
            "structuralValidationPass": ready,
            "actual": {"Total": len(rows)},
            "productionStatus": (
                "READY FOR DATED SNAPSHOT/BACKFILL COMPARISON"
                if ready else
                "FAIL CLOSED - BOEHRINGER SNAPSHOT REVIEW REQUIRED"
            ),
            "canonicalLiveSource": False,
            "snapshotOnly": True,
            "writeMode": "READ_ONLY",
        },
        issues=[{"issue": x} for x in issues],
        diagnostics=diagnostics,
        guardrails={
            "airtableWrites": False,
            "portfolioWrites": False,
            "masterDataWrites": False,
            "publicHttpOnly": True,
            "staticSnapshotOnly": True,
            "thirdPartyMirror": True,
            "documentProvenanceExplicit": True,
            "liveSourceSubstitution": False,
            "portfolioDependentValidation": False,
        },
    )


@app.get("/extract/boehringer/annual-report-pipeline/health")
async def boehringer_annual_health() -> Dict[str, Any]:
    return {
        "ok": True,
        "version": ADAPTER_PROFILE,
        "routeVersion": ROUTE_VERSION,
        "readOnly": True,
        "snapshotOnly": True,
    }


@app.get("/extract/boehringer/annual-report-pipeline", response_model=BoehringerAnnualPipelineResponse)
async def boehringer_annual_route(
    company: str = Query(default="Boehringer Ingelheim", min_length=1, max_length=160),
    source_url: str = Query(default=DEFAULT_SOURCE_URL, min_length=8),
    timeout_seconds: float = Query(default=35.0, ge=5.0, le=35.0),
    x_adapter_key: Optional[str] = Header(default=None),
) -> BoehringerAnnualPipelineResponse:
    _auth(x_adapter_key)
    return await extract_boehringer_annual_pipeline(company, source_url, timeout_seconds)
