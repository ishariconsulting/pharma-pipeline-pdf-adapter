"""R1C shared multi-indication programme identity regressions.

Run: python -m unittest discover -s tests -p 'test_shared_programme_grain_v1.py'
All tests are offline and write zero records.
"""
import unittest

from shared_programme_grain_v1 import (
    CONTRACT_VERSION,
    ProgrammeGrainHold,
    candidate_action_plan,
    expand_verified_programmes,
)

URL = "https://clinicaltrials.gov/study/NCT06303505"


def variant(code, name, **context):
    return {
        "controlledIndicationId": code,
        "indication": name,
        "verified": True,
        "evidenceUrl": URL,
        **context,
    }


def source(*variants):
    return {
        "company": "Example Pharma", "sourceFamily": "Company Pipeline",
        "sourceRecordId": "source-card-47", "asset": "GS-8824 / TUB-040",
        "sourceUrl": "https://example.org/pipeline",
        "trialIds": ["NCT06303505"],
        "verifiedIndications": list(variants),
    }


OVARIAN = variant("recQTqeeeQMyMKnOY", "Platinum-resistant ovarian cancer",
                  treatmentSetting="2L+")
LUNG = variant("recqTQTf5vXD7yKrn", "Non-small cell lung cancer",
               treatmentSetting="2L+")


class ProgrammeIdentityTests(unittest.TestCase):
    def test_two_distinct_programmes_from_one_card(self):
        rows = expand_verified_programmes(source(OVARIAN, LUNG))
        self.assertEqual(len(rows), 2)
        self.assertEqual(len({x["sourceRecordId"] for x in rows}), 2)
        self.assertTrue(all(x["programmeGrainContract"] == CONTRACT_VERSION for x in rows))
        self.assertTrue(all(x["sourceParentRecordId"] == "source-card-47" for x in rows))
        self.assertTrue(all(x["trialIds"] == ["NCT06303505"] for x in rows))
        plan = candidate_action_plan(rows, set())
        self.assertEqual([p["action"] for p in plan],
                         ["STAGE_NEW_CANDIDATE_FOR_REVIEW"] * 2)

    def test_reversing_indication_order_is_idempotent(self):
        a = expand_verified_programmes(source(OVARIAN, LUNG))
        b = expand_verified_programmes(source(LUNG, OVARIAN))
        self.assertEqual(a, b)
        prior = {x["sourceRecordId"] for x in a}
        plan = candidate_action_plan(b, prior)
        self.assertEqual([p["action"] for p in plan],
                         ["REUSE_EXISTING_CANDIDATE"] * 2)

    def test_official_display_label_change_keeps_id(self):
        old = expand_verified_programmes(source(OVARIAN, LUNG))
        alias = variant("recQTqeeeQMyMKnOY", "PROC / ovarian carcinoma",
                        treatmentSetting="2L+")
        new = expand_verified_programmes(source(alias, LUNG))
        self.assertEqual({x["sourceRecordId"] for x in old},
                         {x["sourceRecordId"] for x in new})

    def test_one_existing_one_new(self):
        rows = expand_verified_programmes(source(OVARIAN, LUNG))
        plan = candidate_action_plan(rows, {rows[0]["sourceRecordId"]})
        self.assertEqual(sorted(p["action"] for p in plan),
                         ["REUSE_EXISTING_CANDIDATE",
                          "STAGE_NEW_CANDIDATE_FOR_REVIEW"])

    def test_separate_qualifiers_stay_separate(self):
        early = variant("recQTqeeeQMyMKnOY", "Ovarian cancer",
                        treatmentSetting="1L", formulation="IV")
        later = variant("recQTqeeeQMyMKnOY", "Ovarian cancer",
                        treatmentSetting="2L", formulation="IV")
        rows = expand_verified_programmes(source(early, later))
        self.assertEqual(len({r["sourceRecordId"] for r in rows}), 2)

    def test_legacy_source_is_not_silently_split(self):
        raw = {"sourceRecordId": "old-1", "asset": "Drug A",
               "indication": "Lung cancer; ovarian cancer"}
        self.assertEqual(expand_verified_programmes(raw), [raw])

    def test_legacy_parent_candidate_is_held_per_row(self):
        rows = expand_verified_programmes(source(OVARIAN, LUNG))
        plans = candidate_action_plan(rows, {"source-card-47"})
        self.assertEqual(
            [p["action"] for p in plans],
            ["HOLD_LEGACY_PARENT_CANDIDATE_MIGRATION"] * 2,
        )

    def test_legacy_parent_hold_does_not_suppress_independent_keyed_reuse(self):
        child = expand_verified_programmes(source(OVARIAN))[0]
        unrelated = dict(child, sourceRecordId="independent-keyed-row",
                         sourceParentRecordId="unrelated-parent")
        plans = candidate_action_plan(
            [child, unrelated], {"source-card-47", "independent-keyed-row"},
        )
        self.assertEqual(
            [p["action"] for p in plans],
            ["HOLD_LEGACY_PARENT_CANDIDATE_MIGRATION", "REUSE_EXISTING_CANDIDATE"],
        )

    def test_unkeyed_history_blocks_new_action_but_not_existing_reuse(self):
        rows = expand_verified_programmes(source(OVARIAN, LUNG))
        plans = candidate_action_plan(
            rows, {rows[0]["sourceRecordId"]}, unresolved_legacy_count=2,
        )
        self.assertEqual(
            [p["action"] for p in plans],
            ["REUSE_EXISTING_CANDIDATE", "HOLD_UNKEYED_LEGACY_CANDIDATE_REVIEW"],
        )

    def test_unverified_child_holds_entire_source(self):
        broken = dict(LUNG, verified=False)
        with self.assertRaisesRegex(ProgrammeGrainHold, "VERIFICATION"):
            expand_verified_programmes(source(OVARIAN, broken))

    def test_missing_canonical_identity_holds(self):
        bad = dict(OVARIAN)
        del bad["controlledIndicationId"]
        with self.assertRaisesRegex(ProgrammeGrainHold, "CONTROLLED_INDICATION"):
            expand_verified_programmes(source(OVARIAN, bad))

    def test_missing_official_evidence_holds(self):
        bad = dict(OVARIAN, evidenceUrl="")
        with self.assertRaisesRegex(ProgrammeGrainHold, "EVIDENCE"):
            expand_verified_programmes(source(bad, LUNG))

    def test_duplicate_programme_holds_not_double_creates(self):
        with self.assertRaisesRegex(ProgrammeGrainHold, "DUPLICATE_VERIFIED"):
            expand_verified_programmes(source(OVARIAN, OVARIAN))

    def test_comparator_id_replay_collision_holds(self):
        a = expand_verified_programmes(source(OVARIAN, LUNG))
        with self.assertRaisesRegex(ProgrammeGrainHold, "DUPLICATE_SOURCE"):
            candidate_action_plan(a + [a[0]], set())

    def test_programme_source_id_is_required(self):
        s = source(OVARIAN, LUNG)
        s["sourceRecordId"] = ""
        with self.assertRaisesRegex(ProgrammeGrainHold, "SOURCE_PARENT"):
            expand_verified_programmes(s)

    def test_combinations_are_not_split_by_plus(self):
        raw = {"sourceRecordId": "combo-1", "asset": "Drug A + Drug B",
               "indication": "Lung cancer"}
        self.assertEqual(expand_verified_programmes(raw), [raw])


if __name__ == "__main__":
    unittest.main()
