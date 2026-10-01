"""Read-only regression for comparator responsiveness under concurrent staging.

This is deliberately local and requires no Airtable, Render or upstream calls.
"""
import asyncio
import threading
import time

from fastapi import HTTPException

import portfolio_discovery_extension_v11 as module


async def regression() -> None:
    original_auth = module._auth
    original_compare = module.compare_discovery
    original_timeout = module.COMPARE_WAIT_TIMEOUT_SECONDS
    entered = threading.Event()

    def slow_compare(request):
        entered.set()
        time.sleep(0.22)
        return {"company": request.company, "readOnly": True}

    request = module.DiscoveryCompareRequest(
        company="Concurrency Test Pharma",
        sourceRows=[],
        portfolioRows=[],
        batchRunId="COMPARE_CONCURRENCY_CANARY",
    )
    try:
        module._auth = lambda _header: None
        module.compare_discovery = slow_compare
        module.COMPARE_WAIT_TIMEOUT_SECONDS = 0.03

        first = asyncio.create_task(module.portfolio_discovery_compare(request, None))
        for _ in range(50):
            if entered.is_set():
                break
            await asyncio.sleep(0.005)
        assert entered.is_set(), "first comparison did not start"

        start = time.monotonic()
        try:
            await module.portfolio_discovery_compare(request, None)
        except HTTPException as exc:
            assert exc.status_code == 503
            assert exc.headers["Retry-After"] == str(module.COMPARE_RETRY_AFTER_SECONDS)
        else:
            raise AssertionError("overload must fail closed with HTTP 503")
        elapsed = time.monotonic() - start
        assert elapsed < 0.15, f"event loop was blocked for {elapsed:.3f}s"
        assert not first.done(), "first compare should still be running"
        result = await first
        assert result == {"company": request.company, "readOnly": True}

        # The busy request must not leak the semaphore: a subsequent request works.
        again = await module.portfolio_discovery_compare(request, None)
        assert again["readOnly"] is True

        def failing_compare(_request):
            raise ValueError("synthetic read-only comparison failure")

        module.compare_discovery = failing_compare
        try:
            await module.portfolio_discovery_compare(request, None)
        except ValueError:
            pass
        else:
            raise AssertionError("comparison failure must propagate")

        module.compare_discovery = lambda _request: {"recovered": True}
        assert (await module.portfolio_discovery_compare(request, None))["recovered"] is True
        print("PASS: event loop responsive, concurrent request 503, Retry-After present, slot released on failure")
    finally:
        module._auth = original_auth
        module.compare_discovery = original_compare
        module.COMPARE_WAIT_TIMEOUT_SECONDS = original_timeout


if __name__ == "__main__":
    asyncio.run(regression())
