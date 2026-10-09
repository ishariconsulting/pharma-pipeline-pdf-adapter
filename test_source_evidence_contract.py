"""Network-free, source-evidence safety checks; all input is synthetic."""
import copy
import unittest

from source_evidence_contract import original_item_evidence


class EvidenceContractTests(unittest.TestCase):
    def make(self, html="<div>Case</div>", **fields):
        row = {"Id": "opaque:stable-key", "Html": html, **fields}
        before = copy.deepcopy(row)
        evidence = original_item_evidence(row, source_record_id=row["Id"],
                                          official_url="https://official.example/pipeline",
                                          retrieved_at="2026-10-09T18:00:00Z",
                                          original_text="Case", stable_id_present=True)
        self.assertEqual(before, row)
        self.assertEqual(evidence["originalSourceItem"], before)
        self.assertFalse(evidence["programmeToNctVerified"])
        self.assertFalse(evidence["focalArmVerified"])
        self.assertFalse(evidence["writeEligible"])
        self.assertIsNone(evidence["sourceAsOf"])
        return evidence

    def test_original_item_round_trip_exact(self):
        x = self.make('<div class="field-headbrandname">Asset Q</div>', Date="2026-10-01", Nested={"a": ["x", 1]})
        self.assertEqual(x["originalSourceItem"]["Nested"]["a"], ["x", 1])

    def test_nested_source_mutation_cannot_change_preserved_item(self):
        item = {"Id": "key", "Html": "", "metadata": {"array": [1]}}
        saved = original_item_evidence(item, source_record_id="key",
                                       official_url="https://official.example/pipeline",
                                       retrieved_at="2026-10-09T18:00:00Z",
                                       original_text="", stable_id_present=True)
        item["metadata"]["array"].append(2)
        self.assertEqual(saved["originalSourceItem"]["metadata"]["array"], [1])

    def test_hash_canonical_even_when_input_order_changes(self):
        a = self.make("A", Foo=1)
        b = original_item_evidence({"Foo": 1, "Html": "A", "Id": "opaque:stable-key"},
                                   source_record_id="opaque:stable-key", official_url="https://official.example/pipeline",
                                   retrieved_at="2026-10-09T19:00:00Z", original_text="Case", stable_id_present=True)
        self.assertEqual(a["originalSourceItemSha256"], b["originalSourceItemSha256"])

    def test_exact_https_registry_link_observed_not_promoted(self):
        x = self.make('<a href="https://clinicaltrials.gov/study/NCT01234567">Trial</a>')
        self.assertEqual(x["observedRegistryLinks"], [
            {"nct": "NCT01234567", "url": "https://clinicaltrials.gov/study/NCT01234567",
             "status": "OBSERVED_LINK_NOT_VERIFIED"}])
        self.assertFalse(x["programmeToNctVerified"])

    def test_mention_is_not_a_link(self):
        x = self.make("<p>Clinical study NCT01234567</p>")
        self.assertEqual(x["observedRegistryLinks"], [])

    def test_host_spoof_http_and_unrelated_urls_ignored(self):
        x = self.make('<a href="https://clinicaltrials.gov.evil.test/study/NCT01234567">evil</a>'
                      '<a href="http://clinicaltrials.gov/study/NCT01234567">http</a>'
                      '<a href="https://clinicaltrials.gov/search?term=NCT01234567">search</a>')
        self.assertEqual(x["observedRegistryLinks"], [])

    def test_duplicate_link_is_one_observation(self):
        x = self.make('<a href="https://clinicaltrials.gov/ct2/show/NCT01234567">one</a>'
                      '<a href="https://clinicaltrials.gov/ct2/show/NCT01234567">two</a>')
        self.assertEqual(len(x["observedRegistryLinks"]), 1)

    def test_missing_stable_id_remains_flagged(self):
        x = original_item_evidence({"Html": "none"}, source_record_id="sxa:1",
                                   official_url="https://official.example/pipeline",
                                   retrieved_at="2026-10-09T18:00:00Z", original_text="none",
                                   stable_id_present=False)
        self.assertFalse(x["stableSourceRecordIdPresent"])
        self.assertFalse(x["writeEligible"])

    def test_asof_not_inferred_from_arbitrary_date(self):
        x = self.make("<p>Data as of October 2026</p>", Date="2026-10-01", LastUpdated="2026-10-09")
        self.assertIsNone(x["sourceAsOf"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
