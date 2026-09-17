"""BMS official pipeline adapter V2 using the existing browser retrieval worker.

Read-only. The public BMS pipeline is interactive and its programme rows are not
present in the server-rendered HTML returned by a normal HTTP client. V2 asks the
existing browser worker for rendered DOM innerText with line boundaries preserved,
then applies deterministic row parsing and the existing BMS validation contract.
"""

from __future__ import annotations

import os
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

import httpx
from fastapi import Header, HTTPException, Query

from main import ExtractionResponse, _auth, _clean, _norm, app
from bms_pipeline_extension import (
    BMS_PIPELINE_URL,
    BMS_TAS,
    PHASE_MARKER_RE,
    _clean_asset,
    _extract_dev_code,
    _extract_source_date,
    _is_noise,
    _parse_phase,
    _validate_bms,
)

BMS_ADAPTER_VERSION_V2 = "PIPELINE_BMS_RENDERED_V2.0"


async def _fetch_rendered_lines(
    source_url: str,
    timeout_seconds: float = 35.0,
) -> Tuple[List[str], Dict[str, Any]]:
    base = os.getenv("BROWSER_FETCH_BASE_URL", "").strip().rstrip("/")
    key = os.getenv("BROWSER_FETCH_KEY", "").strip()

    if not base or not key:
        raise HTTPException(
            status_code=502,
            detail="BMS rendered parser requires the existing browser worker configuration",
        )

    endpoint = f"{base}/extract/bms-rendered-text"

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds + 15.0, connect=12.0),
            follow_redirects=False,
        ) as client:
            response = await client.get(
                endpoint,
                params={
                    "url": source_url,
                    "timeout_seconds": timeout_seconds,
                },
                headers={"X-Browser-Key": key},
            )
    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=504,
            detail="BMS browser worker timed out",
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"BMS browser worker transport failed: {type(exc).__name__}",
        ) from exc

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
        raise HTTPException(
            status_code=502,
            detail="BMS browser worker returned invalid JSON",
        ) from exc

    lines = payload.get("lines")
    if not isinstance(lines, list):
        raise HTTPException(
            status_code=502,
            detail="BMS browser worker response did not include rendered lines",
        )

    cleaned = [_clean(x) for x in lines if _clean(x)]

    return cleaned, {
        "browserVersion": payload.get("version"),
        "browserFinalUrl": payload.get("finalUrl"),
        "browserHttpStatus": payload.get("httpStatus"),
        "browserLineCount": payload.get("lineCount"),
        "browserPhaseMarkerCount": payload.get("phaseMarkerCount"),
    }


def _parse_bms_rendered_lines(
    lines: List[str],
    source_url: str,
    browser_diag: Optional[Dict[str, Any]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
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

        # Keep the LAST recognised TA in the block. For the first programme row,
        # this safely ignores the TA filter options that appear before the table.
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
                "blockTail": meaningful[-15:],
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
                "blockTail": meaningful[-15:],
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
            "sourceAdapter": BMS_ADAPTER_VERSION_V2,
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
        count - 1
        for count in Counter(fingerprints).values()
        if count > 1
    )

    phase_counts = Counter(r["phase"] for r in rows)
    ta_counts = Counter(r["sourceTherapeuticArea"] for r in rows)
    unique_compounds = len({_norm(r["asset"]) for r in rows if r["asset"]})

    diagnostics = {
        "parser": BMS_ADAPTER_VERSION_V2,
        "retrievalMode": "PLAYWRIGHT_RENDERED_INNERTEXT_LINES",
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
        "browser": browser_diag or {},
        "structuralNote": (
            "BMS rows are parsed from rendered DOM innerText because the official "
            "interactive programme table is not present in normal server HTML. "
            "No source data is written by this adapter."
        ),
    }

    return rows, diagnostics


@app.get("/extract-bms-v2", response_model=ExtractionResponse)
async def extract_bms_v2(
    source_url: str = Query(default=BMS_PIPELINE_URL),
    x_adapter_key: Optional[str] = Header(default=None),
) -> ExtractionResponse:
    _auth(x_adapter_key)
    lines, browser_diag = await _fetch_rendered_lines(source_url)
    rows, diagnostics = _parse_bms_rendered_lines(
        lines,
        source_url,
        browser_diag,
    )
    summary, issues = _validate_bms(rows, diagnostics)

    return ExtractionResponse(
        version=BMS_ADAPTER_VERSION_V2,
        company="Bristol Myers Squibb",
        sourceUrl=source_url,
        sourceDate=diagnostics.get("sourceDate"),
        rows=rows,
        summary=summary,
        issues=issues,
        diagnostics=diagnostics,
    )


@app.get("/debug-bms-v2")
async def debug_bms_v2(
    source_url: str = Query(default=BMS_PIPELINE_URL),
    x_adapter_key: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    _auth(x_adapter_key)
    lines, browser_diag = await _fetch_rendered_lines(source_url)
    rows, diagnostics = _parse_bms_rendered_lines(
        lines,
        source_url,
        browser_diag,
    )
    summary, issues = _validate_bms(rows, diagnostics)

    return {
        "version": BMS_ADAPTER_VERSION_V2,
        "summary": summary,
        "issues": issues,
        "diagnostics": diagnostics,
        "sampleLines": lines[:250],
        "sampleRows": rows[:30],
    }
