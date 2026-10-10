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

    def test_legacy_parent_collision_holds(self):
        with self.assertRaisesRegex(ProgrammeGrainHold, "MIGRATION_REQUIRED"):
            compare_verified(request([OVARIAN, LUNG], ["sitecore-source-47"]))


if __name__ == "__main__":
    unittest.main()
