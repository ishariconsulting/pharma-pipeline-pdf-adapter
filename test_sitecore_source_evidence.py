"""Offline integration tests for the opt-in Sitecore source-evidence handoff.

All sources are synthetic. No HTTP calls or Airtable writes are performed.
"""
import asyncio
import inspect
import json
import unittest
from unittest.mock import AsyncMock, patch

SOURCE_URL = "https://example.invalid/sxa/pipeline.json"


class _Response:
    status_code = 200
    url = SOURCE_URL

    def __init__(self, payload):
        self._payload = payload
        self.content = json.dumps(payload).encode("utf-8")

    def json(self):
        return self._payload


class _Client:
    def __init__(self, payload):
        self.response = _Response(payload)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url):
        return self.response


def _fixture():
    items = []
    for i in range(4):
        ref = ('<a href="https://clinicaltrials.gov/study/NCT01234567">Registry</a>'
               if i == 0 else '<span>NCT01234567</span>')
        h = (f'<div class="field-headbrandname">ASSET-{i+1}</div>'
             f'<div class="field-potentialindication">Synthetic disease {i+1}</div>'
             '<div class="phase-name">Phase 3</div>' + ref)
        items.append({"Id": f"key-{i+1}", "Html": h, "OtherPublisherMetadata": {"Ordinal": i}})
    return {"Count": 4, "Results": items}


class AdapterEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Use the supported existing import order (pre-existing AZ circular import).
        import service_entrypoint  # noqa: F401
        import sitecore_sxa_pipeline_extension as adapter
        cls.adapter = adapter

    def extract(self, include_source_evidence=False):
        fixture = _fixture()
        adapter = self.adapter
        with patch.object(adapter, "_assert_public_http_url", new_callable=AsyncMock), patch.object(
            adapter.httpx, "AsyncClient", side_effect=lambda **_: _Client(fixture)
        ):
            return asyncio.run(adapter.extract_sitecore_sxa(
                "Synthetic Pharma", SOURCE_URL, include_source_evidence=include_source_evidence))

    def test_default_rows_unchanged(self):
        res = self.extract()
        self.assertEqual(res.rowCount, 4)
        self.assertTrue(res.readyForDiscovery)
        for r in res.rows:
            self.assertNotIn("sourceEvidence", r)
            self.assertEqual(r["trialIds"], [])
            self.assertEqual(r["study"], "")
        self.assertEqual(res.guardrails["masterDataWrites"], False)

    def test_opt_in_keeps_original_item_without_promotion(self):
        res = self.extract(True)
        self.assertEqual(res.rowCount, 4)
        for i, r in enumerate(res.rows):
            evidence = r["sourceEvidence"]
            self.assertEqual(evidence["originalSourceItem"], _fixture()["Results"][i])
            self.assertEqual(evidence["sourceRecordId"], f"key-{i+1}")
            self.assertIsNone(evidence["sourceAsOf"])
            self.assertTrue(evidence["retrievedAt"].endswith("Z"))
            self.assertEqual(evidence["verificationGate"], "CAPTURED_UNVERIFIED")
            self.assertFalse(evidence["programmeToNctVerified"])
            self.assertFalse(evidence["focalArmVerified"])
            self.assertFalse(evidence["writeEligible"])
            self.assertEqual(r["trialIds"], [])
            self.assertEqual(r["study"], "")
        self.assertEqual(len(res.rows[0]["sourceEvidence"]["observedRegistryLinks"]), 1)
        for r in res.rows[1:]:
            self.assertEqual(r["sourceEvidence"]["observedRegistryLinks"], [])

    def test_route_has_off_by_default_parameter(self):
        p = inspect.signature(self.adapter.sitecore_route).parameters
        self.assertIn("include_source_evidence", p)
        self.assertIs(p["include_source_evidence"].default.default, False)


if __name__ == "__main__":
    unittest.main(verbosity=2)
