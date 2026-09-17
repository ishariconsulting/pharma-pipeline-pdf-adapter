"""Bristol Myers Squibb official pipeline adapter.

Additive, read-only extension. It parses the official BMS pipeline page into the
same source-row contract used by the existing recurring delta engine.

No Airtable/master-data writes are performed here.
"""

from __future__ import annotations

import html as html_lib
import re
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

from fastapi import Header, Query

from main import ExtractionResponse, _auth, _clean, _download_html, _norm, app

BMS_ADAPTER_VERSION = "PIPELINE_BMS_HTML_V1.0"
BMS_PIPELINE_URL = "https://www.bms.com/research-and-development/pipeline.html"

BMS_TAS = {
    "cardiovascular": "Cardiovascular",
    "hematology": "Hematology",
    "immunology": "Immunology",
    "neuroscience": "Neuroscience",
    "oncology": "Oncology",
}

PHASE_MARKER_RE = re.compile(
    r"^(?:Phase\s*([123])\s+in\s+Progress|Registration(?:\s*\(([^)]*)\))?)$",
    re.I,
)
BMS_CODE_RE = re.compile(r"\bBMS[-\u2010-\u2015 ]?\d{5,9}\b", re.I)

BOILERPLATE = {
    "active filters",
    "brand compound name",
    "therapeutic area",
    "focus area",
    "indication",
    "phase",
    "new molecular entity lead indication",
    "partner run study",
    "select all",
    "clear all",
    "search",
    "nme",
    "lcm",
}


def _bms_lines(raw_html: str) -> List[str]:
    value = html_lib.unescape(raw_html or "")
    value = re.sub(r"<!--[\s\S]*?-->", "\n", value)
    value = re.sub(r"<script\b[\s\S]*?</script>", "\n", value, flags=re.I)
    value = re.sub(r"<style\b[\s\S]*?</style>", "\n", value, flags=re.I)
    value = re.sub(r"<noscript\b[\s\S]*?</noscript>", "\n", value, flags=re.I)
    value = re.sub(r"<svg\b[\s\S]*?</svg>", "\n", value, flags=re.I)
    value = re.sub(
        r"</?(?:div|p|li|section|article|tr|td|th|h1|h2|h3|h4|h5|h6|span|a|button|label|option)\b[^>]*>",
        "\n",
        value,
        flags=re.I,
    )
    value = re.sub(r"<(?:br|hr)\b[^>]*>", "\n", value, flags=re.I)
    value = re.sub(r"<[^>]+>", " ", value)
    value = value.replace("\r", "\n")

    out: List[str] = []
    for raw in re.split(r"\n+", value):
        line = re.sub(r"\s+", " ", raw).strip()
        if not line or "{{" in line or "}}" in line:
            continue
        out.append(line)
    return out


def _is_noise(line: str) -> bool:
    n = _norm(line)
    if not n or n in BOILERPLATE or n in {"1", "2", "3"}:
        return True
    if re.fullmatch(r"\(\d+\)", line.strip()):
        return True
    if line.strip() in {"[Select]", "[Input]", "[Button: Search]"}:
        return True
    return False


def _clean_asset(value: str) -> str:
    value = _clean(value)
    value = value.replace("^{®}", "®").replace("^{™}", "™")
    return value.replace("∗", "").strip()


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


def _parse_phase(marker: str) -> Tuple[str, str]:
    match = PHASE_MARKER_RE.match(_clean(marker))
    if not match:
        return "", ""
    if match.group(1):
        return f"Phase {match.group(1)}", ""
    return "Filed / Registration", _clean(match.group(2) or "")


def _extract_source_date(lines: List[str]) -> Optional[str]:
    joined = " | ".join(lines[:400])
    match = re.search(
        r"\bAs\s+of\s+([A-Z][a-z]+\s+\d{1,2},\s+\d{4})\b",
        joined,
        re.I,
    )
    return _clean(match.group(1)) if match else None


def _parse_bms_html(
    raw_html: str,
    source_url: str,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    lines = _bms_lines(raw_html)
    source_date = _extract_source_date(lines)

    phase_positions: List[Tuple[int, str]] = []
    for idx, line in enumerate(lines):
        if PHASE_MARKER_RE.match(_clean(line)):
            phase_positions.append((idx, line))

    rows: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []
    prev_phase_idx = -1

    for ordinal, (phase_idx, marker) in enumerate(phase_positions, start=1):
        block = lines[prev_phase_idx + 1 : phase_idx]
        prev_phase_idx = phase_idx
        meaningful = [_clean(x) for x in block if not _is_noise(x)]

        ta_pos = -1
        ta_name = ""
        for i, line in enumerate(meaningful):
            mapped = BMS_TAS.get(_norm(line))
            if mapped:
                ta_pos = i
                ta_name = mapped

        if ta_pos <= 0:
            rejected.append({
                "sourceCardOrdinal": ordinal,
                "phaseMarker": marker,
                "reason": "THERAPEUTIC_AREA_NOT_FOUND",
                "blockTail": meaningful[-12:],
            })
            continue

        asset = _clean_asset(meaningful[ta_pos - 1])
        after_ta = [x for x in meaningful[ta_pos + 1 :] if not _is_noise(x)]
        after_ta = [
            x for x in after_ta
            if _norm(x) not in BMS_TAS and not PHASE_MARKER_RE.match(_clean(x))
        ]

        if not asset or not after_ta:
            rejected.append({
                "sourceCardOrdinal": ordinal,
                "phaseMarker": marker,
                "reason": "ASSET_OR_INDICATION_MISSING",
                "asset": asset,
                "therapeuticArea": ta_name,
                "blockTail": meaningful[-12:],
            })
            continue

        indication = _clean(after_ta[-1]).replace("∗", "").strip()
        focus_area = _clean(after_ta[-2]) if len(after_ta) >= 2 else ""
        phase, registration_geo = _parse_phase(marker)

        if not phase:
            rejected.append({
                "sourceCardOrdinal": ordinal,
                "reason": "PHASE_UNRESOLVED",
                "marker": marker,
                "asset": asset,
            })
            continue

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
            _norm(r["asset"]),
            _norm(r["indication"]),
            _norm(r["phase"]),
            _norm(r.get("sourceFocusArea", "")),
            _norm(r.get("registrationGeography", "")),
        )
        for r in rows
    ]
    exact_duplicate_count = sum(
        count - 1 for count in Counter(fingerprints).values() if count > 1
    )

    phase_counts = Counter(r["phase"] for r in rows)
    ta_counts = Counter(r["sourceTherapeuticArea"] for r in rows)
    unique_compounds = len({_norm(r["asset"]) for r in rows if r["asset"]})

    diagnostics = {
        "parser": BMS_ADAPTER_VERSION,
        "sourceDate": source_date,
        "sourceLineCount": len(lines),
        "phaseMarkersFound": len(phase_positions),
        "parsedRows": len(rows),
        "rejectedRows": len(rejected),
        "rejectedDetails": rejected[:30],
        "exactDuplicates": exact_duplicate_count,
        "phaseCounts": dict(phase_counts),
        "therapeuticAreaCounts": dict(ta_counts),
        "uniqueCompoundLabels": unique_compounds,
        "sourcePublishedCompoundCount": 49,
        "structuralNote": (
            "BMS is programme-grain: one compound may appear in multiple indications "
            "and phases. The source's 49-compound headline is therefore not expected "
            "to equal the number of returned programme rows."
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
        issues.append({
            "issue": "Rows missing core fields",
            "count": len(missing_core),
            "sample": missing_core[:20],
        })

    invalid_phases = [
        {
            "asset": r.get("asset", ""),
            "phase": r.get("phase", ""),
            "sourceCardOrdinal": r.get("sourceCardOrdinal"),
        }
        for r in rows
        if r.get("phase") not in allowed_phases
    ]
    if invalid_phases:
        issues.append({
            "issue": "Rows contain unsupported phase values",
            "count": len(invalid_phases),
            "sample": invalid_phases[:20],
        })

    rejected_rows = int(diagnostics.get("rejectedRows", 0) or 0)
    if rejected_rows:
        issues.append({
            "issue": "One or more phase-card blocks failed extraction",
            "count": rejected_rows,
        })

    exact_duplicates = int(diagnostics.get("exactDuplicates", 0) or 0)
    if exact_duplicates:
        issues.append({
            "issue": "Exact BMS source programme rows are duplicated",
            "count": exact_duplicates,
        })

    if len(rows) < 50 or len(rows) > 180:
        issues.append({
            "issue": "Programme count outside structural sanity bounds",
            "actualTotal": len(rows),
            "allowedRange": [50, 180],
        })

    counts = Counter(r.get("phase", "") for r in rows)
    for phase in ["Phase 1", "Phase 2", "Phase 3"]:
        if counts.get(phase, 0) <= 0:
            issues.append({
                "issue": "Major development phase unexpectedly empty",
                "phase": phase,
            })

    ta_counts = Counter(r.get("sourceTherapeuticArea", "") for r in rows)
    missing_tas = [
        display for display in BMS_TAS.values() if ta_counts.get(display, 0) <= 0
    ]
    if missing_tas:
        issues.append({
            "issue": "Expected BMS therapeutic area absent from parsed source",
            "therapeuticAreas": missing_tas,
        })

    unique_compounds = int(diagnostics.get("uniqueCompoundLabels", 0) or 0)
    if unique_compounds != 49:
        warnings.append({
            "warning": (
                "Parsed unique asset labels do not equal the BMS 49-compound headline. "
                "Brand/combination naming can make this non-fatal; reconcile before changing the parser."
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


@app.get("/extract-bms", response_model=ExtractionResponse)
async def extract_bms(
    source_url: str = Query(default=BMS_PIPELINE_URL),
    x_adapter_key: Optional[str] = Header(default=None),
) -> ExtractionResponse:
    _auth(x_adapter_key)
    raw_html = await _download_html(source_url)
    rows, diagnostics = _parse_bms_html(raw_html, source_url)
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


@app.get("/debug-bms")
async def debug_bms(
    source_url: str = Query(default=BMS_PIPELINE_URL),
    x_adapter_key: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    _auth(x_adapter_key)
    raw_html = await _download_html(source_url)
    rows, diagnostics = _parse_bms_html(raw_html, source_url)
    summary, issues = _validate_bms(rows, diagnostics)
    return {
        "version": BMS_ADAPTER_VERSION,
        "summary": summary,
        "issues": issues,
        "diagnostics": diagnostics,
        "sampleRows": rows[:25],
    }
