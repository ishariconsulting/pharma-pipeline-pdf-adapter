"""Optional read-only startup canaries for the browser retrieval worker."""

import asyncio
import os

from browser_fetch_service import BAYER_CANARY_URL, LILLY_CANARY_URL, _run_canary


async def main() -> None:
    if os.getenv("RUN_BROWSER_CANARIES_ON_START", "").strip().lower() not in {"1", "true", "yes"}:
        return

    lilly = await _run_canary(LILLY_CANARY_URL, ["pipeline", "phase"])
    print("BROWSER_CANARY_LILLY", lilly, flush=True)
    bayer = await _run_canary(BAYER_CANARY_URL, ["pipeline", "phase"])
    print("BROWSER_CANARY_BAYER", bayer, flush=True)


if __name__ == "__main__":
    asyncio.run(main())
