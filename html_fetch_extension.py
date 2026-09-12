import asyncio
import html as html_lib
import ipaddress
import re
import socket
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

import httpx
from fastapi import Header, HTTPException, Query
from pydantic import BaseModel

from main import _auth, app


HTML_FETCH_VERSION = "V2.41.1 EXTERNAL HTML FETCH EXTENSION"
HTML_FETCH_MAX_BYTES = 2_500_000
HTML_FETCH_VISIBLE_TEXT_MAX = 200_000
HTML_FETCH_MAX_ANCHORS = 400
HTML_FETCH_MAX_HEADINGS = 100
HTML_FETCH_MAX_REDIRECTS = 5


class HtmlFetchResponse(BaseModel):
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
    headings: List[Dict[str, Any]]
    anchors: List[Dict[str, str]]


def _strip_html(raw_html: str) -> str:
    text = raw_html or ""
    text = re.sub(r"<!--[\s\S]*?-->", " ", text)
    text = re.sub(r"<script\b[^>]*>[\s\S]*?</script>", " ", text, flags=re.I)
    text = re.sub(r"<style\b[^>]*>[\s\S]*?</style>", " ", text, flags=re.I)
    text = re.sub(r"<noscript\b[^>]*>[\s\S]*?</noscript>", " ", text, flags=re.I)
    text = re.sub(r"<svg\b[^>]*>[\s\S]*?</svg>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html_lib.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _title(raw_html: str) -> Optional[str]:
    match = re.search(r"<title[^>]*>([\s\S]*?)</title>", raw_html or "", re.I)
    if not match:
        return None
    value = _strip_html(match.group(1))[:300]
    return value or None


def _meta_description(raw_html: str) -> Optional[str]:
    patterns = [
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']*)["\'][^>]*>',
        r'<meta[^>]+content=["\']([^"\']*)["\'][^>]+name=["\']description["\'][^>]*>',
        r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']*)["\'][^>]*>',
        r'<meta[^>]+content=["\']([^"\']*)["\'][^>]+property=["\']og:description["\'][^>]*>',
    ]
    for pattern in patterns:
        match = re.search(pattern, raw_html or "", re.I)
        if match:
            value = html_lib.unescape(match.group(1)).strip()[:500]
            return value or None
    return None


def _headings(raw_html: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for match in re.finditer(r"<h([1-4])\b[^>]*>([\s\S]*?)</h\1>", raw_html or "", re.I):
        text = _strip_html(match.group(2))
        if not text or "{{" in text or "}}" in text:
            continue
        out.append({"level": int(match.group(1)), "text": text[:240]})
        if len(out) >= HTML_FETCH_MAX_HEADINGS:
            break
    return out


def _anchors(raw_html: str, base_url: str) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    seen = set()
    pattern = re.compile(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>([\s\S]*?)</a>', re.I)
    for match in pattern.finditer(raw_html or ""):
        href = html_lib.unescape(match.group(1)).strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        text = _strip_html(match.group(2))[:240]
        if not text or "{{" in text or "}}" in text:
            continue
        try:
            final = urljoin(base_url, href)
        except Exception:
            continue
        key = (text.lower(), final)
        if key in seen:
            continue
        seen.add(key)
        out.append({"text": text, "url": final})
        if len(out) >= HTML_FETCH_MAX_ANCHORS:
            break
    return out


async def _assert_public_http_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise HTTPException(status_code=400, detail="Only http/https URLs are allowed")
    if not parsed.hostname:
        raise HTTPException(status_code=400, detail="URL hostname is required")
    if parsed.username or parsed.password:
        raise HTTPException(status_code=400, detail="URL credentials are not allowed")

    host = parsed.hostname.strip().lower()
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        raise HTTPException(status_code=400, detail="Local/private hosts are not allowed")

    try:
        loop = asyncio.get_running_loop()
        infos = await loop.getaddrinfo(
            host,
            parsed.port or (443 if parsed.scheme == "https" else 80),
            type=socket.SOCK_STREAM,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not resolve source host: {exc}") from exc

    addresses = {info[4][0] for info in infos if info and info[4]}
    if not addresses:
        raise HTTPException(status_code=502, detail="Source host resolved to no addresses")

    for addr in addresses:
        try:
            ip = ipaddress.ip_address(addr.split("%", 1)[0])
        except ValueError:
            continue
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise HTTPException(status_code=400, detail="Local/private source addresses are not allowed")


async def _fetch_public_html(url: str) -> HtmlFetchResponse:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-GB,en;q=0.9,en-US;q=0.8",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }

    timeout = httpx.Timeout(35.0, connect=12.0)
    current_url = url
    response: Optional[httpx.Response] = None

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False, headers=headers) as client:
        for redirect_no in range(HTML_FETCH_MAX_REDIRECTS + 1):
            await _assert_public_http_url(current_url)
            try:
                response = await client.get(current_url)
            except httpx.TimeoutException as exc:
                raise HTTPException(status_code=504, detail="Source fetch timed out") from exc
            except httpx.HTTPError as exc:
                raise HTTPException(status_code=502, detail=f"Source fetch failed: {exc}") from exc

            if response.status_code not in {301, 302, 303, 307, 308}:
                break

            location = response.headers.get("location")
            if not location:
                raise HTTPException(status_code=502, detail="Redirect response did not include Location")
            if redirect_no >= HTML_FETCH_MAX_REDIRECTS:
                raise HTTPException(status_code=508, detail="Too many source redirects")
            current_url = urljoin(str(response.url), location)

    if response is None:
        raise HTTPException(status_code=502, detail="Source fetch returned no response")

    status = int(response.status_code)
    if status >= 400:
        raise HTTPException(status_code=502, detail=f"Source returned HTTP {status}")

    content = response.content
    if len(content) > HTML_FETCH_MAX_BYTES:
        raise HTTPException(status_code=413, detail="HTML response exceeds fetch size limit")

    content_type = response.headers.get("content-type")
    raw_html = response.text
    visible = _strip_html(raw_html)
    final_url = str(response.url)

    return HtmlFetchResponse(
        version=HTML_FETCH_VERSION,
        sourceUrl=url,
        finalUrl=final_url,
        httpStatus=status,
        contentType=content_type,
        bodyBytes=len(content),
        title=_title(raw_html),
        metaDescription=_meta_description(raw_html),
        visibleTextLength=len(visible),
        visibleText=visible[:HTML_FETCH_VISIBLE_TEXT_MAX],
        headings=_headings(raw_html),
        anchors=_anchors(raw_html, final_url),
    )


@app.get("/fetch/html/health")
async def fetch_html_health() -> Dict[str, Any]:
    return {
        "ok": True,
        "version": HTML_FETCH_VERSION,
        "service": "external-html-fetch-extension",
    }


@app.get("/fetch/html", response_model=HtmlFetchResponse)
async def fetch_html(
    url: str = Query(..., min_length=8),
    x_adapter_key: Optional[str] = Header(default=None),
) -> HtmlFetchResponse:
    _auth(x_adapter_key)
    return await _fetch_public_html(url)


# Additive route registration only. Importing these modules does not alter any
# existing pipeline/regulatory automation or master-data write path.
import portfolio_discovery_extension_v12  # noqa: E402,F401
import portfolio_discovery_extension_v13  # noqa: E402,F401
import portfolio_discovery_extension_v14  # noqa: E402,F401
import astrazeneca_reconciliation_canary  # noqa: E402,F401
import astrazeneca_reconciliation_canary_patch  # noqa: E402,F401
import portfolio_discovery_regression_canaries  # noqa: E402,F401
