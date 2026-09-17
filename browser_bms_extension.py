"""BMS-specific rendered-text endpoint for the browser retrieval worker.

Read-only. Preserves DOM innerText line boundaries so the main pipeline adapter
can parse the official BMS interactive pipeline without guessing from flattened text.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import Header, HTTPException, Query
from playwright.async_api import Browser, BrowserContext, async_playwright

from browser_fetch_service import (
    DEFAULT_TIMEOUT_SECONDS,
    _assert_public_http_url,
    _auth,
    _install_request_guard,
    app,
)

BMS_RENDER_VERSION = "BMS_BROWSER_RENDER_V1.0"
BMS_PIPELINE_URL = "https://www.bms.com/research-and-development/pipeline.html"
MAX_LINES = 5000
MAX_LINE_CHARS = 1000


@app.get("/extract/bms-rendered-text")
async def extract_bms_rendered_text(
    url: str = Query(default=BMS_PIPELINE_URL, min_length=8),
    timeout_seconds: float = Query(DEFAULT_TIMEOUT_SECONDS, ge=5.0, le=35.0),
    x_browser_key: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    _auth(x_browser_key)
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
                response = await page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=timeout_ms,
                )
            except Exception as exc:
                raise HTTPException(
                    status_code=504,
                    detail=f"BMS browser navigation failed: {type(exc).__name__}",
                ) from exc

            if response is None:
                raise HTTPException(
                    status_code=502,
                    detail="BMS browser navigation returned no document response",
                )

            status = int(response.status)
            if status >= 400:
                raise HTTPException(
                    status_code=502,
                    detail=f"BMS browser source returned HTTP {status}",
                )

            try:
                await page.wait_for_load_state(
                    "networkidle",
                    timeout=min(10_000, timeout_ms),
                )
            except Exception:
                pass

            try:
                await page.wait_for_function(
                    """() => {
                        const t = document.body ? document.body.innerText : '';
                        return t.includes('Phase 1 in Progress') ||
                               t.includes('Phase 2 in Progress') ||
                               t.includes('Phase 3 in Progress');
                    }""",
                    timeout=min(12_000, timeout_ms),
                )
            except Exception:
                pass

            await page.wait_for_timeout(1000)

            try:
                raw_text = await page.locator("body").inner_text(timeout=5000)
            except Exception as exc:
                raise HTTPException(
                    status_code=502,
                    detail=f"Could not read rendered BMS body text: {type(exc).__name__}",
                ) from exc

            lines = []
            for raw in (raw_text or "").splitlines():
                line = " ".join(raw.split()).strip()
                if not line:
                    continue
                lines.append(line[:MAX_LINE_CHARS])
                if len(lines) >= MAX_LINES:
                    break

            phase_marker_count = sum(
                1
                for line in lines
                if line.lower().startswith("phase ")
                and line.lower().endswith(" in progress")
            ) + sum(
                1
                for line in lines
                if line.lower().startswith("registration")
            )

            return {
                "version": BMS_RENDER_VERSION,
                "sourceUrl": url,
                "finalUrl": page.url,
                "httpStatus": status,
                "lineCount": len(lines),
                "phaseMarkerCount": phase_marker_count,
                "lines": lines,
                "writeMode": "READ_ONLY",
            }

        finally:
            if context is not None:
                await context.close()
            await browser.close()
