"""Offline R5 opt-in retrieval integrity regressions. No external I/O or writes."""
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

# Match the production import order used by the Render adapter service.
import service_entrypoint  # noqa: F401
from html_fetch_extension import HtmlFetchResponse
from routed_html_extension import (
    _content_contract,
    _matched_content_markers,
    fetch_routed_html,
)

URL = "https://example.org/medicines"
MARKERS = "Product Alpha,Product Beta,Product Gamma"
NAV = ("Home About Contact Leadership News Investors Careers " * 35).strip()
CATALOGUE = NAV + " Product Alpha Product Beta Product Gamma " + NAV


def direct(text):
    return HtmlFetchResponse(
        version="DIRECT_V1", sourceUrl=URL, finalUrl=URL,
        httpStatus=200, contentType="text/html", bodyBytes=len(text),
        visibleTextLength=len(text), visibleText=text,
        headings=[], anchors=[],
    )


def browser(text):
    return dict(
        version="BROWSER_V1", sourceUrl=URL, finalUrl=URL,
        httpStatus=200, contentType="text/html", bodyBytes=len(text),
        visibleTextLength=len(text), visibleText=text,
        headings=[], anchors=[], transport="PLAYWRIGHT_CHROMIUM",
        retrievalMode="BROWSER_REQUIRED", routingReason="TEST_BROWSER_FALLBACK",
    )


class MarkerContractTests(unittest.TestCase):
    def test_compatibility_opt_out(self):
        self.assertEqual(_content_contract(None, 0), ([], 0))

    def test_missing_contract_fails_closed(self):
        with self.assertRaises(HTTPException) as cm:
            _content_contract(None, 2)
        self.assertEqual(cm.exception.status_code, 400)

    def test_duplicate_and_oversized_contracts_rejected(self):
        for value in ("ABC,abc", ",".join(f"Brand {i}" for i in range(13))):
            with self.subTest(value=value), self.assertRaises(HTTPException):
                _content_contract(value, 2)

    def test_minimum_cannot_exceed_number_of_configured_markers(self):
        with self.assertRaises(HTTPException):
            _content_contract("Product Alpha,Product Beta", 3)

    def test_marker_matches_are_distinct_and_word_bounded(self):
        content = dict(visibleText="Product Alpha and Product Beta. Product Alpha.",
                       headings=[], anchors=[])
        self.assertEqual(_matched_content_markers(content, ["Product Alpha", "Product Beta"]), 2)
        self.assertEqual(_matched_content_markers(
            dict(visibleText="Product AlphaPlus", headings=[], anchors=[]),
            ["Product Alpha"],
        ), 0)


class RouterIntegrityTests(unittest.IsolatedAsyncioTestCase):
    async def get(self, text, fallback, *, markers=MARKERS, min_hits=3):
        with patch("routed_html_extension._auth"), \
                patch("routed_html_extension._fetch_public_html",
                      new=AsyncMock(return_value=direct(text))) as get_direct, \
                patch("routed_html_extension._browser_payload",
                      new=AsyncMock(return_value=browser(fallback))) as get_browser:
            result = await fetch_routed_html(
                url=URL, timeout_seconds=35.0,
                x_adapter_key="test",
                required_content_terms=markers, min_required_hits=min_hits,
            )
            return result, get_direct.await_count, get_browser.await_count

    async def test_long_navigation_page_triggers_browser_when_opted_in(self):
        result, direct_count, browser_count = await self.get(NAV, CATALOGUE)
        self.assertEqual(result.retrievalMode, "BROWSER_REQUIRED")
        self.assertEqual(result.routingReason, "DIRECT_CONTENT_MARKERS_MISSING")
        self.assertEqual((direct_count, browser_count), (1, 1))

    async def test_navigation_only_fallback_is_a_hold(self):
        with self.assertRaises(HTTPException) as cm:
            await self.get(NAV, NAV)
        self.assertEqual(cm.exception.status_code, 502)
        self.assertIn("SOURCE_CONTENT_INTEGRITY_HOLD", str(cm.exception.detail))

    async def test_verified_direct_content_does_not_call_browser(self):
        result, direct_count, browser_count = await self.get(CATALOGUE, NAV)
        self.assertEqual(result.retrievalMode, "DIRECT")
        self.assertEqual((direct_count, browser_count), (1, 0))

    async def test_legacy_unconfigured_route_unchanged(self):
        # Explicitly records that the Airtable caller MUST opt in. The
        # existing non-contracted route continues to accept long HTML.
        result, direct_count, browser_count = await self.get(
            NAV, NAV, markers=None, min_hits=0,
        )
        self.assertEqual(result.retrievalMode, "DIRECT")
        self.assertEqual((direct_count, browser_count), (1, 0))


if __name__ == "__main__":
    unittest.main()
