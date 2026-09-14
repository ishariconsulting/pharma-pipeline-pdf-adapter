"""Read-only network canary for alternate execution environments."""

from __future__ import annotations

import asyncio
import json

import httpx
from playwright.async_api import async_playwright


SOURCES = {
    "LILLY": "https://www.lilly.com/science/research-development/pipeline",
    "BAYER": "https://www.bayer.com/en/pharma/development-pipeline",
}


def emit(label: str, payload: dict) -> None:
    print(label, json.dumps(payload, sort_keys=True), flush=True)


async def direct_probe(name: str, url: str) -> dict:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True, headers=headers) as client:
            response = await client.get(url)
        text = response.text[:250_000]
        return {
            "name": name,
            "status": response.status_code,
            "finalUrl": str(response.url),
            "bytes": len(response.content),
            "hasPipeline": "pipeline" in text.lower(),
            "hasPhase": "phase" in text.lower(),
            "hasOrforglipron": "orforglipron" in text.lower(),
        }
    except Exception as exc:
        return {"name": name, "error": f"{type(exc).__name__}: {str(exc)[:500]}"}


async def browser_probe(name: str, url: str) -> dict:
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True, args=["--no-sandbox"])
            try:
                page = await browser.new_page(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"
                )
                response = await page.goto(url, wait_until="domcontentloaded", timeout=35_000)
                if response is None:
                    return {"name": name, "error": "no document response"}
                try:
                    await page.wait_for_load_state("networkidle", timeout=10_000)
                except Exception:
                    pass
                text = await page.locator("body").inner_text(timeout=5_000)
                return {
                    "name": name,
                    "status": response.status,
                    "finalUrl": page.url,
                    "visibleTextLength": len(text),
                    "hasPipeline": "pipeline" in text.lower(),
                    "hasPhase": "phase" in text.lower(),
                    "hasOrforglipron": "orforglipron" in text.lower(),
                }
            finally:
                await browser.close()
    except Exception as exc:
        return {"name": name, "error": f"{type(exc).__name__}: {str(exc)[:500]}"}


async def main() -> None:
    failures = 0
    for name, url in SOURCES.items():
        direct = await direct_probe(name, url)
        emit(f"NETWORK_DIRECT_{name}", direct)
        browser = await browser_probe(name, url)
        emit(f"NETWORK_BROWSER_{name}", browser)
        if browser.get("status") != 200 or browser.get("visibleTextLength", 0) < 800:
            failures += 1
    if failures:
        raise SystemExit(2)


if __name__ == "__main__":
    asyncio.run(main())
