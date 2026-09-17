"""Bristol Myers Squibb official pipeline adapter V3.

Read-only. BMS renders programme rows client-side. This extension uses the
existing browser retrieval worker, then parses its rendered visible text.
No Airtable/master-data writes are performed here.
"""

from __future__ import annotations

import os
import re
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

import httpx
from fastapi import Header, HTTPException, Query

from main import ExtractionResponse, _auth, _clean, _norm, app

BMS_ADAPTER_VERSION = "PIPELINE_BMS_HTML_V1.2"
BMS_PIPELINE_URL = "https://www.bms.com/research-and-development/pipeline.html"

BMS_TAS = {
    "cardiovascular": "Cardiovascular",
    "hematology": "Hematology",
    "immunology": "Immunology",
    "neuroscience": "Neuroscience",
    "oncology": "Oncology",
}

BMS_FOCUS_AREAS = sorted(
    {
        "Multiple Myeloma",
        "Lymphoma",
        "Leukemia",
        "Sickle Cell Disease",
        "Prostate Cancer",
        "Lung Cancer",
        "Solid Tumors",
        "Breast Cancer",
        "Urothelial Cancer",
        "Hepatocellular Carcinoma",
        "Pancreatic Cancer",
        "Renal Cell Carcinoma",
        "Colorectal Cancer",
        "Gastric Cancer",
    },
    key=len,
    reverse=True,
)

PHASE_FIND_RE = re.compile(
    r"\b(Phase\s*([123])\s+in\s+Progress|Registration\s*(?:\(([^)]*)\))?)\b",
    re.I,
)
BMS_CODE_RE = re.compile(r"\bBMS[-\u2010-\u2015 ]?\d{5,9}\b", re.I)


def _clean_source_text(value: Any) -> str:
    value = _clean(value)
    value = value.replace("^{®}", "®").replace("^{™}", "™")
    value = value.replace("∗", "").replace("*", "")
    return re.sub(r"\s+", " ", value).strip()


def _extract_dev_code(asset: str) -> str:
    match = BMS_CODE_RE.search(asset or "")
    if not match:
        return ""
    return (
        match.group(0)
        .replace("\u2010", "-")
        .replace("\u2011", "-")
        .replace("\u2012", "-")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace(" ", "-")
        .upper()
    )


def _source_date(text: str) -> Optional[str]:
    match = re.search(
        r"\bAs\s+of\s+([A-Z][a-z]+\s+\d{1,2},\s+\d{4})\b",
        text,
        re.I,
    )
    return _clean(match.group(1)) if match else None


async def _fetch_browser_rendered(url: str) -> Dict[str, Any]:
    base = os.getenv("BROWSER_FETCH_BASE_URL", "").strip().rstrip("/")
    key = os.getenv("BROWSER_FETCH_KEY", "").strip()
    if not base or not key:
        raise HTTPException(
            status_code=502,
            detail="BMS requires browser retrieval but browser worker is not configured",
        )

    endpoint = f"{base}/fetch/browser"
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(50.0, connect=12.0),
            follow_redirects=False,
        ) as client:
            response = await client.get(
                endpoint,
                params={"url": url, "timeout_seconds": 35.0},
                headers={"X-Browser-Key": key, "Accept": "application/json"},
            )
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="BMS browser retrieval timed out") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"BMS browser retrieval failed: {type(exc).__name__}") from exc

    if response.status_code >= 400:
        try:
            detail = response.json().get("detail")
        except Exception:
            detail = response.text[:500]
        raise HTTPException(
            status_code=502,
            detail=f"BMS browser worker failed ({response.status_code}: {detail})",
        )

    try:
        payload = response.json()
    except Exception as exc:
        raise HTTPException(status_code=502, detail="BMS browser worker returned invalid JSON") from exc

    text = _clean(payload.get("visibleText", ""))
    if len(text) < 2000:
        raise HTTPException(status_code=502, detail="BMS rendered page remained too sparse")
    return payload


def _split_focus_and_indication(rest: str) -> Tuple[str, str]:
    value = _clean_source_text(rest)
    for focus in BMS_FOCUS_AREAS:
        if value.lower().startswith(focus.lower() + " "):
            indication = value[len(focus):].strip()
            if indication:
                return focus, indication
    return "", value


def _find_ta(segment: str) -> Optional[Tuple[int, int, str]]:
    best: Optional[Tuple[int, int, str]] = None
    for display in BMS_TAS.values():
        match = re.search(rf"\b{re.escape(display)}\b", segment, re.I)
        if not match:
            continue
        candidate = (match.start(), match.end(), display)
        if best is None or candidate[0] < best[0]:
            best = candidate
    return best


def _parse_bms_rendered_text(
    visible_text: str,
    source_url: str,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    text = re.sub(r"\s+", " ", visible_text or "").strip()
    source_date = _source_date(text)
    matches = list(PHASE_FIND_RE.finditer(text))

    table_start = 0
    if matches:
        prefix = text[: matches[0].start()]
        header_hits = list(re.finditer(r"Partner[- ]run\s+study", prefix, re.I))
        if header_hits:
            table_start = header_hits[-1].end()
        else:
            active = list(re.finditer(r"Active\s+Filters", prefix, re.I))
            if active:
                table_start = active[-1].end()

    rows: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []
    previous_end = table_start

    for ordinal, match in enumerate(matches, start=1):
        segment = _clean_source_text(text[previous_end: match.start()])
        previous_end = match.end()
        segment = re.sub(r"(?:\s+|^)1\s+2\s+3\s*$", "", segment).strip()

        ta = _find_ta(segment)
        if not ta:
            rejected.append({
                "sourceCardOrdinal": ordinal,
                "phaseMarker": _clean(match.group(1)),
                "reason": "THERAPEUTIC_AREA_NOT_FOUND",
                "segmentTail": segment[-500:],
            })
            continue

        ta_start, ta_end, ta_name = ta
        asset = _clean_source_text(segment[:ta_start])
        rest = _clean_source_text(segment[ta_end:])
        focus_area, indication = _split_focus_and_indication(rest)

        if not asset or not indication:
            rejected.append({
                "sourceCardOrdinal": ordinal,
                "phaseMarker": _clean(match.group(1)),
                "reason": "ASSET_OR_INDICATION_MISSING",
                "asset": asset,
                "therapeuticArea": ta_name,
                "rest": rest,
            })
            continue

        if match.group(2):
            phase = f"Phase {match.group(2)}"
            registration_geo = ""
        else:
            phase = "Filed / Registration"
            registration_geo = _clean(match.group(3) or "")

        rows.append({
            "company": "Bristol Myers Squibb",
            "asset": asset,
            "developmentCode": _extract_dev_code(asset),
            "mechanismOfAction": "",
            "indication": indication,
            "phase": phase,
            "therapeuticArea": ta_name,
            "sourceTherapeuticArea": ta_name,
            "sourceFocusArea": focus_area,
            "registrationGeography": registration_geo,
            "sourceUrl": source_url,
            "sourceConfidence": "High",
            "sourceAdapter": BMS_ADAPTER_VERSION,
            "sourceCardOrdinal": ordinal,
        })

    fingerprints = [
        (
            _norm(r.get("asset")),
            _norm(r.get("indication")),
            _norm(r.get("phase")),
            _norm(r.get("sourceFocusArea")),
            _norm(r.get("registrationGeography")),
        )
        for r in rows
    ]
    exact_duplicate_count = sum(
        count - 1 for count in Counter(fingerprints).values() if count > 1
    )

    phase_counts = Counter(r.get("phase", "") for r in rows)
    ta_counts = Counter(r.get("sourceTherapeuticArea", "") for r in rows)
    unique_compounds = len({_norm(r.get("asset")) for r in rows if r.get("asset")})

    diagnostics = {
        "parser": BMS_ADAPTER_VERSION,
        "sourceDate": source_date,
        "renderedVisibleTextLength": len(text),
        "phaseMarkersFound": len(matches),
        "parsedRows": len(rows),
        "rejectedRows": len(rejected),
        "rejectedDetails": rejected[:30],
        "exactDuplicates": exact_duplicate_count,
        "phaseCounts": dict(phase_counts),
        "therapeuticAreaCounts": dict(ta_counts),
        "uniqueCompoundLabels": unique_compounds,
        "sourcePublishedCompoundCount": 49,
        "structuralNote": (
            "BMS programme rows are browser-rendered. The 49-compound headline is "
            "an asset-level count and is not expected to equal programme-row count."
        ),
    }
    return rows, diagnostics


def _validate_bms(
    rows: List[Dict[str, Any]],
    diagnostics: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    diagnostics = diagnostics or {}
    issues: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []
    allowed_phases = {"Phase 1", "Phase 2", "Phase 3", "Filed / Registration"}

    missing_core = [
        {
            "asset": r.get("asset", ""),
            "sourceCardOrdinal": r.get("sourceCardOrdinal"),
            "missing": [
                field for field in ["asset", "indication", "phase", "sourceTherapeuticArea"]
                if not _clean(r.get(field, ""))
            ],
        }
        for r in rows
        if any(
            not _clean(r.get(field, ""))
            for field in ["asset", "indication", "phase", "sourceTherapeuticArea"]
        )
    ]
    if missing_core:
        issues.append({"issue": "Rows missing core fields", "count": len(missing_core), "sample": missing_core[:20]})

    invalid_phases = [
        {"asset": r.get("asset", ""), "phase": r.get("phase", ""), "sourceCardOrdinal": r.get("sourceCardOrdinal")}
        for r in rows
        if r.get("phase") not in allowed_phases
    ]
    if invalid_phases:
        issues.append({"issue": "Rows contain unsupported phase values", "count": len(invalid_phases), "sample": invalid_phases[:20]})

    rejected_rows = int(diagnostics.get("rejectedRows", 0) or 0)
    if rejected_rows:
        issues.append({"issue": "One or more rendered BMS programme blocks failed extraction", "count": rejected_rows})

    exact_duplicates = int(diagnostics.get("exactDuplicates", 0) or 0)
    if exact_duplicates:
        issues.append({"issue": "Exact BMS source programme rows are duplicated", "count": exact_duplicates})

    if len(rows) < 50 or len(rows) > 180:
        issues.append({
            "issue": "Programme count outside structural sanity bounds",
            "actualTotal": len(rows),
            "allowedRange": [50, 180],
        })

    counts = Counter(r.get("phase", "") for r in rows)
    for phase in ["Phase 1", "Phase 2", "Phase 3"]:
        if counts.get(phase, 0) <= 0:
            issues.append({"issue": "Major development phase unexpectedly empty", "phase": phase})

    ta_counts = Counter(r.get("sourceTherapeuticArea", "") for r in rows)
    missing_tas = [display for display in BMS_TAS.values() if ta_counts.get(display, 0) <= 0]
    if missing_tas:
        issues.append({"issue": "Expected BMS therapeutic area absent from parsed source", "therapeuticAreas": missing_tas})

    unique_compounds = int(diagnostics.get("uniqueCompoundLabels", 0) or 0)
    if unique_compounds != 49:
        warnings.append({
            "warning": (
                "Parsed unique asset labels do not equal the BMS 49-compound headline. "
                "This is diagnostic, not an automatic rejection, because brand/combination labels can differ from compound counting."
            ),
            "headlineCompoundCount": 49,
            "parsedUniqueAssetLabels": unique_compounds,
        })

    structural_valid = len(issues) == 0
    summary = {
        "structuralValidationPass": structural_valid,
        "productionStatus": (
            "READY FOR AIRTABLE DELTA COMPARISON"
            if structural_valid
            else "FAIL CLOSED - PARSER/STRUCTURE REVIEW REQUIRED"
        ),
        "actual": {
            "Phase 1": counts.get("Phase 1", 0),
            "Phase 2": counts.get("Phase 2", 0),
            "Phase 3": counts.get("Phase 3", 0),
            "Filed / Registration": counts.get("Filed / Registration", 0),
            "Total": len(rows),
        },
        "therapeuticAreaCounts": dict(ta_counts),
        "sourcePublishedCompoundCount": 49,
        "parsedUniqueAssetLabels": unique_compounds,
        "warnings": warnings,
    }
    return summary, issues


@app.get("/extract-bms-v3", response_model=ExtractionResponse)
async def extract_bms_v3(
    source_url: str = Query(default=BMS_PIPELINE_URL),
    x_adapter_key: Optional[str] = Header(default=None),
) -> ExtractionResponse:
    _auth(x_adapter_key)
    browser = await _fetch_browser_rendered(source_url)
    rows, diagnostics = _parse_bms_rendered_text(browser.get("visibleText", ""), source_url)
    diagnostics.update({
        "retrievalTransport": browser.get("transport"),
        "retrievalMode": browser.get("retrievalMode"),
        "browserVersion": browser.get("version"),
        "browserFinalUrl": browser.get("finalUrl"),
        "browserHttpStatus": browser.get("httpStatus"),
    })
    summary, issues = _validate_bms(rows, diagnostics)
    return ExtractionResponse(
        version=BMS_ADAPTER_VERSION,
        company="Bristol Myers Squibb",
        sourceUrl=source_url,
        sourceDate=diagnostics.get("sourceDate"),
        rows=rows,
        summary=summary,
        issues=issues,
        diagnostics=diagnostics,
    )


@app.get("/debug-bms-v3")
async def debug_bms_v3(
    source_url: str = Query(default=BMS_PIPELINE_URL),
    x_adapter_key: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    _auth(x_adapter_key)
    browser = await _fetch_browser_rendered(source_url)
    rows, diagnostics = _parse_bms_rendered_text(browser.get("visibleText", ""), source_url)
    diagnostics.update({
        "retrievalTransport": browser.get("transport"),
        "retrievalMode": browser.get("retrievalMode"),
        "browserVersion": browser.get("version"),
        "browserFinalUrl": browser.get("finalUrl"),
        "browserHttpStatus": browser.get("httpStatus"),
    })
    summary, issues = _validate_bms(rows, diagnostics)
    return {
        "version": BMS_ADAPTER_VERSION,
        "summary": summary,
        "issues": issues,
        "diagnostics": diagnostics,
        "sampleRows": rows[:30],
    }
