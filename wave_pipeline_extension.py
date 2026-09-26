"""Read-only Wave Life Sciences graphical pipeline adapter.

Wave's official R&D pipeline encodes development status in rendered bar geometry
rather than server-side structured rows. This adapter retrieves the public page
through the isolated browser worker, reads the rendered layout, and emits only
named WVE programmes. It preserves Wave's broad source stage (Discovery,
IND/CTA Enabling Studies, Clinical) and deliberately does NOT invent a numeric
clinical phase. Exact phase remains a separate ClinicalTrials.gov / trial-layer
fact.

No Airtable or master-data writes.
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional

import httpx
from fastapi import Header, HTTPException, Query
from pydantic import BaseModel

from main import _auth, app
from html_fetch_extension import _assert_public_http_url


ADAPTER_PROFILE = "PIPELINE_WAVE_BROWSER_LAYOUT_V1"
ROUTE_VERSION = "WAVE_BROWSER_LAYOUT_PIPELINE_V1.0_READ_ONLY"
DEFAULT_SOURCE_URL = "https://wavelifesciences.com/pipeline/research-and-development/"
MIN_NAMED_ROWS = 4
MAX_NAMED_ROWS = 20
EXPECTED_STAGE_HEADERS = ["Discovery", "IND / CTA Enabling Studies", "Clinical"]


class WavePipelineResponse(BaseModel):
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
    diagnostics: Dict[str, Any]
    guardrails: Dict[str, Any]


def clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _browser_config() -> tuple[str, str]:
    return (
        os.getenv("BROWSER_FETCH_BASE_URL", "").strip().rstrip("/"),
        os.getenv("BROWSER_FETCH_KEY", "").strip(),
    )


async def _fetch_layout(source_url: str, timeout_seconds: float) -> Dict[str, Any]:
    await _assert_public_http_url(source_url)
    base, key = _browser_config()
    if not base or not key:
        raise HTTPException(status_code=502, detail="Wave browser retrieval is required but not configured")

    endpoint = f"{base}/fetch/browser"
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
                    "include_layout": "true",
                },
                headers={
                    "X-Browser-Key": key,
                    "Accept": "application/json",
                },
            )
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="Wave browser retrieval timed out") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Wave browser retrieval failed: {exc}") from exc

    try:
        payload = response.json()
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Wave browser retrieval returned invalid JSON") from exc

    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"Wave browser retrieval failed: HTTP {response.status_code}; {clean(payload.get('detail'))}",
        )

    if not isinstance(payload.get("layoutTextNodes"), list):
        raise HTTPException(status_code=502, detail="Wave browser layout payload is missing layoutTextNodes")

    return payload


def _header_centres(nodes: List[Dict[str, Any]]) -> Dict[str, float]:
    centres: Dict[str, float] = {}
    for label in EXPECTED_STAGE_HEADERS:
        candidates = [n for n in nodes if clean(n.get("text")).lower() == label.lower()]
        if not candidates:
            continue
        node = min(candidates, key=lambda n: float(n.get("y") or 999999))
        centres[label] = float(node.get("x") or 0) + float(node.get("width") or 0) / 2.0
    return centres


def _stage_from_bar(bar: Dict[str, Any], centres: Dict[str, float]) -> str:
    if len(centres) != len(EXPECTED_STAGE_HEADERS):
        return ""
    right_edge = float(bar.get("x") or 0) + float(bar.get("width") or 0)
    ordered = sorted(((centres[label], label) for label in EXPECTED_STAGE_HEADERS), key=lambda x: x[0])
    reached = ""
    for centre, label in ordered:
        if right_edge + 2.0 >= centre:
            reached = label
    return reached


def _nearest(
    nodes: List[Dict[str, Any]],
    y: float,
    predicate,
    max_distance: float,
    require_after: bool = False,
) -> Optional[Dict[str, Any]]:
    candidates = []
    for node in nodes:
        if not predicate(node):
            continue
        node_y = float(node.get("y") or 0)
        if require_after and node_y + 1 < y:
            continue
        distance = abs(node_y - y)
        if distance <= max_distance:
            candidates.append((distance, node_y, node))
    if not candidates:
        return None
    candidates.sort(key=lambda x: (x[0], x[1]))
    return candidates[0][2]


def _platform_for_asset(nodes: List[Dict[str, Any]], asset_y: float) -> str:
    candidates = []
    for node in nodes:
        if "pipeline-title" not in clean(node.get("className")):
            continue
        text = clean(node.get("text"))
        if not text:
            continue
        node_y = float(node.get("y") or 0)
        if node_y <= asset_y and asset_y - node_y <= 180:
            candidates.append((asset_y - node_y, text))
    return min(candidates, key=lambda x: x[0])[1] if candidates else ""


def parse_wave_layout(payload: Dict[str, Any], company: str) -> tuple[List[Dict[str, Any]], Dict[str, Any], List[str]]:
    nodes = payload.get("layoutTextNodes") or []
    headers = _header_centres(nodes)
    issues: List[str] = []

    missing_headers = [x for x in EXPECTED_STAGE_HEADERS if x not in headers]
    if missing_headers:
        issues.append("missing stage headers: " + ", ".join(missing_headers))

    asset_nodes = []
    for node in nodes:
        text = clean(node.get("text"))
        if re.fullmatch(r"WVE-[A-Z0-9]+(?:\s*\(GalNAc\))?", text, flags=re.I):
            asset_nodes.append(node)

    rows: List[Dict[str, Any]] = []
    seen = set()
    for asset_node in sorted(asset_nodes, key=lambda n: float(n.get("y") or 0)):
        source_asset_label = clean(asset_node.get("text"))
        code_match = re.search(r"\bWVE-[A-Z0-9]+\b", source_asset_label, flags=re.I)
        if not code_match:
            continue
        code = code_match.group(0).upper()
        if code in seen:
            continue
        seen.add(code)
        asset_y = float(asset_node.get("y") or 0)

        indication_node = _nearest(
            nodes,
            asset_y,
            lambda n: clean(n.get("className")) == "sub-title" and bool(clean(n.get("text"))),
            42.0,
            require_after=True,
        )
        bar_node = _nearest(
            nodes,
            asset_y,
            lambda n: "rounded-block-stat" in clean(n.get("className")),
            35.0,
        )
        population_node = _nearest(
            nodes,
            asset_y,
            lambda n: (
                clean(n.get("tag")).lower() == "p"
                and "population" in clean(n.get("parentClassName")).lower()
                and bool(clean(n.get("text")))
            ),
            45.0,
        )

        indication = clean(indication_node.get("text")) if indication_node else ""
        stage = _stage_from_bar(bar_node or {}, headers) if bar_node else ""
        population = clean(population_node.get("text")) if population_node else ""
        platform = _platform_for_asset(nodes, asset_y)

        row_issues = []
        if not indication:
            row_issues.append("missing indication")
        if not stage:
            row_issues.append("missing/unknown source stage")
        if row_issues:
            issues.append(f"{code}: " + ", ".join(row_issues))

        rows.append({
            "company": company,
            "sourceFamily": "Company Pipeline",
            "sourceRecordId": f"{code}|{indication or 'UNRESOLVED'}",
            "sourceUrl": clean(payload.get("finalUrl")) or DEFAULT_SOURCE_URL,
            "asset": code,
            "molecule": "",
            "developmentCode": code,
            "brand": "",
            "indication": indication,
            "phase": "",
            "phaseEvidence": "SOURCE_GRAPHICAL_STAGE_ONLY",
            "sourceStage": stage,
            "programStatus": "Active",
            "sponsorOwner": company,
            "partners": [],
            "study": "",
            "trialIds": [],
            "therapeuticArea": "",
            "platform": platform,
            "patientPopulation": population,
            "sourceAssetLabel": source_asset_label,
            "sourceStageBarClass": clean((bar_node or {}).get("className")),
            "sourceStageBarRight": (
                round(float((bar_node or {}).get("x") or 0) + float((bar_node or {}).get("width") or 0), 1)
                if bar_node else None
            ),
            "parserMethod": "WAVE_RENDERED_LAYOUT_GEOMETRY",
            "sourceAdapter": ADAPTER_PROFILE,
        })

    if len(rows) < MIN_NAMED_ROWS:
        issues.append(f"too few named WVE rows: {len(rows)} < {MIN_NAMED_ROWS}")
    if len(rows) > MAX_NAMED_ROWS:
        issues.append(f"unexpectedly many named WVE rows: {len(rows)} > {MAX_NAMED_ROWS}")
    if len(rows) != len(seen):
        issues.append("duplicate named WVE rows detected")

    stage_counts: Dict[str, int] = {}
    for row in rows:
        stage = row.get("sourceStage") or "UNKNOWN"
        stage_counts[stage] = stage_counts.get(stage, 0) + 1

    diagnostics = {
        "browserVersion": payload.get("version"),
        "httpStatus": payload.get("httpStatus"),
        "visibleLineCount": len(payload.get("visibleLines") or []),
        "layoutNodeCount": len(nodes),
        "stageHeaderCentres": {k: round(v, 1) for k, v in headers.items()},
        "namedAssetCount": len(rows),
        "namedAssets": [r["developmentCode"] for r in rows],
        "stageCounts": stage_counts,
        "phaseSpecificity": "BROAD_STAGE_ONLY",
        "exactClinicalPhaseFromCompanyPage": False,
        "unnamedResearchRowsIntentionallyExcluded": True,
        "writes": 0,
    }
    return rows, diagnostics, issues


async def extract_wave_pipeline(
    company: str = "Wave Life Sciences",
    source_url: str = DEFAULT_SOURCE_URL,
    timeout_seconds: float = 35.0,
) -> WavePipelineResponse:
    payload = await _fetch_layout(source_url, timeout_seconds)
    final_url = clean(payload.get("finalUrl")) or source_url
    await _assert_public_http_url(final_url)

    rows, diagnostics, issues = parse_wave_layout(payload, company)
    ready = not issues

    return WavePipelineResponse(
        version=ADAPTER_PROFILE,
        routeVersion=ROUTE_VERSION,
        company=company,
        sourceUrl=source_url,
        finalUrl=final_url,
        retrievalMode="BROWSER_REQUIRED",
        readOnly=True,
        readyForDiscovery=ready,
        rowCount=len(rows),
        rows=rows,
        summary={
            "structuralValidationPass": ready,
            "actual": {"NamedProgrammes": len(rows)},
            "productionStatus": (
                "READY FOR SOURCE-SPECIFIC STAGE MONITORING"
                if ready else
                "FAIL CLOSED - WAVE LAYOUT REVIEW REQUIRED"
            ),
            "selectedMethod": "WAVE_RENDERED_LAYOUT_GEOMETRY",
            "phasePolicy": "DO_NOT_INFER_NUMERIC_PHASE_FROM_GRAPHICAL_STAGE",
            "writeMode": "READ_ONLY",
        },
        issues=[{"issue": issue} for issue in issues],
        diagnostics=diagnostics,
        guardrails={
            "airtableWrites": False,
            "portfolioWrites": False,
            "masterDataWrites": False,
            "publicHttpOnly": True,
            "browserRequired": True,
            "fuzzyIdentityResolution": False,
            "numericPhaseInferenceFromStage": False,
            "unnamedProgrammePromotion": False,
        },
    )


@app.get("/extract/wave/browser-layout-pipeline/health")
async def wave_health() -> Dict[str, Any]:
    return {
        "ok": True,
        "version": ADAPTER_PROFILE,
        "routeVersion": ROUTE_VERSION,
        "readOnly": True,
        "phasePolicy": "BROAD_STAGE_ONLY",
    }


@app.get("/extract/wave/browser-layout-pipeline", response_model=WavePipelineResponse)
async def wave_route(
    company: str = Query(default="Wave Life Sciences", min_length=1, max_length=160),
    source_url: str = Query(default=DEFAULT_SOURCE_URL, min_length=8),
    timeout_seconds: float = Query(default=35.0, ge=5.0, le=35.0),
    x_adapter_key: Optional[str] = Header(default=None),
) -> WavePipelineResponse:
    _auth(x_adapter_key)
    return await extract_wave_pipeline(company, source_url, timeout_seconds)
