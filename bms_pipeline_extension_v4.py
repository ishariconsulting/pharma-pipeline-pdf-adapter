"""Bristol Myers Squibb official pipeline adapter V4.

Read-only. Routes BMS browser rendering through the existing Docker Playwright
worker, which includes Chromium in the runtime image. This avoids the Python
browser worker path that can deploy without a usable Chromium executable.

V4 also keeps a short-lived in-process cache of the last successful BMS source
snapshot and retries transient Render/browser-worker gateway failures. This
prevents downstream read-only reconciliation from re-rendering the same public
source repeatedly during one validation/reconciliation cycle.

No Airtable/master-data writes are performed here.
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any, Dict, Optional

import httpx
from fastapi import Header, HTTPException, Query

from main import ExtractionResponse, _auth, _clean, app
import bms_pipeline_extension_v3 as v3

BMS_ADAPTER_VERSION = "PIPELINE_BMS_HTML_V1.3"
BMS_PIPELINE_URL = v3.BMS_PIPELINE_URL
DEFAULT_DOCKER_BROWSER_BASE = "https://pharma-browser-retrieval-docker.onrender.com"
BMS_CACHE_TTL_SECONDS = int(os.getenv("BMS_CACHE_TTL_SECONDS", "7200"))
BMS_BROWSER_ATTEMPTS = max(1, int(os.getenv("BMS_BROWSER_ATTEMPTS", "3")))

_BMS_CACHE: Dict[str, Dict[str, Any]] = {}
_BMS_CACHE_LOCK = asyncio.Lock()


def _cache_get(source_url: str) -> Optional[ExtractionResponse]:
    cached = _BMS_CACHE.get(source_url)
    if not cached:
        return None

    age = time.time() - float(cached.get("storedAt", 0.0))
    if age > BMS_CACHE_TTL_SECONDS:
        _BMS_CACHE.pop(source_url, None)
        return None

    payload = dict(cached["payload"])
    diagnostics = dict(payload.get("diagnostics") or {})
    diagnostics.update({
        "cacheHit": True,
        "cacheAgeSeconds": round(age, 1),
        "cacheTtlSeconds": BMS_CACHE_TTL_SECONDS,
    })
    payload["diagnostics"] = diagnostics
    return ExtractionResponse(**payload)


def _cache_put(source_url: str, response: ExtractionResponse) -> None:
    payload = response.model_dump()
    diagnostics = dict(payload.get("diagnostics") or {})
    diagnostics.update({
        "cacheHit": False,
        "cacheAgeSeconds": 0.0,
        "cacheTtlSeconds": BMS_CACHE_TTL_SECONDS,
    })
    payload["diagnostics"] = diagnostics
    _BMS_CACHE[source_url] = {
        "storedAt": time.time(),
        "payload": payload,
    }


async def _warm_browser_worker(client: httpx.AsyncClient, base: str) -> None:
    """Best-effort warm-up for Render services that may have spun down."""
    try:
        await client.get(
            f"{base}/health",
            timeout=httpx.Timeout(12.0, connect=8.0),
        )
    except Exception:
        # Warm-up is advisory only; the authenticated fetch loop below remains
        # the source of truth and will retry/fail closed.
        return


async def _fetch_browser_rendered_docker(url: str) -> Dict[str, Any]:
    """Fetch rendered BMS content from the Docker-backed browser worker.

    Transient 5xx/HTML gateway responses are retried because Render free-tier
    browser workers can cold-start between validation and reconciliation runs.
    """

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
    last_detail = "browser worker unavailable"

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(50.0, connect=12.0),
        follow_redirects=False,
    ) as client:
        await _warm_browser_worker(client, base)

        for attempt in range(1, BMS_BROWSER_ATTEMPTS + 1):
            try:
                response = await client.get(
                    endpoint,
                    params={"url": url, "timeout_seconds": 35.0},
                    headers={
                        "X-Browser-Key": key,
                        "Accept": "application/json",
                    },
                )
            except httpx.TimeoutException:
                last_detail = "browser retrieval timed out"
                response = None
            except httpx.HTTPError as exc:
                last_detail = f"browser HTTP transport failed: {type(exc).__name__}"
                response = None

            if response is not None and response.status_code < 400:
                try:
                    payload = response.json()
                except Exception as exc:
                    last_detail = "browser worker returned invalid JSON"
                else:
                    text = _clean(payload.get("visibleText", ""))
                    if len(text) >= 2000:
                        payload["selectedBrowserWorker"] = base
                        payload["browserAttempt"] = attempt
                        return payload
                    last_detail = "BMS rendered page remained too sparse"

            elif response is not None:
                content_type = (response.headers.get("content-type") or "").lower()
                try:
                    detail = response.json().get("detail")
                except Exception:
                    detail = response.text[:500]

                last_detail = f"HTTP {response.status_code}: {detail}"

                # 401/403 are configuration/source-policy failures, not cold
                # starts. Fail immediately rather than masking them as retries.
                if response.status_code in {401, 403}:
                    raise HTTPException(
                        status_code=502,
                        detail=(
                            f"BMS Docker browser worker failed "
                            f"({response.status_code}: {detail})"
                        ),
                    )

                # A Render gateway/cold-start failure is often returned as an
                # HTML 502/503 page instead of the worker's JSON contract.
                if response.status_code not in {500, 502, 503, 504} and "text/html" not in content_type:
                    raise HTTPException(
                        status_code=502,
                        detail=(
                            f"BMS Docker browser worker failed "
                            f"({response.status_code}: {detail})"
                        ),
                    )

            if attempt < BMS_BROWSER_ATTEMPTS:
                await asyncio.sleep(1.5 * attempt)
                await _warm_browser_worker(client, base)

    raise HTTPException(
        status_code=502,
        detail=(
            f"BMS Docker browser worker failed after {BMS_BROWSER_ATTEMPTS} "
            f"attempt(s): {last_detail}"
        ),
    )


async def _extract_bms_response(source_url: str) -> ExtractionResponse:
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
        "browserAttempt": browser.get("browserAttempt"),
        "cacheHit": False,
        "cacheAgeSeconds": 0.0,
        "cacheTtlSeconds": BMS_CACHE_TTL_SECONDS,
    })

    summary, issues = v3._validate_bms(rows, diagnostics)

    response = ExtractionResponse(
        version=BMS_ADAPTER_VERSION,
        company="Bristol Myers Squibb",
        sourceUrl=source_url,
        sourceDate=diagnostics.get("sourceDate"),
        rows=rows,
        summary=summary,
        issues=issues,
        diagnostics=diagnostics,
    )

    # Cache only structurally valid, issue-free snapshots. Bad source states
    # must never become a reusable downstream snapshot.
    if summary.get("structuralValidationPass") is True and not issues:
        _cache_put(source_url, response)

    return response


@app.get("/extract-bms-v4", response_model=ExtractionResponse)
async def extract_bms_v4(
    source_url: str = Query(default=BMS_PIPELINE_URL),
    refresh: bool = Query(default=False),
    x_adapter_key: Optional[str] = Header(default=None),
) -> ExtractionResponse:
    _auth(x_adapter_key)

    if not refresh:
        cached = _cache_get(source_url)
        if cached is not None:
            return cached

    # Prevent concurrent callers from waking/rendering the same source twice.
    async with _BMS_CACHE_LOCK:
        if not refresh:
            cached = _cache_get(source_url)
            if cached is not None:
                return cached

        return await _extract_bms_response(source_url)


@app.get("/debug-bms-v4")
async def debug_bms_v4(
    source_url: str = Query(default=BMS_PIPELINE_URL),
    refresh: bool = Query(default=False),
    x_adapter_key: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    _auth(x_adapter_key)

    response = await extract_bms_v4(
        source_url=source_url,
        refresh=refresh,
        x_adapter_key=x_adapter_key,
    )

    payload = response.model_dump()
    return {
        "version": payload.get("version"),
        "summary": payload.get("summary"),
        "issues": payload.get("issues"),
        "diagnostics": payload.get("diagnostics"),
        "sampleRows": (payload.get("rows") or [])[:30],
    }
