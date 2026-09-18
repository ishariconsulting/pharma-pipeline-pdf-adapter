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
    validate_source,
)


ADAPTER_PROFILE = "PIPELINE_GENERIC_HTML_V1"
ROUTE_VERSION = "GENERIC_PIPELINE_EXTRACTION_V1.1_READ_ONLY"


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


async def _extract_generic_pipeline(
    *,
    company: str,
    source_url: str,
    timeout_seconds: float = 35.0,
) -> GenericPipelineExtractionResponse:
    raw_html, final_url = await _fetch_raw_public_html(
        source_url,
        timeout_seconds=timeout_seconds,
    )

    # The interpreter is CPU-light but may use the public CT.gov phase fallback
    # for source rows whose phase is only encoded visually.
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
            "publicHttpOnly": True,
            "ssrfGuard": True,
            "fuzzyIdentityResolution": False,
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
