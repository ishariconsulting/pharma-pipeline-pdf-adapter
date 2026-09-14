"""Additive retrieval router for HTML sources.

The existing /fetch/html endpoint is intentionally left unchanged. This module
adds /fetch/routed-html, which tries normal HTTP once and only escalates to the
separate browser worker for known transport failures or sparse server HTML.
It is read-only and fail-closed.
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, Optional

import httpx
from fastapi import Header, HTTPException, Query
from pydantic import BaseModel

from main import _auth, app
from html_fetch_extension import HtmlFetchResponse, _fetch_public_html


ROUTER_VERSION = "RETRIEVAL_ROUTER_V1.0"
MIN_USABLE_VISIBLE_TEXT = 800
ROUTABLE_SOURCE_STATUSES = {403, 408, 429}


class RoutedHtmlFetchResponse(BaseModel):
    version: str
    sourceUrl: str
    finalUrl: str
    httpStatus: int
    contentType: Optional[str] = None
    bodyBytes: int
    title: Optional[str] = None
    metaDescription: Optional[str] = None
    visibleTextLength: int
    visibleText: str
    headings: list[dict[str, Any]]
    anchors: list[dict[str, str]]
    transport: str
    retrievalMode: str
    routingReason: str
    directHttpStatus: Optional[int] = None
    directVersion: Optional[str] = None
    browserVersion: Optional[str] = None


def _source_status_from_exception(exc: HTTPException) -> Optional[int]:
    detail = str(exc.detail or "")
    match = re.search(r"Source returned HTTP\s+(\d{3})", detail, re.I)
    return int(match.group(1)) if match else None


def _direct_payload(result: HtmlFetchResponse) -> Dict[str, Any]:
    payload = result.model_dump()
    payload.update(
        {
            "version": ROUTER_VERSION,
            "transport": "DIRECT_HTTP",
            "retrievalMode": "DIRECT",
            "routingReason": "DIRECT_HTTP_USABLE",
            "directHttpStatus": result.httpStatus,
            "directVersion": result.version,
            "browserVersion": None,
        }
    )
    return payload


async def _browser_payload(
    *,
    url: str,
    timeout_seconds: float,
    reason: str,
    direct_status: Optional[int],
    direct_version: Optional[str],
) -> Dict[str, Any]:
    base = os.getenv("BROWSER_FETCH_BASE_URL", "").strip().rstrip("/")
    key = os.getenv("BROWSER_FETCH_KEY", "").strip()
    if not base or not key:
        raise HTTPException(
            status_code=502,
            detail=f"{reason}; browser fallback is not configured",
        )

    endpoint = f"{base}/fetch/browser"
    timeout = httpx.Timeout(timeout_seconds + 10.0, connect=12.0)
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            response = await client.get(
                endpoint,
                params={"url": url, "timeout_seconds": timeout_seconds},
                headers={"X-Browser-Key": key},
            )
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail=f"{reason}; browser fallback timed out") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"{reason}; browser fallback transport failed") from exc

    if response.status_code >= 400:
        try:
            error_detail = response.json().get("detail")
        except Exception:
            error_detail = None
        raise HTTPException(
            status_code=502,
            detail=f"{reason}; browser fallback failed ({response.status_code}: {error_detail or 'no detail'})",
        )

    try:
        browser = response.json()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"{reason}; browser fallback returned invalid JSON") from exc

    required = {
        "sourceUrl",
        "finalUrl",
        "httpStatus",
        "bodyBytes",
        "visibleTextLength",
        "visibleText",
        "headings",
        "anchors",
    }
    missing = sorted(required.difference(browser))
    if missing:
        raise HTTPException(status_code=502, detail=f"{reason}; browser fallback missing fields: {', '.join(missing)}")

    if int(browser.get("visibleTextLength") or 0) < MIN_USABLE_VISIBLE_TEXT:
        raise HTTPException(status_code=502, detail=f"{reason}; browser fallback content remained sparse")

    return {
        "version": ROUTER_VERSION,
        "sourceUrl": browser["sourceUrl"],
        "finalUrl": browser["finalUrl"],
        "httpStatus": browser["httpStatus"],
        "contentType": browser.get("contentType"),
        "bodyBytes": browser["bodyBytes"],
        "title": browser.get("title"),
        "metaDescription": browser.get("metaDescription"),
        "visibleTextLength": browser["visibleTextLength"],
        "visibleText": browser["visibleText"],
        "headings": browser["headings"],
        "anchors": browser["anchors"],
        "transport": browser.get("transport", "PLAYWRIGHT_CHROMIUM"),
        "retrievalMode": "BROWSER_REQUIRED",
        "routingReason": reason,
        "directHttpStatus": direct_status,
        "directVersion": direct_version,
        "browserVersion": browser.get("version"),
    }


@app.get("/fetch/routed-html/health")
async def routed_html_health() -> Dict[str, Any]:
    return {
        "ok": True,
        "version": ROUTER_VERSION,
        "service": "retrieval-router",
        "browserConfigured": bool(
            os.getenv("BROWSER_FETCH_BASE_URL", "").strip()
            and os.getenv("BROWSER_FETCH_KEY", "").strip()
        ),
        "writeMode": "READ_ONLY",
    }


@app.get("/fetch/routed-html", response_model=RoutedHtmlFetchResponse)
async def fetch_routed_html(
    url: str = Query(..., min_length=8),
    timeout_seconds: float = Query(default=35.0, ge=5.0, le=35.0),
    x_adapter_key: Optional[str] = Header(default=None),
) -> RoutedHtmlFetchResponse:
    _auth(x_adapter_key)

    try:
        direct = await _fetch_public_html(url, timeout_seconds=timeout_seconds)
    except HTTPException as exc:
        source_status = _source_status_from_exception(exc)
        if source_status not in ROUTABLE_SOURCE_STATUSES:
            raise
        payload = await _browser_payload(
            url=url,
            timeout_seconds=timeout_seconds,
            reason=f"DIRECT_HTTP_{source_status}",
            direct_status=source_status,
            direct_version=None,
        )
        return RoutedHtmlFetchResponse(**payload)

    if direct.visibleTextLength < MIN_USABLE_VISIBLE_TEXT:
        payload = await _browser_payload(
            url=url,
            timeout_seconds=timeout_seconds,
            reason="SPARSE_SERVER_HTML",
            direct_status=direct.httpStatus,
            direct_version=direct.version,
        )
        return RoutedHtmlFetchResponse(**payload)

    return RoutedHtmlFetchResponse(**_direct_payload(direct))
