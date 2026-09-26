"""Read-only generic company-pipeline extraction route.

This is an additive route over the existing adapter service. It interprets
public company pipeline HTML into rows aligned to PORTFOLIO_DISCOVERY_V1.

Guardrails:
- public HTTP(S) only with the existing SSRF/public-host checks;
- no Airtable access or writes;
- no Portfolio/master-data writes;
- no company-specific parser branch;
- fail closed via readyForDiscovery=False when structural validation fails.
"""

from __future__ import annotations

import asyncio
import os
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import httpx
from fastapi import Header, HTTPException, Query
from pydantic import BaseModel

from main import _auth, app
from html_fetch_extension import (
    HTML_FETCH_MAX_BYTES,
    HTML_FETCH_MAX_REDIRECTS,
    _assert_public_http_url,
)
from generic_pipeline_interpreter_canary import (
    VERSION as INTERPRETER_VERSION,
    interpret_pipeline_html,
    interpret_pipeline_structure,
    validate_source,
)


ADAPTER_PROFILE = "PIPELINE_GENERIC_HTML_V1"
ROUTE_VERSION = "GENERIC_PIPELINE_EXTRACTION_V1.2.4_BROWSER_ON_STRUCTURE_FAIL_READ_ONLY"


class GenericPipelineExtractionResponse(BaseModel):
    version: str
    routeVersion: str
    interpreterVersion: str
    company: str
    sourceUrl: str
    finalUrl: str
    sourceDate: Optional[str] = None
    readOnly: bool
    readyForDiscovery: bool
    rowCount: int
    rows: List[Dict[str, Any]]
    summary: Dict[str, Any]
    issues: List[Dict[str, Any]]
    diagnostics: Dict[str, Any]
    validation: Dict[str, Any]
    guardrails: Dict[str, Any]


async def _fetch_raw_public_html(
    url: str,
    timeout_seconds: float = 35.0,
) -> tuple[str, str]:
    """Fetch raw HTML while reusing the service's existing public-host guard."""

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36 "
            "GenericPipelineExtraction/1.0"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-GB,en;q=0.9,en-US;q=0.8",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }

    timeout = httpx.Timeout(
        timeout_seconds,
        connect=min(12.0, max(5.0, timeout_seconds * 0.4)),
    )

    current_url = url
    response: Optional[httpx.Response] = None

    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=False,
        headers=headers,
    ) as client:
        for redirect_no in range(HTML_FETCH_MAX_REDIRECTS + 1):
            await _assert_public_http_url(current_url)

            try:
                response = await client.get(current_url)
            except httpx.TimeoutException as exc:
                raise HTTPException(
                    status_code=504,
                    detail="Pipeline source fetch timed out",
                ) from exc
            except httpx.HTTPError as exc:
                raise HTTPException(
                    status_code=502,
                    detail=f"Pipeline source fetch failed: {exc}",
                ) from exc

            if response.status_code not in {301, 302, 303, 307, 308}:
                break

            location = response.headers.get("location")
            if not location:
                raise HTTPException(
                    status_code=502,
                    detail="Pipeline source redirect missing Location",
                )
            if redirect_no >= HTML_FETCH_MAX_REDIRECTS:
                raise HTTPException(
                    status_code=508,
                    detail="Too many pipeline source redirects",
                )

            current_url = urljoin(str(response.url), location)

    if response is None:
        raise HTTPException(
            status_code=502,
            detail="Pipeline source returned no response",
        )

    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"Pipeline source returned HTTP {response.status_code}",
        )

    content = response.content
    if len(content) > HTML_FETCH_MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail="Pipeline source HTML exceeds fetch size limit",
        )

    final_url = str(response.url)
    await _assert_public_http_url(final_url)

    return response.text, final_url


def _visible_text_length(raw_html: str) -> int:
    """Approximate useful server-rendered text before parser interpretation.

    Modern JS sites can return HTTP 200 with a large HTML/script shell but almost
    no user-visible content. Treat that as sparse server HTML so the existing
    bounded Playwright route gets one chance to recover the rendered pipeline.
    """
    text = raw_html or ""
    text = re.sub(
        r"(?is)<(?:script|style|noscript|svg)\\b[^>]*>.*?</(?:script|style|noscript|svg)>",
        " ",
        text,
    )
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = re.sub(r"\\s+", " ", text).strip()
    return len(text)


def _browser_config() -> tuple[str, str]:
    return (
        os.getenv("BROWSER_FETCH_BASE_URL", "").strip().rstrip("/"),
        os.getenv("BROWSER_FETCH_KEY", "").strip(),
    )


def _browser_fallback_allowed(exc: HTTPException) -> bool:
    detail = str(exc.detail or "").lower()
    return (
        exc.status_code == 504
        or "timed out" in detail
        or any(f"http {status}" in detail for status in (403, 408, 429))
    )


async def _fetch_browser_structure(
    url: str,
    timeout_seconds: float,
) -> Dict[str, Any]:
    """Retrieve the public page through the isolated browser worker.

    The worker owns browser/network safety. This service receives only the
    rendered structural evidence needed by the generic interpreter.
    """

    base, key = _browser_config()
    if not base or not key:
        raise HTTPException(
            status_code=502,
            detail="Browser fallback is required but not configured",
        )

    endpoint = f"{base}/fetch/browser"
    timeout = httpx.Timeout(timeout_seconds + 12.0, connect=12.0)

    response: Optional[httpx.Response] = None
    payload: Optional[Dict[str, Any]] = None
    last_error = "Browser fallback failed"

    # Render browser workers can cold-start behind a non-JSON 502/503 page.
    # Retry only bounded transient transport/service failures. Source-level
    # failures remain fail-closed and are never retried into success.
    for attempt in range(1, 3):
        try:
            async with httpx.AsyncClient(
                timeout=timeout,
                follow_redirects=False,
            ) as client:
                response = await client.get(
                    endpoint,
                    params={
                        "url": url,
                        "timeout_seconds": timeout_seconds,
                        "expand_load_more": "true",
                    },
                    headers={
                        "X-Browser-Key": key,
                        "Accept": "application/json",
                    },
                )
        except httpx.TimeoutException:
            last_error = "Browser fallback timed out"
            if attempt < 2:
                await asyncio.sleep(1.0)
                continue
            raise HTTPException(status_code=504, detail=last_error)
        except httpx.HTTPError as exc:
            last_error = f"Browser fallback transport failed: {exc}"
            if attempt < 2:
                await asyncio.sleep(1.0)
                continue
            raise HTTPException(status_code=502, detail=last_error) from exc

        try:
            parsed_payload = response.json()
            payload = parsed_payload if isinstance(parsed_payload, dict) else None
        except Exception:
            payload = None

        if payload is None:
            last_error = (
                f"Browser fallback returned invalid JSON; "
                f"HTTP {response.status_code}; "
                f"body={response.text[:180]!r}"
            )
            if attempt < 2 and response.status_code in {408, 429, 500, 502, 503, 504}:
                await asyncio.sleep(1.0)
                continue
            raise HTTPException(status_code=502, detail=last_error)

        if response.status_code >= 400:
            detail = str(payload.get("detail", "no detail"))
            last_error = (
                f"Browser fallback failed: HTTP {response.status_code}; {detail}"
            )
            # Retry only worker/service transient errors. If the worker reached
            # the target and reports source HTTP 403/other source denial, fail
            # closed immediately rather than masking the source condition.
            source_denial = "source returned http" in detail.lower()
            if (
                attempt < 2
                and not source_denial
                and response.status_code in {408, 429, 500, 502, 503, 504}
            ):
                await asyncio.sleep(1.0)
                continue
            raise HTTPException(status_code=502, detail=last_error)

        break

    if response is None or payload is None:
        raise HTTPException(status_code=502, detail=last_error)

    visible_lines = payload.get("visibleLines")
    tables = payload.get("tables")

    if not isinstance(visible_lines, list) or not isinstance(tables, list):
        raise HTTPException(
            status_code=502,
            detail=(
                "Browser fallback response does not expose rendered "
                "visibleLines/tables; deploy browser worker V1.1+ first"
            ),
        )

    return payload


async def _extract_generic_pipeline(
    *,
    company: str,
    source_url: str,
    timeout_seconds: float = 35.0,
) -> GenericPipelineExtractionResponse:
    retrieval_mode = "DIRECT"
    routing_reason = "DIRECT_STRUCTURE_PASS"
    browser_version: Optional[str] = None
    direct_failure: Optional[str] = None
    final_url = source_url
    rows = []
    diagnostics: Dict[str, Any] = {}
    validation: Dict[str, Any] = {}

    try:
        raw_html, final_url = await _fetch_raw_public_html(
            source_url,
            timeout_seconds=timeout_seconds,
        )

        rows, diagnostics = await asyncio.to_thread(
            interpret_pipeline_html,
            company,
            final_url,
            raw_html,
        )
        validation = validate_source(
            company,
            rows,
            diagnostics,
        )

        # A successful HTTP response with substantial source text is a parser
        # problem, not a transport problem. Keep it DIRECT and fail closed so
        # we do not hide unsupported page structures behind browser rendering.
        #
        # Browser escalation is allowed only for a genuinely sparse server
        # response (typical JS shell) or the bounded transport failures handled
        # in the HTTPException path below.
        direct_visible_lines = int(diagnostics.get("visibleLineCount") or 0)
        direct_visible_text_length = _visible_text_length(raw_html)
        if not validation.get("pass"):
            base, key = _browser_config()
            if base and key:
                routing_reason = (
                    "SPARSE_SERVER_HTML"
                    if (
                        direct_visible_lines < 20
                        or direct_visible_text_length < 800
                    )
                    else "DIRECT_STRUCTURE_BROWSER_RETRY"
                )
                browser = await _fetch_browser_structure(
                    source_url,
                    timeout_seconds,
                )
                retrieval_mode = "BROWSER_REQUIRED"
                browser_version = str(browser.get("version") or "")
                final_url = str(browser.get("finalUrl") or source_url)

                rows, diagnostics = await asyncio.to_thread(
                    interpret_pipeline_structure,
                    company,
                    final_url,
                    browser.get("visibleLines") or [],
                    browser.get("tables") or [],
                )
                validation = validate_source(
                    company,
                    rows,
                    diagnostics,
                )
            else:
                routing_reason = "DIRECT_STRUCTURE_UNSUPPORTED_BROWSER_NOT_CONFIGURED"

    except HTTPException as exc:
        if not _browser_fallback_allowed(exc):
            raise

        direct_failure = str(exc.detail or "")
        routing_reason = "DIRECT_TRANSPORT_FAIL"
        browser = await _fetch_browser_structure(
            source_url,
            timeout_seconds,
        )
        retrieval_mode = "BROWSER_REQUIRED"
        browser_version = str(browser.get("version") or "")
        final_url = str(browser.get("finalUrl") or source_url)

        rows, diagnostics = await asyncio.to_thread(
            interpret_pipeline_structure,
            company,
            final_url,
            browser.get("visibleLines") or [],
            browser.get("tables") or [],
        )
        validation = validate_source(
            company,
            rows,
            diagnostics,
        )

    diagnostics = dict(diagnostics)
    diagnostics.update(
        {
            "retrievalMode": retrieval_mode,
            "routingReason": routing_reason,
            "browserVersion": browser_version,
            "browserExpansionClicks": (
                int(browser.get("expansionClicks") or 0)
                if "browser" in locals() and isinstance(browser, dict)
                else 0
            ),
            "directFailure": direct_failure,
            "directVisibleTextLength": (
                direct_visible_text_length
                if "direct_visible_text_length" in locals()
                else None
            ),
            "portfolioDependentValidation": False,
        }
    )

    row_payloads: List[Dict[str, Any]] = []
    for row in rows:
        payload = row.as_discovery_contract()
        payload["sourceAdapter"] = ADAPTER_PROFILE
        payload["sourceCardOrdinal"] = payload.get("sourceOrdinal")
        payload["sourceTherapeuticArea"] = payload.get("therapeuticArea", "")
        row_payloads.append(payload)

    structural_pass = bool(validation.get("pass"))
    issues = [
        {"issue": str(issue)}
        for issue in validation.get("issues", [])
    ]
    summary = {
        "structuralValidationPass": structural_pass,
        "actual": {
            "Total": len(row_payloads),
        },
        "productionStatus": (
            "READY FOR AIRTABLE DELTA COMPARISON"
            if structural_pass
            else "FAIL CLOSED - PARSER/STRUCTURE REVIEW REQUIRED"
        ),
        "selectedMethod": diagnostics.get("selectedMethod"),
        "ctgovPhaseFallbackRows": diagnostics.get("ctgovPhaseFallbackRows", 0),
        "retrievalMode": retrieval_mode,
        "routingReason": routing_reason,
        "browserVersion": browser_version,
        "portfolioDependentValidation": False,
        "companySpecificParserBranch": False,
        "writeMode": "READ_ONLY",
    }

    return GenericPipelineExtractionResponse(
        version=ADAPTER_PROFILE,
        routeVersion=ROUTE_VERSION,
        interpreterVersion=INTERPRETER_VERSION,
        company=company,
        sourceUrl=source_url,
        finalUrl=final_url,
        sourceDate=None,
        readOnly=True,
        readyForDiscovery=structural_pass,
        rowCount=len(row_payloads),
        rows=row_payloads,
        summary=summary,
        issues=issues,
        diagnostics=diagnostics,
        validation=validation,
        guardrails={
            "airtableWrites": False,
            "portfolioWrites": False,
            "masterDataWrites": False,
            "companySpecificParserBranch": False,
            "portfolioDependentValidation": False,
            "publicHttpOnly": True,
            "ssrfGuard": True,
            "fuzzyIdentityResolution": False,
            "browserEscalationBounded": True,
        },
    )


@app.get("/extract/generic/pipeline/health")
async def generic_pipeline_health() -> Dict[str, Any]:
    return {
        "ok": True,
        "version": ADAPTER_PROFILE,
        "routeVersion": ROUTE_VERSION,
        "interpreterVersion": INTERPRETER_VERSION,
        "readOnly": True,
        "writeMode": "READ_ONLY",
    }


@app.get(
    "/extract/generic/pipeline",
    response_model=GenericPipelineExtractionResponse,
)
async def extract_generic_pipeline(
    company: str = Query(..., min_length=1, max_length=160),
    source_url: str = Query(..., min_length=8),
    timeout_seconds: float = Query(default=35.0, ge=5.0, le=35.0),
    x_adapter_key: Optional[str] = Header(default=None),
) -> GenericPipelineExtractionResponse:
    _auth(x_adapter_key)

    return await _extract_generic_pipeline(
        company=company,
        source_url=source_url,
        timeout_seconds=timeout_seconds,
    )
