"""Optional read-only startup diagnostics for the browser retrieval worker."""

import asyncio
import os
import hashlib

import httpx

from browser_fetch_service import BAYER_CANARY_URL, LILLY_CANARY_URL, _run_canary


TRUE_VALUES = {"1", "true", "yes"}


async def _probe(url: str) -> None:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/pdf,application/json;q=0.9,*/*;q=0.8",
    }
    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True, headers=headers) as client:
            response = await client.get(url)
        text = response.text[:200_000] if "text" in response.headers.get("content-type", "").lower() or "json" in response.headers.get("content-type", "").lower() else ""
        print(
            "RETRIEVAL_PROBE",
            {
                "url": url,
                "status": response.status_code,
                "finalUrl": str(response.url),
                "contentType": response.headers.get("content-type"),
                "bytes": len(response.content),
                "hasPipeline": "pipeline" in text.lower(),
                "hasPhase": "phase" in text.lower(),
                "hasOrforglipron": "orforglipron" in text.lower(),
            },
            flush=True,
        )
    except Exception as exc:
        print("RETRIEVAL_PROBE", {"url": url, "error": f"{type(exc).__name__}: {str(exc)[:500]}"}, flush=True)


async def main() -> None:
    key = os.getenv("BROWSER_FETCH_KEY", "")
    print(
        "BROWSER_KEY_FINGERPRINT",
        {
            "configured": bool(key),
            "sha256_12": hashlib.sha256(key.encode("utf-8")).hexdigest()[:12] if key else None,
            "length": len(key),
        },
        flush=True,
    )
    if os.getenv("RUN_BROWSER_PROBES_ON_START", "").strip().lower() in TRUE_VALUES:
        for url in [
            LILLY_CANARY_URL,
            f"{LILLY_CANARY_URL}.plain.html",
            f"{LILLY_CANARY_URL}.json",
            "https://www.lilly.com/science",
            "https://www.bayer.com/sites/default/files/ph-rd-pipeline-2026-07-21-final-updated.pdf",
        ]:
            await _probe(url)

    if os.getenv("RUN_BROWSER_CANARIES_ON_START", "").strip().lower() not in TRUE_VALUES:
        return

    lilly = await _run_canary(LILLY_CANARY_URL, ["pipeline", "phase"])
    print("BROWSER_CANARY_LILLY", lilly, flush=True)
    bayer = await _run_canary(BAYER_CANARY_URL, ["pipeline", "phase"])
    print("BROWSER_CANARY_BAYER", bayer, flush=True)

    extra_canaries = [
        ("ABBVIE", "https://www.abbvie.com/science/pipeline.html", ["pipeline"]),
        ("VERVE", "https://www.vervetx.com/our-programs/our-pipeline", ["pipeline"]),
        ("BOEHRINGER", "https://www.boehringer-ingelheim.com/science-innovation/human-health-innovation/pipeline", ["pipeline"]),
        ("SOBI", "https://www.sobi.com/en/pipeline", ["pipeline", "phase"]),
    ]
    for label, url, terms in extra_canaries:
        result = await _run_canary(url, terms)
        print(f"BROWSER_CANARY_{label}", result, flush=True)


if __name__ == "__main__":
    asyncio.run(main())
