"""Branch-only R1C comparator integration tests (no HTTP or Airtable writes).

Run in repository environment:
    python -m unittest discover -s tests -p 'test_programme_compare_r1c_v1.py'
"""
import unittest

# Use the same import order as the live Render service to avoid legacy import cycles.
import service_entrypoint  # noqa: F401

from shared_programme_grain_v1 import ProgrammeGrainHold
from programme_compare_r1c_v1 import (
    VerifiedCompareRequest, VerifiedSourceRow, compare_verified,
    preview_verified_worker,
)
from portfolio_discovery_extension_v11 import PortfolioSnapshotRow

SRC = "https://clinicaltrials.gov/study/NCT06303505"


def programme(code, label, setting="2L+"):
    return {
        "controlledIndicationId": code,
        "indication": label,
        "verified": True,
        "evidenceUrl": SRC,
        "treatmentSetting": setting,
    }


OVARIAN = programme("recQTqeeeQMyMKnOY", "Platinum-resistant ovarian cancer")
LUNG = programme("recqTQTf5vXD7yKrn", "Non-small cell lung cancer")


def request(ordered, existing=()):
    return VerifiedCompareRequest(
        company="Example Pharma", existingCandidateSourceIds=list(existing),
        existingCandidateInventoryComplete=True,
        existingCandidateExpectedCount=len(existing),
        existingCandidateInventory=[
            dict(discoveryCandidateId=f"existing-candidate-{i}", sourceRecordId=source_id)
            for i, source_id in enumerate(existing)
        ],
        approvedEvidenceHosts=["clinicaltrials.gov"],
        evidenceAttestations=[
            dict(sourceRecordId="sitecore-source-47", indication=p["indication"],
                 controlledIndicationId=p["controlledIndicationId"],
                 evidenceUrl=p["evidenceUrl"], treatmentSetting=p.get("treatmentSetting"),
                 reviewed=True, scopeVerified=True, assetVerified=True)
            for p in ordered
        ],
        sourceRows=[VerifiedSourceRow(
            company="Example Pharma", sourceFamily="Company Pipeline",
            sourceRecordId="sitecore-source-47", asset="GS-8824 / TUB-040",
            sponsorOwner="Example Pharma", programStatus="Active",
            sourceUrl="https://example.org/pipeline", phase="Phase 2",
            verifiedIndications=list(ordered),
        )],
        portfolioRows=[
            PortfolioSnapshotRow(
                recordId="recTOUCjUJMUhVjuq",
                company="Example Pharma", asset="GS-8824 / TUB-040",
                indication="Platinum-resistant ovarian cancer",
                controlledIndication="Platinum-resistant ovarian cancer",
                phase="Phase 1/2",
            ),
            PortfolioSnapshotRow(
                recordId="recD3oDxpTGvWbNSd",
                company="Example Pharma", asset="GS-8824 / TUB-040",
                indication="Non-small cell lung cancer",
                controlledIndication="Non-small cell lung cancer",
                phase="Phase 1/2",
            ),
        ],
    )


class VerifiedComparatorTest(unittest.TestCase):
    def test_two_candidates_and_existing_portfolio_matches(self):
        out = compare_verified(request([OVARIAN, LUNG]))
        self.assertTrue(out.readOnly)
        self.assertEqual(len(out.candidates), 2)
        self.assertEqual(
            {c["controlledIndicationId"] for c in out.candidates},
            {OVARIAN["controlledIndicationId"], LUNG["controlledIndicationId"]},
        )
        self.assertEqual(len({
            c["discoveryCandidateId"] for c in out.candidates
        }), 2)
        self.assertTrue(all(
            c["candidateStagingAction"] == "STAGE_NEW_CANDIDATE_FOR_REVIEW"
            for c in out.candidates
        ))
        self.assertTrue(all(not c["portfolioMasterWritesAllowed"] for c in out.candidates))

    def test_reorder_and_alias_preserves_candidate_ids(self):
        first = compare_verified(request([OVARIAN, LUNG]))
        second = compare_verified(request([LUNG, OVARIAN]))
        alias = programme(OVARIAN["controlledIndicationId"], "PROC ovarian carcinoma")
        third = compare_verified(request([alias, LUNG]))
        key = lambda out: sorted(c["discoveryCandidateId"] for c in out.candidates)
        self.assertEqual(key(first), key(second))
        self.assertEqual(key(first), key(third))

    def test_idempotent_replay(self):
        first = compare_verified(request([OVARIAN, LUNG]))
        existing = [c["sourceRecordId"] for c in first.candidates]
        second = compare_verified(request([LUNG, OVARIAN], existing))
        self.assertEqual(
            [c["candidateStagingAction"] for c in second.candidates],
            ["REUSE_EXISTING_CANDIDATE", "REUSE_EXISTING_CANDIDATE"],
        )

    def test_unverified_source_never_enters_new_candidate_staging(self):
        r = request([OVARIAN, LUNG])
        r.evidenceAttestations = []
        with self.assertRaisesRegex(ProgrammeGrainHold, "VERIFIED_PROGRAMME_EVIDENCE_REQUIRED"):
            compare_verified(r)

    def test_spoofed_evidence_host_is_held(self):
        r = request([OVARIAN, LUNG])
        r.evidenceAttestations[0]["evidenceUrl"] = "https://clinicaltrials.gov.evil.example/"
        with self.assertRaises(ProgrammeGrainHold):
            compare_verified(r)

    def test_incomplete_candidate_inventory_holds_before_comparison(self):
        r = request([OVARIAN])
        r.existingCandidateInventoryComplete = False
        with self.assertRaisesRegex(ProgrammeGrainHold, "COMPLETE_CANDIDATE_INVENTORY_REQUIRED"):
            compare_verified(r)

    def test_unkeyed_legacy_candidate_returns_hold_not_global_failure(self):
        r = request([OVARIAN])
        r.existingCandidateInventory = [
            dict(discoveryCandidateId="gilead-old-source", sourceRecordId="")
        ]
        r.existingCandidateExpectedCount = 1
        out = compare_verified(r)
        self.assertTrue(out.readOnly)
        self.assertEqual(
            [c["candidateStagingAction"] for c in out.candidates],
            ["HOLD_UNKEYED_LEGACY_CANDIDATE_REVIEW"],
        )
        self.assertTrue(all(not c["portfolioMasterWritesAllowed"]
                            for c in out.candidates))

    def test_mixed_unkeyed_history_reuses_only_exact_existing_candidate(self):
        first = compare_verified(request([OVARIAN, LUNG]))
        known = first.candidates[0]["sourceRecordId"]
        r = request([OVARIAN, LUNG], [known])
        r.existingCandidateInventory.append(dict(
            discoveryCandidateId="historic-unkeyed", sourceRecordId="",
        ))
        r.existingCandidateExpectedCount = 2
        out = compare_verified(r)
        actions = {c["sourceRecordId"]: c["candidateStagingAction"]
                   for c in out.candidates}
        self.assertEqual(actions[known], "REUSE_EXISTING_CANDIDATE")
        self.assertEqual(
            [a for key, a in actions.items() if key != known],
            ["HOLD_UNKEYED_LEGACY_CANDIDATE_REVIEW"],
        )

    def test_candidate_inventory_count_mismatch_fails_closed(self):
        r = request([OVARIAN])
        r.existingCandidateExpectedCount = 62
        with self.assertRaisesRegex(ProgrammeGrainHold, "CANDIDATE_INVENTORY_COUNT_MISMATCH"):
            compare_verified(r)

    def test_live_gilead_candidate_requires_independent_attestation(self):
        # Production Candidate source key: 5eb1e386-d42a-4627-ac3b-0f42f3e45c81.
        # A company pipeline row + existing Portfolio link cannot self-attest.
        r = request([OVARIAN])
        r.sourceRows[0].sourceRecordId = "5eb1e386-d42a-4627-ac3b-0f42f3e45c81"
        r.evidenceAttestations = []
        with self.assertRaisesRegex(ProgrammeGrainHold, "VERIFIED_PROGRAMME_EVIDENCE_REQUIRED"):
            compare_verified(r)

    def test_live_ionis_composite_candidate_stays_held(self):
        # The live Candidate is still keyed to owned:1769806455 and has two
        # existing Portfolio links. No split or Candidate creation is permitted.
        r = request([OVARIAN, LUNG], ["owned:1769806455"])
        r.sourceRows[0].sourceRecordId = "owned:1769806455"
        r.sourceRows[0].asset = "TRYNGOLZA (olezarsen)"
        for attestation in r.evidenceAttestations:
            attestation["sourceRecordId"] = "owned:1769806455"
        out = compare_verified(r)
        self.assertEqual(
            [c["candidateStagingAction"] for c in out.candidates],
            ["HOLD_LEGACY_PARENT_CANDIDATE_MIGRATION"] * 2,
        )

    def test_legacy_parent_collision_holds_without_global_failure(self):
        out = compare_verified(request([OVARIAN, LUNG], ["sitecore-source-47"]))
        self.assertTrue(out.readOnly)
        self.assertEqual(
            [c["candidateStagingAction"] for c in out.candidates],
            ["HOLD_LEGACY_PARENT_CANDIDATE_MIGRATION"] * 2,
        )
        self.assertTrue(all(not c["portfolioMasterWritesAllowed"]
                            for c in out.candidates))


class ReadOnlyWorkerCompatibilityTests(unittest.TestCase):
    """Future caller contract only; published Airtable worker is unchanged."""

    def test_gilead_one_to_many_and_missing_parent_evidence_do_not_mix(self):
        r = request([OVARIAN, LUNG])
        second = r.sourceRows[0].model_copy(
            update={"sourceRecordId": "gilead-second-unverified-parent"}
        )
        r.sourceRows.append(second)
        out = preview_verified_worker(r)
        self.assertTrue(out["readOnly"])
        self.assertFalse(out["productionWorkerIntegrated"])
        self.assertEqual(out["sourceRowCount"], 2)
        self.assertEqual(out["verifiedProgrammePreviewCount"], 2)
        self.assertEqual(out["parentHoldCount"], 1)
        self.assertEqual(out["parentResults"][0]["candidateCount"], 2)
        self.assertEqual(out["parentResults"][1]["result"], "HOLD")
        self.assertIn("VERIFIED_PROGRAMME_EVIDENCE_REQUIRED",
                      out["parentResults"][1]["holdReason"])
        self.assertEqual(out["candidateWrites"], 0)
        self.assertEqual(out["portfolioMasterWrites"], 0)
        self.assertEqual(out["sourceWatchWrites"], 0)
        self.assertEqual(out["queueWrites"], 0)
        self.assertTrue(all(
            not c["canWrite"] and
            c["portfolioLinkAction"] == "HOLD_FOR_INDEPENDENT_VERIFICATION"
            for p in out["parentResults"] for c in p["candidates"]
        ))

    def test_ionis_parent_collision_and_unkeyed_history_remain_row_held(self):
        r = request([OVARIAN, LUNG], ["owned:1769806455"])
        r.sourceRows[0].sourceRecordId = "owned:1769806455"
        r.sourceRows[0].asset = "TRYNGOLZA (olezarsen)"
        for item in r.evidenceAttestations:
            item["sourceRecordId"] = "owned:1769806455"
        second = r.sourceRows[0].model_copy(
            update={"sourceRecordId": "owned:other-programme"}
        )
        r.sourceRows.append(second)
        r.evidenceAttestations.append(dict(
            sourceRecordId="owned:other-programme",
            indication=OVARIAN["indication"],
            controlledIndicationId=OVARIAN["controlledIndicationId"],
            evidenceUrl=SRC, treatmentSetting="2L+",
            reviewed=True, scopeVerified=True, assetVerified=True,
        ))
        r.existingCandidateInventory.append(dict(
            discoveryCandidateId="ionis-unkeyed-history", sourceRecordId="",
        ))
        r.existingCandidateExpectedCount = 2
        out = preview_verified_worker(r)
        self.assertEqual(out["sourceRowCount"], 2)
        self.assertEqual(out["parentHoldCount"], 0)
        self.assertEqual(out["verifiedProgrammePreviewCount"], 3)
        actions = [[c["candidateStagingActionPreview"] for c in p["candidates"]]
                   for p in out["parentResults"]]
        self.assertEqual(actions[0], ["HOLD_LEGACY_PARENT_CANDIDATE_MIGRATION"] * 2)
        self.assertEqual(actions[1], ["HOLD_UNKEYED_LEGACY_CANDIDATE_REVIEW"])
        self.assertEqual(out["candidateWrites"], 0)

    def test_worker_preview_replay_reuses_existing_child_identity(self):
        first = preview_verified_worker(request([OVARIAN, LUNG]))
        ids = [c["sourceRecordId"] for c in first["parentResults"][0]["candidates"]]
        second = preview_verified_worker(request([LUNG, OVARIAN], ids))
        self.assertEqual(second["verifiedProgrammePreviewCount"], 2)
        self.assertEqual(
            [c["candidateStagingActionPreview"] for c
             in second["parentResults"][0]["candidates"]],
            ["REUSE_EXISTING_CANDIDATE"] * 2,
        )
        self.assertEqual(second["candidateWrites"], 0)

    def test_worker_preview_requires_complete_source_scoped_inventory(self):
        r = request([OVARIAN])
        r.existingCandidateInventoryComplete = False
        with self.assertRaisesRegex(
            ProgrammeGrainHold, "COMPLETE_CANDIDATE_INVENTORY_REQUIRED"
        ):
            preview_verified_worker(r)

    def test_worker_preview_rejects_duplicate_source_parent(self):
        r = request([OVARIAN])
        r.sourceRows.append(r.sourceRows[0].model_copy())
        with self.assertRaisesRegex(
            ProgrammeGrainHold, "DUPLICATE_OR_MISSING_PARENT_SOURCE_ID"
        ):
            preview_verified_worker(r)

    def test_worker_preview_rejects_empty_snapshot(self):
        r = request([OVARIAN])
        r.sourceRows = []
        with self.assertRaisesRegex(ProgrammeGrainHold, "SOURCE_ROWS_REQUIRED"):
            preview_verified_worker(r)


if __name__ == "__main__":
    unittest.main()
