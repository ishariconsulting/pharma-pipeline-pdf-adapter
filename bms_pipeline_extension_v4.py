"""Bristol Myers Squibb official pipeline adapter V4.

Read-only. Routes BMS browser rendering through the existing Docker Playwright
worker, which includes Chromium in the runtime image. This avoids the Python
browser worker path that can deploy without a usable Chromium executable.

No Airtable/master-data writes are performed here.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

import httpx
from fastapi import Header, HTTPException, Query

from main import ExtractionResponse, _auth, _clean, app
import bms_pipeline_extension_v3 as v3

BMS_ADAPTER_VERSION = "PIPELINE_BMS_HTML_V1.3"
BMS_PIPELINE_URL = v3.BMS_PIPELINE_URL
DEFAULT_DOCKER_BROWSER_BASE = "https://pharma-browser-retrieval-docker.onrender.com"


async def _fetch_browser_rendered_docker(url: str) -> Dict[str, Any]:
    """Fetch rendered BMS content from the Docker-backed browser worker."""

    base = (
        os.getenv("BMS_BROWSER_FETCH_BASE_URL", "").strip().rstrip("/")
        or DEFAULT_DOCKER_BROWSER_BASE
    )
    key = os.getenv("BROWSER_FETCH_KEY", "").strip()

    if not key:
        raise HTTPException(
            status_code=502,
            detail="BMS browser retrieval key is not configured",
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
                headers={
                    "X-Browser-Key": key,
                    "Accept": "application/json",
                },
            )
    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=504,
            detail="BMS Docker browser retrieval timed out",
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"BMS Docker browser retrieval failed: {type(exc).__name__}",
        ) from exc

    if response.status_code >= 400:
        try:
            detail = response.json().get("detail")
        except Exception:
            detail = response.text[:500]
        raise HTTPException(
            status_code=502,
            detail=(
                f"BMS Docker browser worker failed "
                f"({response.status_code}: {detail})"
            ),
        )

    try:
        payload = response.json()
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="BMS Docker browser worker returned invalid JSON",
        ) from exc

    text = _clean(payload.get("visibleText", ""))
    if len(text) < 2000:
        raise HTTPException(
            status_code=502,
            detail="BMS rendered page remained too sparse",
        )

    payload["selectedBrowserWorker"] = base
    return payload


@app.get("/extract-bms-v4", response_model=ExtractionResponse)
async def extract_bms_v4(
    source_url: str = Query(default=BMS_PIPELINE_URL),
    x_adapter_key: Optional[str] = Header(default=None),
) -> ExtractionResponse:
    _auth(x_adapter_key)

    browser = await _fetch_browser_rendered_docker(source_url)
    rows, diagnostics = v3._parse_bms_rendered_text(
        browser.get("visibleText", ""),
        source_url,
    )

    # Stamp the current adapter version onto every emitted row.
    for row in rows:
        row["sourceAdapter"] = BMS_ADAPTER_VERSION

    diagnostics.update({
        "parser": BMS_ADAPTER_VERSION,
        "retrievalTransport": browser.get("transport"),
        "retrievalMode": browser.get("retrievalMode"),
        "browserVersion": browser.get("version"),
        "browserFinalUrl": browser.get("finalUrl"),
        "browserHttpStatus": browser.get("httpStatus"),
        "browserWorkerBase": browser.get("selectedBrowserWorker"),
    })

    summary, issues = v3._validate_bms(rows, diagnostics)

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


@app.get("/debug-bms-v4")
async def debug_bms_v4(
    source_url: str = Query(default=BMS_PIPELINE_URL),
    x_adapter_key: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    _auth(x_adapter_key)

    browser = await _fetch_browser_rendered_docker(source_url)
    rows, diagnostics = v3._parse_bms_rendered_text(
        browser.get("visibleText", ""),
        source_url,
    )

    for row in rows:
        row["sourceAdapter"] = BMS_ADAPTER_VERSION

    diagnostics.update({
        "parser": BMS_ADAPTER_VERSION,
        "retrievalTransport": browser.get("transport"),
        "retrievalMode": browser.get("retrievalMode"),
        "browserVersion": browser.get("version"),
        "browserFinalUrl": browser.get("finalUrl"),
        "browserHttpStatus": browser.get("httpStatus"),
        "browserWorkerBase": browser.get("selectedBrowserWorker"),
    })

    summary, issues = v3._validate_bms(rows, diagnostics)

    return {
        "version": BMS_ADAPTER_VERSION,
        "summary": summary,
        "issues": issues,
        "diagnostics": diagnostics,
        "sampleRows": rows[:30],
    }
