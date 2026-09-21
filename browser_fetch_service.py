"""Read-only browser retrieval worker for public pharma source pages.

This service exists only to retrieve public pages that cannot be reliably fetched
through normal server-side HTTP (for example JavaScript-rendered pages or sources
that return 403/408 to a simple machine client). It never writes to Airtable or
any master-data store.
"""

from __future__ import annotations

import asyncio
import html as html_lib
import ipaddress
import os
import re
import socket
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urljoin, urlparse

from fastapi import FastAPI, Header, HTTPException, Query
from pydantic import BaseModel
from playwright.async_api import Browser, BrowserContext, Page, async_playwright


BROWSER_FETCH_VERSION = "BROWSER_RETRIEVAL_V1.2_STRUCTURED_DOM_EXPAND"
MAX_VISIBLE_TEXT = 200_000
MAX_HTML_BYTES = 2_500_000
MAX_ANCHORS = 400
MAX_HEADINGS = 100
MAX_VISIBLE_LINES = 5000
MAX_LINE_CHARS = 1200
MAX_TABLES = 40
MAX_TABLE_ROWS = 1000
MAX_TABLE_CELLS = 40
MAX_TABLE_CELL_CHARS = 800
DEFAULT_TIMEOUT_SECONDS = 35.0

LILLY_CANARY_URL = "https://www.lilly.com/science/research-development/pipeline"
BAYER_CANARY_URL = "https://www.bayer.com/en/pharma/development-pipeline"

app = FastAPI(
    title="Pharma Browser Retrieval Worker",
    version=BROWSER_FETCH_VERSION,
    description="Read-only browser transport for public pharma intelligence sources.",
)


class BrowserFetchResponse(BaseModel):
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
    visibleLines: List[str] = []
    tables: List[List[List[str]]] = []
    headings: List[Dict[str, Any]]
    anchors: List[Dict[str, str]]
    transport: str = "PLAYWRIGHT_CHROMIUM"
    retrievalMode: str = "BROWSER_REQUIRED"
    expansionClicks: int = 0
    layoutTextNodes: List[Dict[str, Any]] = []


def _auth(x_browser_key: Optional[str]) -> None:
    expected = os.getenv("BROWSER_FETCH_KEY", "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="Browser worker key is not configured")
    if x_browser_key != expected:
        raise HTTPException(status_code=401, detail="Invalid browser worker key")


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


async def _resolve_public_host(host: str, port: int) -> None:
    try:
        loop = asyncio.get_running_loop()
        infos = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
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


async def _assert_public_http_url(url: str, validated_hosts: Optional[Set[str]] = None) -> None:
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

    if validated_hosts is not None and host in validated_hosts:
        return

    await _resolve_public_host(host, parsed.port or (443 if parsed.scheme == "https" else 80))
    if validated_hosts is not None:
        validated_hosts.add(host)


async def _install_request_guard(page: Page) -> None:
    validated_hosts: Set[str] = set()

    async def guard(route) -> None:
        request = route.request
        parsed = urlparse(request.url)

        if request.resource_type in {"image", "media", "font"}:
            await route.abort()
            return

        if parsed.scheme in {"data", "blob"}:
            await route.continue_()
            return

        try:
            await _assert_public_http_url(request.url, validated_hosts)
        except HTTPException:
            await route.abort()
            return

        await route.continue_()

    await page.route("**/*", guard)


async def _extract_rendered(
    page: Page,
    source_url: str,
    response_status: int,
    expansion_clicks: int = 0,
    include_layout: bool = False,
) -> BrowserFetchResponse:
    raw_html = await page.content()
    encoded = raw_html.encode("utf-8", errors="ignore")
    if len(encoded) > MAX_HTML_BYTES:
        raise HTTPException(status_code=413, detail="Rendered HTML exceeds fetch size limit")

    title = (await page.title()).strip() or None
    final_url = page.url
    await _assert_public_http_url(final_url)

    try:
        raw_visible_text = await page.locator("body").inner_text(timeout=5_000)
    except Exception:
        raw_visible_text = _strip_html(raw_html)

    visible_lines: List[str] = []
    for raw_line in (raw_visible_text or "").splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line:
            continue
        visible_lines.append(line[:MAX_LINE_CHARS])
        if len(visible_lines) >= MAX_VISIBLE_LINES:
            break

    visible_text = re.sub(r"\s+", " ", raw_visible_text or "").strip()

    tables = await page.evaluate(
        """({maxTables, maxRows, maxCells, maxChars}) =>
          Array.from(document.querySelectorAll('table'))
            .slice(0, maxTables)
            .map((table) =>
              Array.from(table.querySelectorAll('tr'))
                .slice(0, maxRows)
                .map((row) =>
                  Array.from(row.querySelectorAll(':scope > th, :scope > td'))
                    .slice(0, maxCells)
                    .map((cell) =>
                      (cell.innerText || cell.textContent || '')
                        .replace(/\\s+/g, ' ')
                        .trim()
                        .slice(0, maxChars)
                    )
                )
                .filter((row) => row.some((cell) => cell))
            )
            .filter((table) => table.length > 0)""",
        {
            "maxTables": MAX_TABLES,
            "maxRows": MAX_TABLE_ROWS,
            "maxCells": MAX_TABLE_CELLS,
            "maxChars": MAX_TABLE_CELL_CHARS,
        },
    )

    try:
        meta_description = await page.locator('meta[name="description"]').get_attribute("content", timeout=2_000)
    except Exception:
        meta_description = None
    if not meta_description:
        try:
            meta_description = await page.locator('meta[property="og:description"]').get_attribute("content", timeout=2_000)
        except Exception:
            meta_description = None
    if meta_description:
        meta_description = meta_description.strip()[:500] or None

    headings = await page.evaluate(
        """(limit) => Array.from(document.querySelectorAll('h1,h2,h3,h4'))
          .map((el) => ({level: Number(el.tagName.substring(1)), text: (el.innerText || el.textContent || '').replace(/\\s+/g,' ').trim().slice(0,240)}))
          .filter((x) => x.text && !x.text.includes('{{') && !x.text.includes('}}'))
          .slice(0, limit)""",
        MAX_HEADINGS,
    )

    raw_anchors = await page.evaluate(
        """(limit) => Array.from(document.querySelectorAll('a[href]'))
          .map((el) => ({text: (el.innerText || el.textContent || '').replace(/\\s+/g,' ').trim().slice(0,240), href: el.getAttribute('href') || ''}))
          .filter((x) => x.text && x.href && !x.href.startsWith('#') && !x.href.startsWith('javascript:') && !x.href.startsWith('mailto:') && !x.href.startsWith('tel:'))
          .slice(0, limit)""",
        MAX_ANCHORS * 2,
    )

    layout_text_nodes: List[Dict[str, Any]] = []
    if include_layout:
        try:
            layout_text_nodes = await page.evaluate(
                """(limit) => {
                  const nodes = [];
                  const all = Array.from(document.querySelectorAll('body *'));
                  for (const el of all) {
                    if (nodes.length >= limit) break;
                    const style = window.getComputedStyle(el);
                    if (!style || style.display === 'none' || style.visibility === 'hidden') continue;
                    const rect = el.getBoundingClientRect();
                    if (!rect || rect.width <= 0 || rect.height <= 0) continue;
                    const ownText = Array.from(el.childNodes)
                      .filter(n => n.nodeType === Node.TEXT_NODE)
                      .map(n => n.textContent || '')
                      .join(' ')
                      .replace(/\\s+/g, ' ')
                      .trim();
                    if (!ownText) continue;
                    nodes.push({
                      tag: (el.tagName || '').toLowerCase(),
                      text: ownText.slice(0, 500),
                      x: Math.round(rect.x * 10) / 10,
                      y: Math.round(rect.y * 10) / 10,
                      width: Math.round(rect.width * 10) / 10,
                      height: Math.round(rect.height * 10) / 10,
                      className: String(el.className || '').slice(0, 300),
                      id: String(el.id || '').slice(0, 160),
                      ariaLabel: String(el.getAttribute('aria-label') || '').slice(0, 240),
                      role: String(el.getAttribute('role') || '').slice(0, 120),
                    });
                  }
                  return nodes;
                }""",
                1800,
            )
        except Exception:
            layout_text_nodes = []

    anchors: List[Dict[str, str]] = []
    seen = set()
    for item in raw_anchors:
        try:
            absolute = urljoin(final_url, item.get("href", ""))
            parsed = urlparse(absolute)
            if parsed.scheme not in {"http", "https"}:
                continue
        except Exception:
            continue
        key = (item.get("text", "").lower(), absolute)
        if key in seen:
            continue
        seen.add(key)
        anchors.append({"text": item.get("text", ""), "url": absolute})
        if len(anchors) >= MAX_ANCHORS:
            break

    return BrowserFetchResponse(
        version=BROWSER_FETCH_VERSION,
        sourceUrl=source_url,
        finalUrl=final_url,
        httpStatus=response_status,
        contentType="text/html; rendered=chromium",
        bodyBytes=len(encoded),
        title=title,
        metaDescription=meta_description,
        visibleTextLength=len(visible_text),
        visibleText=visible_text[:MAX_VISIBLE_TEXT],
        visibleLines=visible_lines,
        tables=tables,
        headings=headings,
        anchors=anchors,
        expansionClicks=expansion_clicks,
        layoutTextNodes=layout_text_nodes,
    )


async def _expand_load_more_buttons(page: Page, max_clicks: int = 30) -> int:
    """Expand read-only cards hidden behind literal Load more buttons."""
    clicks = 0
    unchanged = 0

    for _ in range(max_clicks):
        locator = page.get_by_role(
            "button",
            name=re.compile(r"^\s*load\s+more\s*$", re.I),
        )
        count = await locator.count()
        target = None
        for idx in range(min(count, 12)):
            candidate = locator.nth(idx)
            try:
                if await candidate.is_visible():
                    target = candidate
                    break
            except Exception:
                continue

        if target is None:
            break

        try:
            before = await page.locator("body").inner_text(timeout=3_000)
            await target.scroll_into_view_if_needed(timeout=2_000)
            await target.click(timeout=3_000)
            clicks += 1
            await page.wait_for_timeout(650)
            after = await page.locator("body").inner_text(timeout=3_000)
        except Exception:
            break

        if len(after or "") <= len(before or ""):
            unchanged += 1
            if unchanged >= 2:
                break
        else:
            unchanged = 0

    return clicks


async def _browser_fetch(
    url: str,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    expand_load_more: bool = False,
    include_layout: bool = False,
) -> BrowserFetchResponse:
    await _assert_public_http_url(url)
    timeout_ms = int(timeout_seconds * 1000)

    async with async_playwright() as pw:
        browser: Browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        )
        context: Optional[BrowserContext] = None
        try:
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                locale="en-GB",
                viewport={"width": 1365, "height": 900},
                java_script_enabled=True,
            )
            page = await context.new_page()
            await _install_request_guard(page)

            try:
                response = await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            except Exception as exc:
                raise HTTPException(status_code=504, detail=f"Browser navigation failed: {type(exc).__name__}") from exc

            if response is None:
                raise HTTPException(status_code=502, detail="Browser navigation returned no document response")

            status = int(response.status)
            if status >= 400:
                raise HTTPException(status_code=502, detail=f"Browser source returned HTTP {status}")

            try:
                await page.wait_for_load_state("networkidle", timeout=min(10_000, timeout_ms))
            except Exception:
                pass

            await page.wait_for_timeout(1_000)
            expansion_clicks = 0
            if expand_load_more:
                expansion_clicks = await _expand_load_more_buttons(page)
            return await _extract_rendered(
                page,
                url,
                status,
                expansion_clicks=expansion_clicks,
                include_layout=include_layout,
            )
        finally:
            if context is not None:
                await context.close()
            await browser.close()


@app.get("/health")
async def health() -> Dict[str, Any]:
    return {
        "ok": True,
        "version": BROWSER_FETCH_VERSION,
        "service": "pharma-browser-retrieval",
        "writeMode": "READ_ONLY",
    }


@app.get("/fetch/browser", response_model=BrowserFetchResponse)
async def fetch_browser(
    url: str = Query(..., min_length=8),
    timeout_seconds: float = Query(DEFAULT_TIMEOUT_SECONDS, ge=5.0, le=35.0),
    expand_load_more: bool = Query(default=False),
    include_layout: bool = Query(default=False),
    x_browser_key: Optional[str] = Header(default=None),
) -> BrowserFetchResponse:
    _auth(x_browser_key)
    return await _browser_fetch(
        url,
        timeout_seconds=timeout_seconds,
        expand_load_more=expand_load_more,
        include_layout=include_layout,
    )


async def _run_canary(url: str, expected_terms: List[str]) -> Dict[str, Any]:
    try:
        result = await _browser_fetch(url, timeout_seconds=35.0)
        text = result.visibleText.lower()
        matched = [term for term in expected_terms if term.lower() in text]
        return {
            "ok": bool(result.httpStatus == 200 and result.visibleTextLength >= 800 and matched),
            "version": BROWSER_FETCH_VERSION,
            "sourceUrl": url,
            "finalUrl": result.finalUrl,
            "httpStatus": result.httpStatus,
            "visibleTextLength": result.visibleTextLength,
            "title": result.title,
            "matchedExpectedTerms": matched,
            "transport": result.transport,
            "retrievalMode": result.retrievalMode,
        }
    except HTTPException as exc:
        return {
            "ok": False,
            "version": BROWSER_FETCH_VERSION,
            "sourceUrl": url,
            "errorStatus": exc.status_code,
            "error": str(exc.detail),
        }
    except Exception as exc:
        return {
            "ok": False,
            "version": BROWSER_FETCH_VERSION,
            "sourceUrl": url,
            "errorStatus": 500,
            "error": type(exc).__name__,
        }


@app.get("/canary/lilly")
async def canary_lilly() -> Dict[str, Any]:
    return await _run_canary(
        LILLY_CANARY_URL,
        ["pipeline", "phase"],
    )


@app.get("/canary/bayer")
async def canary_bayer() -> Dict[str, Any]:
    return await _run_canary(
        BAYER_CANARY_URL,
        ["pipeline", "phase"],
    )


async def _browser_dom_context(
    url: str,
    terms: List[str],
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> Dict[str, Any]:
    """Read-only bounded DOM context for source-structure diagnostics."""
    await _assert_public_http_url(url)
    timeout_ms = int(timeout_seconds * 1000)

    clean_terms = []
    for raw in terms[:12]:
        term = re.sub(r"\s+", " ", str(raw or "")).strip()
        if term and len(term) <= 160:
            clean_terms.append(term)
    if not clean_terms:
        raise HTTPException(status_code=400, detail="At least one inspect term is required")

    async with async_playwright() as pw:
        browser: Browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        )
        context: Optional[BrowserContext] = None
        try:
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                locale="en-GB",
                viewport={"width": 1365, "height": 900},
                java_script_enabled=True,
            )
            page = await context.new_page()
            await _install_request_guard(page)
            try:
                response = await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            except Exception as exc:
                raise HTTPException(status_code=504, detail=f"Browser navigation failed: {type(exc).__name__}") from exc
            if response is None:
                raise HTTPException(status_code=502, detail="Browser navigation returned no document response")
            if int(response.status) >= 400:
                raise HTTPException(status_code=502, detail=f"Browser source returned HTTP {int(response.status)}")
            try:
                await page.wait_for_load_state("networkidle", timeout=min(10_000, timeout_ms))
            except Exception:
                pass
            await page.wait_for_timeout(1_000)

            result = await page.evaluate(
                """(terms) => {
                  const norm = (s) => (s || '').replace(/\\s+/g,' ').trim();
                  const attrs = (el) => {
                    const out = {};
                    for (const a of Array.from(el.attributes || [])) {
                      if (
                        a.name === 'class' || a.name === 'id' || a.name === 'style' ||
                        a.name.startsWith('data-') || a.name.startsWith('aria-') ||
                        a.name === 'role'
                      ) out[a.name] = (a.value || '').slice(0,500);
                    }
                    return out;
                  };
                  const node = (el) => {
                    const cs = getComputedStyle(el);
                    const r = el.getBoundingClientRect();
                    return {
                      tag: el.tagName.toLowerCase(),
                      text: norm(el.innerText || el.textContent || '').slice(0,500),
                      attrs: attrs(el),
                      computed: {
                        display: cs.display,
                        position: cs.position,
                        width: cs.width,
                        left: cs.left,
                        right: cs.right,
                        gridColumn: cs.gridColumn,
                        gridRow: cs.gridRow,
                        transform: cs.transform
                      },
                      rect: {
                        x: Math.round(r.x * 10) / 10,
                        y: Math.round(r.y * 10) / 10,
                        width: Math.round(r.width * 10) / 10,
                        height: Math.round(r.height * 10) / 10
                      }
                    };
                  };
                  const all = Array.from(document.querySelectorAll('body *'));
                  const results = [];
                  for (const term of terms) {
                    const low = term.toLowerCase();
                    const exact = all.filter(el => norm(el.innerText || el.textContent || '').toLowerCase() === low);
                    const pool = exact.length ? exact : all.filter(el => {
                      const t = norm(el.innerText || el.textContent || '').toLowerCase();
                      return t && t.includes(low) && t.length <= Math.max(300, low.length * 8);
                    });
                    const matches = [];
                    for (const el of pool.slice(0,4)) {
                      const ancestors = [];
                      let p = el.parentElement;
                      for (let depth=0; p && depth<7; depth++, p=p.parentElement) ancestors.push(node(p));
                      const parent = el.parentElement;
                      const siblings = parent ? Array.from(parent.children).slice(0,30).map(node) : [];
                      matches.push({element: node(el), ancestors, siblings});
                    }
                    results.push({term, matches});
                  }
                  return results;
                }""",
                clean_terms,
            )
            return {
                "ok": True,
                "version": BROWSER_FETCH_VERSION,
                "sourceUrl": url,
                "finalUrl": page.url,
                "terms": clean_terms,
                "contexts": result,
                "readOnly": True,
            }
        finally:
            if context is not None:
                await context.close()
            await browser.close()


@app.get("/diagnostic/dom-context")
async def diagnostic_dom_context(
    url: str = Query(..., min_length=8),
    terms: str = Query(..., min_length=1, max_length=1000),
    timeout_seconds: float = Query(DEFAULT_TIMEOUT_SECONDS, ge=5.0, le=35.0),
    x_browser_key: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    _auth(x_browser_key)
    return await _browser_dom_context(
        url,
        [x for x in terms.split("|") if x.strip()],
        timeout_seconds=timeout_seconds,
    )
