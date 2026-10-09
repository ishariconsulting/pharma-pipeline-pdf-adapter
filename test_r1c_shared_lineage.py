"""Synthetic safety regressions, NOT observations of Gilead/Airtable records.

All record IDs, protocol assertions, assets and snapshot state are invented test
fixtures. The real six-case manifest supplies names/NCTs only and no source keys.
"""
from copy import deepcopy
import json
import unittest

from r1c_shared_lineage import Snapshot, scope_reasons, validate


def fixture():
    """One explicitly synthetic, fully scoped, reciprocal positive relationship."""
    provenance = dict(url="https://example.invalid/pipeline", sourceRecordId="fixture-row",
                      asOf="2026-10-01", retrievedAt="2026-10-09T00:00:00Z",
                      version="synthetic-v1", authorityId="fixture-pipeline-authority",
                      originalText="SYNTHETIC TEST EVIDENCE ONLY")
    scope = dict(components=["fixture-component-a"], indication="Example disease", line="4L+",
                 population="fixture-population", setting="fixture-setting", route="IV",
                 dose="fixture-dose", companyRole="owner", roleProof="synthetic-role-proof",
                 proofReferences={k: "synthetic-proof-" + k for k in
                                  ("components", "indication", "line", "population", "setting", "route", "dose")})
    comparison = dict(company="Example Pharma", sourceFamily="Company Pipeline",
                      sourceRecordId=provenance["sourceRecordId"], sourceUrl=provenance["url"],
                      sourceWatchRecordId="fixture-watch", asset="ALPHAMAB", molecule="alphamab",
                      indication="Example disease", phase="Phase 3", ownershipResolved=True)
    ct = {**provenance, "url": "https://clinicaltrials.gov/study/NCT00000001",
          "authorityId": "NCT00000001", "sourceRecordId": "fixture-arm"}
    arm_comparison = {**comparison, "sourceRecordId": ct["sourceRecordId"], "sourceUrl": ct["url"],
                      "sourceFamily": "ClinicalTrials.gov"}
    return dict(schemaVersion="R1C_SNAPSHOT_V1", snapshotId="SYNTHETIC-NOT-GILEAD",
                capturedAt="2026-10-09T00:00:00Z", company="Example Pharma", companyAliases=[],
                relatedCompanies=[], sourceWatchRecordId="fixture-watch", expectedSourceCount=1,
                expectedDispositionCounts={"MATCHED": 1}, scopeDescription="Synthetic unit-test closure only",
                completeTables=["sources", "candidates", "portfolio", "trials", "arms", "relations", "evidence", "landscape"],
                sources=[dict(stableKey="opaque-fixture-key", sourceWatchRecordId="fixture-watch",
                              company="Example Pharma", adapterVersion="synthetic-adapter", parserVersion="synthetic-parser", granularity="programme",
                              provenance=provenance, comparison=comparison, scope=scope,
                              baselineDisposition="MATCHED", baselineReason="", baselineProof="synthetic-R1A",
                              assessedFamilies=["PIPELINE", "TRIAL_REGISTRY"], relationIds=["fixture-relation"],
                              trialReferences={"NCT00000001": "synthetic-official-trial-relationship"})],
                candidates=[dict(recordId="fixture-candidate", stableKey="opaque-fixture-key",
                                 sourceWatchRecordId="fixture-watch", sourceRecordId="fixture-row",
                                 company="Example Pharma", active=True, reviewStatus="Resolved",
                                 sourceVersion="synthetic-v1", sourceGranularity="programme",
                                 programmeGate="Verified", discoveryClassification="MATCHED", holdReason="",
                                 portfolioIds=["fixture-portfolio"], queueEligible=False, portfolioWriteEligible=False)],
                portfolio=[dict(recordId="fixture-portfolio", company="Example Pharma",
                                comparison=dict(recordId="fixture-portfolio", company="Example Pharma", asset="ALPHAMAB",
                                                molecule="alphamab", indication="Example disease", phase="Phase 3"),
                                scope=scope, candidateIds=["fixture-candidate"], landscapeIds=["fixture-tl"],
                                trialIds=["fixture-trial"], evidenceFamilies=[], crossSourceStatus=None)],
                trials=[dict(recordId="fixture-trial", nct="NCT00000001", studyName="Synthetic study",
                             status="Synthetic active", provenance=ct, portfolioIds=["fixture-portfolio"], armIds=["fixture-arm"])],
                arms=[dict(recordId="fixture-arm", trialRecordId="fixture-trial", nct="NCT00000001", armRef="Synthetic arm A",
                           interventionRole="experimental", comparison=arm_comparison, scope=scope, provenance=ct)],
                relations=[dict(recordId="fixture-relation", stableKey="opaque-fixture-key", portfolioId="fixture-portfolio",
                                relationType="CANONICAL_PROGRAMME", sharedStudyIdentity="NCT00000001",
                                companyRoleProof="synthetic-relation-role", sourceComparison=comparison, sourceScope=scope,
                                sourceProvenance=provenance, sourceProjectionVerified=True,
                                sourceProjectionProof="synthetic-official-scope-assertion", evidenceIds=["fixture-evidence"])],
                evidence=[dict(recordId="fixture-evidence", family="TRIAL_REGISTRY", portfolioIds=["fixture-portfolio"],
                               provenance=ct, armId="fixture-arm", comparison=arm_comparison, scope=scope,
                               jurisdiction=None, independent=True, verified=True)],
                landscape=[dict(recordId="fixture-tl", portfolioIds=["fixture-portfolio"], comparison=arm_comparison,
                                scope=scope, market="fixture-market", provenance=ct,
                                confidence="High", readiness="Ready", lastVerified="2026-09-03")],
                cases=[dict(name="Synthetic case", sourceKeys=["opaque-fixture-key"], expectedNcts=["NCT00000001"],
                            expectedPortfolioIds=["fixture-portfolio"], expectedLandscapeIds=["fixture-tl"],
                            expectedDisposition="SUPPORTED_EXACT", oracleProvenance="synthetic-oracle")])


def run(data):
    return validate(Snapshot.model_validate(deepcopy(data)))


class SafetyTests(unittest.TestCase):
    def setUp(self):
        # Break any shared dictionaries inside fixture construction before mutation.
        self.data = json.loads(json.dumps(fixture()))

    def held(self, code=None):
        result = run(self.data)
        row = result["rows"][0]
        self.assertNotEqual(row["disposition"], "SUPPORTED_EXACT")
        self.assertFalse(row["portfolioWriteEligible"])
        self.assertFalse(row["queueEligible"])
        if code:
            self.assertIn(code, row["reasonCodes"])
        return result


    def test_observed_gilead_six_identity_preflight_never_promotes(self):
        # These named input fields were inspected read-only from the existing
        # Gilead Candidate and Portfolio records on 9 October 2026.
        # They prove only identity candidates, NOT focal arms or full R1C.
        targets = [
            {"recordId": "recJ6Gw3qoSQRi2x9", "asset": "Anito-cel", "molecule": "anitocabtagene autoleucel"},
            {"recordId": "recSPdCh4UJgdQVGd", "asset": "Anito-cel", "molecule": "anitocabtagene autoleucel"},
            {"recordId": "recAMZGRRM6BC0Haq", "asset": "Islatravir + lenacapavir", "molecule": "islatravir + lenacapavir"},
            {"recordId": "recOx6PWK0MJ4rJHy", "asset": "Islatravir/Lenacapavir", "molecule": "islatravir/lenacapavir"},
            {"recordId": "recD3oDxpTGvWbNSd", "asset": "GS-8824 / TUB-040", "molecule": "NaPi2b-directed topoisomerase-I ADC"},
            {"recordId": "recTOUCjUJMUhVjuq", "asset": "GS-8824 / TUB-040", "molecule": "NaPi2b-directed topoisomerase-I ADC"},
            {"recordId": "recBiCP8FUS5E4qBG", "asset": "KITE-753", "molecule": "bicistronic CD19/CD20 autologous CAR T"},
            {"recordId": "recnTXAC84OeTnZp0", "asset": "BIXLENVO", "molecule": "bictegravir/lenacapavir"},
            {"recordId": "recPzHmWJVzevncvC", "asset": "IDVYNSO", "molecule": "doravirine / islatravir"},
        ]
        cases = [
            ("iMMagine-1", "Anitocabtagene autoleucel (iMMagine-1)",
             ["recJ6Gw3qoSQRi2x9", "recSPdCh4UJgdQVGd"]),
            ("iMMagine-3", "Anitocabtagene autoleucel (iMMagine-3)",
             ["recJ6Gw3qoSQRi2x9", "recSPdCh4UJgdQVGd"]),
            ("ISLEND-1/2", "Islatravir/lenacapavir oral combination (ISLEND-1 & ISLEND-2)",
             ["recAMZGRRM6BC0Haq", "recOx6PWK0MJ4rJHy"]),
            ("NAPISTAR 1-01", "NaPi2b ADC (GS-8824) (NAPISTAR 1-01)",
             ["recD3oDxpTGvWbNSd", "recTOUCjUJMUhVjuq"]),
            ("PALISADES-1", "CD19/CD20 bicistronic (KITE-753) (PALISADES-1)",
             ["recBiCP8FUS5E4qBG"]),
            ("ARTISTRY-1/2", "Bictegravir/lenacapavir oral combination (ARTISTRY-1 & ARTISTRY-2)",
             ["recnTXAC84OeTnZp0"]),
        ]
        from r1c_shared_lineage import identity_preflight
        for name, asset, expected in cases:
            with self.subTest(programme=name):
                source = {"asset": asset, "developmentCode": "CD19" if name == "PALISADES-1" else ""}
                assessment = identity_preflight(source, targets)
                self.assertEqual(sorted(row["recordId"] for row in assessment["assetIdentityCandidates"]),
                                 sorted(expected))
                self.assertEqual(assessment["programmeIdentity"], "NOT_ASSESSED")
                self.assertFalse(assessment["autoLink"])
                self.assertFalse(assessment["portfolioWriteEligible"])
                self.assertFalse(assessment["queueEligible"])

    def test_cross_field_identity_negative_controls_fail_closed(self):
        from r1c_shared_lineage import identity_methods
        negatives = [
            ("CD19 target", {"asset": "CD19", "developmentCode": "CD19"}, {"asset": "KITE-753"}),
            ("different CAR-T code", {"asset": "KITE-363"}, {"asset": "KITE-753"}),
            ("wrong regimen partner", {"asset": "doravirine/islatravir"}, {"molecule": "islatravir/lenacapavir"}),
            ("single component", {"asset": "lenacapavir"}, {"molecule": "islatravir/lenacapavir"}),
            ("study label", {"asset": "Anitocabtagene autoleucel (iMMagine-3)"}, {"asset": "iMMagine-3"}),
            ("partial regimen", {"asset": "bictegravir/lenacapavir"}, {"asset": "bictegravir"}),
            ("target biomarker", {"asset": "CD19/CD20 bicistronic (KITE-753)"}, {"asset": "CD19"}),
            ("nonidentical code", {"asset": "NaPi2b ADC (GS-8824)"}, {"asset": "GS-8825"}),
            ("additional regimen component", {"asset": "islatravir + lenacapavir"},
             {"molecule": "islatravir + lenacapavir + doravirine"}),
        ]
        for name, source, target in negatives:
            with self.subTest(control=name):
                self.assertEqual(identity_methods(source, target), [])

    def test_shared_sitecore_parser_prefer_drug_code_over_biomarker(self):
        # Generic extraction rule; neither the function nor production parser
        # contains a Gilead-specific conditional.
        import service_entrypoint  # noqa: F401
        from sitecore_sxa_pipeline_extension import identity_parts
        self.assertEqual(
            identity_parts("CD19/CD20 bicistronic (KITE-753) (PALISADES-1)")["developmentCode"],
            "KITE-753")
        self.assertEqual(identity_parts("CD19/CD20 directed CAR T")["developmentCode"], "")
        self.assertEqual(identity_parts("NaPi2b ADC (GS-8824)")["developmentCode"], "GS-8824")

    def test_positive_and_replay_without_mutation(self):
        before = deepcopy(self.data)
        a, b = run(self.data), run(self.data)
        self.assertEqual(a, b)
        self.assertEqual(before, self.data)
        self.assertEqual(a["status"], "PASS")
        self.assertEqual(a["rows"][0]["independentSourceCount"], 2)
        self.assertEqual(a["rows"][0]["familyStatus"]["REGULATORY"], "NOT_ASSESSED")
        self.assertNotIn("TREATMENT_LANDSCAPE", a["downstreamImpacts"][0]["derivedEvidenceFamilies"])

    def test_unverified_history_preserves_evidence_but_never_passes(self):
        self.data["sources"][0].update(baselineDisposition="UNVERIFIED",
                                       baselineReason="", baselineProof="")
        self.data["cases"][0]["expectedDisposition"] = "SUPPORTED_RELATIONSHIP_WITH_SCOPE_HOLD"
        before = deepcopy(self.data)
        r = run(self.data)
        self.assertEqual(r["rows"][0]["relations"][0]["readOnlyEvidenceAssessment"],
                         "SUPPORTED_FOR_READ_ONLY_REVIEW")
        self.assertIn("R1A_HISTORICAL_DISPOSITION_UNVERIFIED", r["rows"][0]["reasonCodes"])
        self.assertEqual(r["rows"][0]["status"], "HOLD")
        self.assertEqual(r["cases"][0]["status"], "HOLD")
        self.assertEqual(r["status"], "HOLD")
        self.assertEqual(r["historicalDispositionCoverage"]["unverifiedPerKey"], 1)
        self.assertEqual(r["historicalDispositionCoverage"]["recordedPerKey"], 0)
        self.assertEqual(r["historicalDispositionCoverage"]["reportedR1AAggregate"], {"MATCHED": 1})
        self.assertEqual(r["historicalDispositionCoverage"]["historicalKeyedReplay"],
                         "NOT_REPLAYED_PARTIAL_EVIDENCE")
        self.assertFalse(r["rows"][0]["queueEligible"])
        self.assertFalse(r["rows"][0]["portfolioWriteEligible"])
        self.assertEqual(self.data, before)

    def test_unverified_history_preserves_missing_focal_arm_hold(self):
        self.data["sources"][0].update(baselineDisposition="UNVERIFIED", baselineProof="")
        self.data["arms"] = []
        self.data["trials"][0]["armIds"] = []
        self.data["cases"][0]["expectedDisposition"] = "SUPPORTED_RELATIONSHIP_WITH_SCOPE_HOLD"
        r = run(self.data)
        rel = r["rows"][0]["relations"][0]
        self.assertEqual(rel["readOnlyEvidenceAssessment"], "EVIDENCE_HELD")
        self.assertIn("NCT_WITHOUT_FOCAL_ARM_PROOF", rel["evidenceReasonCodes"])
        self.assertEqual(r["rows"][0]["status"], "HOLD")
        self.assertEqual(r["cases"][0]["status"], "HOLD")
        self.assertEqual(r["status"], "HOLD")
        self.assertFalse(r["rows"][0]["portfolioWriteEligible"])

    def test_missing_source_as_of_is_not_fabricated(self):
        self.data["sources"][0]["provenance"]["asOf"] = ""
        self.data["relations"][0]["sourceProvenance"]["asOf"] = ""
        self.data["cases"][0]["expectedDisposition"] = "SUPPORTED_RELATIONSHIP_WITH_SCOPE_HOLD"
        r = run(self.data)
        self.assertIn("MISSING_PROVENANCE_ASOF", r["rows"][0]["reasonCodes"])
        self.assertEqual(r["rows"][0]["status"], "HOLD")
        self.assertEqual(r["status"], "HOLD")

    def test_known_historical_disposition_requires_real_proof(self):
        self.data["sources"][0]["baselineProof"] = ""
        r = run(self.data)
        self.assertIn("MISSING_R1A_DISPOSITION_PROOF", r["rows"][0]["reasonCodes"])
        self.assertEqual(r["status"], "FAIL")
        self.assertFalse(r["rows"][0]["portfolioWriteEligible"])

    def synthetic_partial_history_53(self):
        """Entirely invented fixtures: 20 keyed NEW, 33 unknown; not Gilead data."""
        template = fixture()
        self.data["sources"] = []
        self.data["candidates"] = []
        for table in ("portfolio", "trials", "arms", "relations", "evidence", "landscape", "cases"):
            self.data[table] = []
        self.data["expectedSourceCount"] = 53
        self.data["expectedDispositionCounts"] = {"MATCHED": 11, "HELD": 16, "NEW": 26}
        for i in range(53):
            source, candidate = deepcopy(template["sources"][0]), deepcopy(template["candidates"][0])
            key, source_id = "SYNTHETIC-KEY-" + str(i), "SYNTHETIC-ROW-" + str(i)
            source["stableKey"] = key
            source["provenance"]["sourceRecordId"] = source_id
            source["comparison"]["sourceRecordId"] = source_id
            source["baselineDisposition"] = "NEW" if i < 20 else "UNVERIFIED"
            source["baselineProof"] = "synthetic-new-proof" if i < 20 else ""
            source["relationIds"], source["trialReferences"] = [], {}
            candidate.update(recordId="SYNTHETIC-CANDIDATE-" + str(i), stableKey=key,
                             sourceRecordId=source_id, portfolioIds=[],
                             reviewStatus="New", programmeGate="Unassessed")
            self.data["sources"].append(source)
            self.data["candidates"].append(candidate)

    def test_20_new_33_unverified_never_replay_historical_aggregate(self):
        self.synthetic_partial_history_53()
        before = deepcopy(self.data)
        r = run(self.data)
        self.assertEqual(r["status"], "HOLD")
        self.assertEqual(r["testedSourceKeys"], 53)
        self.assertEqual(r["sourceCoverage"]["activeCandidateAddressable"], 53)
        self.assertEqual(r["historicalDispositionCoverage"]["verifiedPerKeyCounts"], {"NEW": 20})
        self.assertEqual(r["historicalDispositionCoverage"]["unverifiedPerKey"], 33)
        self.assertEqual(r["historicalDispositionCoverage"]["historicalKeyedReplay"],
                         "NOT_REPLAYED_PARTIAL_EVIDENCE")
        self.assertNotIn("R1A_DISPOSITION_TOTAL_MISMATCH", r["issues"])
        self.assertTrue(all(row["status"] == "HOLD" for row in r["rows"]))
        self.assertTrue(all(not row["queueEligible"] and not row["portfolioWriteEligible"]
                            for row in r["rows"]))
        self.assertEqual(self.data, before)

    def test_partial_historical_disposition_overcount_fails(self):
        self.synthetic_partial_history_53()
        self.data["expectedDispositionCounts"]["NEW"] = 19
        r = run(self.data)
        self.assertEqual(r["status"], "FAIL")
        self.assertIn("R1A_PARTIAL_DISPOSITION_OVERCOUNT", r["issues"])

    def test_unlinked_proposal_can_be_evidence_supported_without_pass(self):
        self.data["candidates"][0]["portfolioIds"] = []
        self.data["portfolio"][0]["candidateIds"] = []
        # The positive fixture's original SUPPORTED_EXACT oracle is deliberately
        # stale after removing both persisted links. It must still fail closed.
        stale = run(self.data)
        self.assertEqual(stale["status"], "FAIL")
        self.assertIn("CASE_DISPOSITION_DIFFERS_FROM_ORACLE", stale["cases"][0]["reasonCodes"])
        # The independent oracle for this unlinked synthetic scenario is HOLD,
        # not the positive linked fixture's SUPPORTED_EXACT.
        self.data["cases"][0]["expectedDisposition"] = "HELD_AMBIGUOUS"
        before = deepcopy(self.data)
        r = run(self.data)
        relation = r["rows"][0]["relations"][0]
        self.assertEqual(relation["readOnlyEvidenceAssessment"], "SUPPORTED_FOR_READ_ONLY_REVIEW")
        self.assertEqual(relation["evidenceReasonCodes"], [])
        self.assertEqual(relation["persistedLinkageAssessment"], "NOT_PERSISTED")
        self.assertIn("NO_PERSISTED_CANDIDATE_CANONICAL_LINK", relation["persistenceReasonCodes"])
        self.assertNotIn("NO_PERSISTED_CANDIDATE_CANONICAL_LINK", relation["evidenceReasonCodes"])
        self.assertEqual(r["rows"][0]["status"], "HOLD")
        self.assertEqual(r["status"], "HOLD")
        self.assertEqual(r["cases"][0]["status"], "HOLD")
        self.assertFalse(r["rows"][0]["queueEligible"])
        self.assertFalse(r["rows"][0]["portfolioWriteEligible"])
        self.assertEqual(before, self.data)

    def test_unlinked_proposal_scope_conflict_cannot_be_supported(self):
        self.data["candidates"][0]["portfolioIds"] = []
        self.data["portfolio"][0]["candidateIds"] = []
        self.data["arms"][0]["scope"]["line"] = "2L"
        relation = run(self.data)["rows"][0]["relations"][0]
        self.assertEqual(relation["readOnlyEvidenceAssessment"], "EVIDENCE_HELD")
        self.assertIn("CONFLICT_LINE", relation["evidenceReasonCodes"])

    def test_unlinked_proposal_parent_trial_is_not_focal_arm_proof(self):
        self.data["candidates"][0]["portfolioIds"] = []
        self.data["portfolio"][0]["candidateIds"] = []
        self.data["arms"] = []
        self.data["trials"][0]["armIds"] = []
        relation = run(self.data)["rows"][0]["relations"][0]
        self.assertEqual(relation["readOnlyEvidenceAssessment"], "EVIDENCE_HELD")
        self.assertIn("NCT_WITHOUT_FOCAL_ARM_PROOF", relation["evidenceReasonCodes"])

    def test_unlinked_proposal_without_official_source_nct_proof_holds(self):
        self.data["candidates"][0]["portfolioIds"] = []
        self.data["portfolio"][0]["candidateIds"] = []
        self.data["sources"][0]["trialReferences"] = {}
        relation = run(self.data)["rows"][0]["relations"][0]
        self.assertEqual(relation["readOnlyEvidenceAssessment"], "EVIDENCE_HELD")
        self.assertIn("OFFICIAL_SOURCE_NCT_RELATION_UNPROVEN", relation["evidenceReasonCodes"])

    def test_r1a_held_with_unlinked_proposal_does_not_promote(self):
        self.data["candidates"][0]["portfolioIds"] = []
        self.data["portfolio"][0]["candidateIds"] = []
        self.data["sources"][0].update(baselineDisposition="HELD", baselineReason="Unresolved grain")
        self.data["expectedDispositionCounts"] = {"HELD": 1}
        r = run(self.data)
        self.assertEqual(r["rows"][0]["relations"][0]["readOnlyEvidenceAssessment"], "SUPPORTED_FOR_READ_ONLY_REVIEW")
        self.assertIn("R1A_HELD_PRESERVED:Unresolved grain", r["rows"][0]["reasonCodes"])
        self.assertEqual(r["rows"][0]["status"], "HOLD")
        self.assertFalse(r["rows"][0]["queueEligible"])
        self.assertFalse(r["rows"][0]["portfolioWriteEligible"])

    def test_one_sided_candidate_link_is_integrity_failure_not_evidence_failure(self):
        self.data["portfolio"][0]["candidateIds"] = []
        r = run(self.data)
        relation = r["rows"][0]["relations"][0]
        self.assertEqual(relation["readOnlyEvidenceAssessment"], "SUPPORTED_FOR_READ_ONLY_REVIEW")
        self.assertEqual(relation["persistedLinkageAssessment"], "NONRECIPROCAL")
        self.assertEqual(r["status"], "FAIL")
        self.assertFalse(r["rows"][0]["portfolioWriteEligible"])

    def test_missing_candidate(self):
        self.data["candidates"] = []
        self.held("ACTIVE_CANDIDATE_COUNT_0")

    def test_duplicate_active_candidate(self):
        other = deepcopy(self.data["candidates"][0]); other["recordId"] = "duplicate"
        self.data["candidates"].append(other)
        self.held("ACTIVE_CANDIDATE_COUNT_2")

    def test_superseded_only(self):
        self.data["candidates"][0]["active"] = False
        self.data["candidates"][0]["reviewStatus"] = "Superseded"
        self.held("ACTIVE_CANDIDATE_COUNT_0")

    def test_historical_candidate_does_not_break_active_identity(self):
        other = deepcopy(self.data["candidates"][0])
        other.update(recordId="history", active=False, reviewStatus="Superseded", portfolioIds=[])
        self.data["candidates"].append(other)
        self.assertEqual(run(self.data)["status"], "PASS")

    def test_r1a_held_is_not_promoted_by_new_positive_evidence(self):
        self.data["sources"][0].update(baselineDisposition="HELD", baselineReason="Programme grain unresolved")
        self.data["expectedDispositionCounts"] = {"HELD": 1}
        self.held("R1A_HELD_PRESERVED:Programme grain unresolved")

    def test_new_excluded_discovery_candidate_is_not_promoted(self):
        self.data["sources"][0].update(baselineDisposition="NEW", relationIds=[])
        self.data["expectedDispositionCounts"] = {"NEW": 1}
        self.data["relations"] = []
        self.data["candidates"][0].update(discoveryClassification="EXCLUDED BY RULE",
                                          portfolioIds=[], programmeGate="Unassessed", reviewStatus="New")
        self.data["portfolio"][0]["candidateIds"] = []
        self.held("R1A_NEW_NOT_PROMOTED")

    def test_parent_nct_without_arm(self):
        self.data["arms"] = []
        self.data["trials"][0]["armIds"] = []
        self.held("NCT_WITHOUT_FOCAL_ARM_PROOF")

    def test_line_mismatch(self):
        self.data["arms"][0]["scope"]["line"] = "2L"
        self.held("CONFLICT_LINE")

    def test_unproved_prior_line_conversion(self):
        self.data["arms"][0]["scope"]["line"] = "1-3 prior lines"
        self.data["arms"][0]["scope"]["proofReferences"]["line"] = ""
        self.held("UNPROVEN_LINE")

    def test_population_mismatch(self):
        self.data["arms"][0]["scope"]["population"] = "different-population"
        self.held("CONFLICT_POPULATION")

    def test_comparator_leakage(self):
        self.data["arms"][0]["interventionRole"] = "comparator"
        self.held("NON_FOCAL_INTERVENTION_ROLE")

    def test_placebo_leakage(self):
        self.data["arms"][0]["interventionRole"] = "placebo"
        self.held("NON_FOCAL_INTERVENTION_ROLE")

    def test_background_and_supportive_drugs(self):
        for role in ("background", "supportive"):
            with self.subTest(role=role):
                self.data["arms"][0]["interventionRole"] = role
                self.held("NON_FOCAL_INTERVENTION_ROLE")

    def test_single_vs_combination(self):
        self.data["arms"][0]["scope"]["components"].append("fixture-component-b")
        self.held("CONFLICT_COMPONENTS")

    def test_indication_mismatch(self):
        self.data["arms"][0]["scope"]["indication"] = "platinum-sensitive"
        self.held("CONFLICT_INDICATION")

    def test_combination_arm_leakage(self):
        self.data["arms"][0]["comparison"]["asset"] = "ALPHAMAB + BETAMAB"
        self.data["arms"][0]["comparison"]["molecule"] = "alphamab + betamab"
        self.data["arms"][0]["scope"]["components"].append("fixture-component-b")
        self.held("ASSET_INDICATION_NOT_EXACT")

    def test_separate_arm_asset_mismatch(self):
        self.data["arms"][0]["comparison"].update(asset="BETAMAB", molecule="betamab")
        self.data["arms"][0]["scope"]["components"] = ["fixture-component-b"]
        self.held("ASSET_INDICATION_NOT_EXACT")

    def test_mixed_arms_as_combination(self):
        self.data["arms"][0]["scope"]["components"] = ["fixture-component-a", "fixture-component-b"]
        self.held("CONFLICT_COMPONENTS")

    def test_dose_mismatch(self):
        self.data["arms"][0]["scope"]["dose"] = "other-dose"
        self.held("CONFLICT_DOSE")

    def test_route_mismatch(self):
        self.data["arms"][0]["scope"]["route"] = "oral"
        self.held("CONFLICT_ROUTE")

    def test_unlinked_news_and_regulatory_cannot_corroborate(self):
        for family in ("SIGNAL", "REGULATORY"):
            with self.subTest(family=family):
                self.data["sources"][0]["assessedFamilies"] = ["PIPELINE", family]
                self.data["evidence"][0].update(family=family, portfolioIds=[], armId=None)
                self.held("EVIDENCE_NOT_LINKED_TO_TARGET")

    def test_signal_republication_does_not_add_independent_source(self):
        self.data["sources"][0]["assessedFamilies"].append("SIGNAL")
        e = deepcopy(self.data["evidence"][0])
        e.update(recordId="republished-signal", family="SIGNAL", armId=None, independent=False)
        self.data["evidence"].append(e)
        self.data["relations"][0]["evidenceIds"].append(e["recordId"])
        self.assertEqual(run(self.data)["rows"][0]["independentSourceCount"], 2)

    def test_missing_tl_link_is_coverage_review_not_defect(self):
        self.data["portfolio"][0]["landscapeIds"] = []
        self.data["landscape"] = []
        self.data["cases"][0]["expectedLandscapeIds"] = []
        r = run(self.data)
        self.assertEqual(r["status"], "PASS")
        self.assertEqual(r["downstreamImpacts"][0]["landscapeCoverage"], "COVERAGE_REVIEW_ONLY")

    def test_tl_segment_line_and_competitor_role_preserved(self):
        self.data["landscape"][0]["scope"].update(population="other", line="1L", companyRole="competitor")
        r = run(self.data)
        self.assertEqual(r["cases"][0]["status"], "HOLD")
        codes = r["downstreamImpacts"][0]["landscape"][0]["reasonCodes"]
        self.assertIn("CONFLICT_COMPANY_ROLE", codes)
        self.assertIn("CONFLICT_LINE", codes)
        self.assertIn("CONFLICT_POPULATION", codes)

    def test_nonreciprocal_tl_link(self):
        self.data["landscape"][0]["portfolioIds"] = []
        self.assertEqual(run(self.data)["status"], "FAIL")

    def test_snapshot_count_and_disposition_mismatch(self):
        self.data["expectedSourceCount"] = 53
        self.data["expectedDispositionCounts"] = {"MATCHED": 11, "HELD": 16, "NEW": 26}
        r = run(self.data)
        self.assertEqual(r["status"], "FAIL")
        self.assertIn("SOURCE_DENOMINATOR_MISMATCH", r["issues"])
        self.assertEqual(r["downstreamImpacts"][0]["derivedEvidenceFamilies"], [])

    def test_incomplete_snapshot_blocked(self):
        self.data["completeTables"].remove("arms")
        self.assertEqual(run(self.data)["status"], "BLOCKED — INPUT SNAPSHOT REQUIRED")

    def test_foreign_source_watch_candidate_not_reused(self):
        self.data["candidates"][0]["sourceWatchRecordId"] = "other-watch"
        self.held("ACTIVE_CANDIDATE_COUNT_0")

    def test_input_unknown_fields_rejected(self):
        self.data["portfolio"][0]["ZZ System Programme Key"] = "never-write"
        with self.assertRaises(ValueError):
            Snapshot.model_validate(self.data)

    def test_phase_delta_stays_held(self):
        self.data["arms"][0]["comparison"]["phase"] = "Phase 2"
        self.held("FIELD_DELTA_REQUIRES_REVIEW")

    def test_protocol_backed_normalization_requires_proof(self):
        scope = Snapshot.model_validate(self.data).sources[0].scope
        normalized = scope.model_copy(deep=True)
        self.assertEqual(scope_reasons(scope, normalized), [])
        normalized.proofReferences["line"] = ""
        self.assertIn("UNPROVEN_LINE", scope_reasons(scope, normalized))

    def test_joint_company_views_share_study_not_duplicate_effort(self):
        self.data["relatedCompanies"] = ["Partner Pharma"]
        p = deepcopy(self.data["portfolio"][0])
        p.update(recordId="partner-portfolio", company="Partner Pharma", landscapeIds=[])
        p["comparison"].update(recordId="partner-portfolio", company="Partner Pharma")
        p["scope"]["companyRole"] = "partner"
        self.data["portfolio"].append(p)
        self.data["candidates"][0]["portfolioIds"].append(p["recordId"])
        self.data["trials"][0]["portfolioIds"].append(p["recordId"])
        self.data["evidence"][0]["portfolioIds"].append(p["recordId"])
        rel = deepcopy(self.data["relations"][0])
        rel.update(recordId="partner-relation", portfolioId=p["recordId"], relationType="JOINT_DEVELOPMENT_VIEW")
        rel["sourceScope"]["companyRole"] = "partner"
        self.data["relations"].append(rel)
        self.data["sources"][0]["relationIds"].append(rel["recordId"])
        self.data["cases"][0]["expectedPortfolioIds"].append(p["recordId"])
        r = run(self.data)
        self.assertEqual(r["status"], "PASS", r["rows"][0]["reasonCodes"])
        self.assertEqual(r["rows"][0]["independentSourceCount"], 2)
        self.assertEqual({x["sharedStudyIdentity"] for x in r["rows"][0]["relations"]}, {"NCT00000001"})

    def test_multi_indication_projection_requires_verified_source_scope(self):
        source = self.data["sources"][0]
        source["granularity"] = "multi_indication"
        self.data["candidates"][0]["sourceGranularity"] = "multi_indication"
        source["scope"]["indication"] = None
        p = deepcopy(self.data["portfolio"][0])
        p.update(recordId="other-indication", landscapeIds=[])
        p["comparison"].update(recordId="other-indication", indication="Second disease")
        p["scope"]["indication"] = "Second disease"
        self.data["portfolio"].append(p)
        self.data["candidates"][0]["portfolioIds"].append(p["recordId"])
        self.data["trials"][0]["portfolioIds"].append(p["recordId"])
        a = deepcopy(self.data["arms"][0])
        a.update(recordId="second-cohort", armRef="Synthetic independently supported cohort B")
        a["comparison"]["indication"] = "Second disease"
        a["scope"]["indication"] = "Second disease"
        self.data["arms"].append(a)
        self.data["trials"][0]["armIds"].append(a["recordId"])
        e = deepcopy(self.data["evidence"][0])
        e.update(recordId="second-cohort-evidence", armId=a["recordId"], portfolioIds=[p["recordId"]])
        e["comparison"]["indication"] = "Second disease"
        e["scope"]["indication"] = "Second disease"
        self.data["evidence"].append(e)
        rel = deepcopy(self.data["relations"][0])
        rel.update(recordId="second-indication-relation", portfolioId=p["recordId"],
                   relationType="INDICATION_RELATIONSHIP", evidenceIds=[e["recordId"]])
        rel["sourceComparison"]["indication"] = "Second disease"
        rel["sourceScope"]["indication"] = "Second disease"
        self.data["relations"].append(rel)
        source["relationIds"].append(rel["recordId"])
        self.data["cases"][0]["expectedPortfolioIds"].append(p["recordId"])
        self.assertEqual(run(self.data)["status"], "PASS")
        rel["sourceProjectionVerified"] = False
        self.held("UNVERIFIED_SOURCE_SCOPE_PROJECTION")

    def test_nct_match_needs_official_source_relationship_proof(self):
        self.data["sources"][0]["trialReferences"] = {}
        self.held("OFFICIAL_SOURCE_NCT_RELATION_UNPROVEN")

    def test_no_network_calls_or_routes_added(self):
        from unittest.mock import patch
        from service_entrypoint import app
        before = list(app.routes)
        with patch("httpx.AsyncClient.request", side_effect=AssertionError("Network access prohibited")), \
             patch("httpx.Client.request", side_effect=AssertionError("Network access prohibited")), \
             patch("socket.create_connection", side_effect=AssertionError("Network access prohibited")):
            self.assertEqual(run(self.data)["status"], "PASS")
        self.assertEqual(before, app.routes)

    def test_source_projection_cannot_replace_asset_or_phase(self):
        self.data["relations"][0]["sourceComparison"]["asset"] = "Different asset"
        self.held("SOURCE_PROJECTION_IDENTITY_OR_STATE_MUTATION")

    def test_duplicate_source_keys_fail_full_contract(self):
        self.data["sources"].append(deepcopy(self.data["sources"][0]))
        self.data["expectedSourceCount"] = 2
        self.data["expectedDispositionCounts"] = {"MATCHED": 2}
        r = run(self.data)
        self.assertEqual(r["status"], "FAIL")
        self.assertIn("DUPLICATE_OFFICIAL_SOURCE_KEYS", r["issues"])

    def test_active_candidate_routing_flags_never_enable_writes(self):
        self.data["candidates"][0]["queueEligible"] = True
        r = self.held("PERSISTED_WRITE_ELIGIBILITY_CONFLICT")
        self.assertEqual(r["status"], "FAIL")
        self.assertFalse(r["guardrails"]["queueEligible"])

    def test_stale_source_grain_stays_held(self):
        self.data["candidates"][0]["sourceVersion"] = "old-source-version"
        self.held("STALE_OR_UNPROVEN_CANDIDATE_SOURCE_GRAIN")

    def test_unknown_official_grain_stays_held(self):
        self.data["sources"][0]["granularity"] = "unknown"
        self.data["candidates"][0]["sourceGranularity"] = "unknown"
        self.held("OFFICIAL_SOURCE_GRAIN_UNASSESSED")

    def test_trial_family_requires_official_registry_urls_not_news_title(self):
        self.data["evidence"][0]["provenance"]["url"] = "https://example.invalid/news/NCT00000001"
        self.data["evidence"][0]["comparison"]["sourceUrl"] = "https://example.invalid/news/NCT00000001"
        self.held("OFFICIAL_NCT_URL_UNPROVEN")

    def test_snapshot_cli_uses_typed_cases_and_exit_status(self):
        import os
        from pathlib import Path
        import subprocess
        import sys
        import tempfile
        script = str(Path(__file__).with_name("r1c_shared_lineage.py"))
        with tempfile.TemporaryDirectory(prefix="r1c-test-", dir="/tmp") as folder:
            snapshot = Path(folder) / "synthetic.json"
            cases = Path(folder) / "cases.json"
            snapshot.write_text(json.dumps(self.data))
            cases.write_text(json.dumps([{"name": "Synthetic case", "ncts": ["NCT00000001"]}]))
            command = [sys.executable, script, "--snapshot", str(snapshot), "--expected-count", "1"]
            for extra in ([], ["--cases", str(cases)]):
                r = subprocess.run(command + extra, capture_output=True, text=True,
                                   env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertEqual(json.loads(r.stdout)["status"], "PASS")
            cases.write_text(json.dumps([{"name": "Missing case"}]))
            r = subprocess.run(command + ["--cases", str(cases)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 2, r.stderr)
            self.assertEqual(json.loads(r.stdout)["status"], "BLOCKED — INPUT SNAPSHOT REQUIRED")


class AssetPresenceSafetyTests(unittest.TestCase):
    """Read-only generic identity checks; clinical programme approval excluded."""

    @staticmethod
    def src(**kwargs):
        return {**dict(company="Example Pharma", sourceRecordId="row-1",
                       asset="ALPHAMAB"), **kwargs}

    @staticmethod
    def target(record_id="p-1", **kwargs):
        return {**dict(recordId=record_id, company="Example Pharma",
                       asset="ALPHAMAB", molecule="alphamab"), **kwargs}

    def assess(self, source=None, targets=None, classification="NEW ASSET"):
        from r1c_shared_lineage import assess_asset_presence
        return assess_asset_presence(
            source or self.src(),
            targets if targets is not None else [self.target()],
            observed_classification=classification)

    def test_cross_field_whole_identity_flags_false_new_asset_without_link(self):
        result = self.assess(targets=[self.target(asset="Branded therapy",
                                                  molecule="ALPHAMAB")])
        self.assertEqual(result["assetExistenceAssessment"],
                         "EXISTING_ASSET_IDENTITY_OBSERVED")
        self.assertEqual(result["classificationReview"],
                         "REASSESS_NEW_ASSET_CLASSIFICATION")
        self.assertEqual(result["candidatePortfolioIdentities"][0]["recordId"], "p-1")
        self.assertEqual(result["originalDiscoveryClassification"], "NEW ASSET")
        self.assertIsNone(result["proposedDiscoveryClassification"])
        self.assertIsNone(result["canonicalPortfolioMatch"])
        self.assertFalse(result["autoLink"])
        self.assertFalse(result["queueEligible"])
        self.assertFalse(result["portfolioWriteEligible"])
        self.assertEqual(result["masterWrites"], 0)

    def test_same_molecule_different_programmes_both_found_but_held(self):
        targets = [self.target("later", indication="4L+ myeloma"),
                   self.target("earlier", indication="2L myeloma")]
        result = self.assess(targets=targets)
        self.assertEqual(result["candidatePortfolioIdentityCount"], 2)
        self.assertEqual(result["programmeIdentity"], "NOT_ASSESSED")
        self.assertIsNone(result["canonicalPortfolioMatch"])

    def test_indication_and_therapy_line_do_not_collapse(self):
        targets = [self.target("ovarian", indication="Ovarian cancer"),
                   self.target("lung", indication="NSCLC")]
        result = self.assess(targets=targets)
        self.assertEqual({x["recordId"] for x in result["candidatePortfolioIdentities"]},
                         {"ovarian", "lung"})
        self.assertEqual(result["programmeIdentity"], "NOT_ASSESSED")

    def test_monotherapy_cannot_be_identity_matched_to_combination(self):
        source = self.src(asset="OMEGAMAB")
        targets = [self.target(asset="OMEGAMAB + DELTAMAB",
                               molecule="omegamab + deltamab")]
        self.assertEqual(self.assess(source, targets)["candidatePortfolioIdentityCount"], 0)

    def test_entire_regimens_can_match_cross_field_without_approval(self):
        source = self.src(asset="OMEGAMAB/DELTAMAB")
        targets = [self.target(asset="Combination R", molecule="DELTAMAB + OMEGAMAB")]
        result = self.assess(source, targets)
        self.assertEqual(result["assetExistenceAssessment"],
                         "EXISTING_ASSET_IDENTITY_OBSERVED")
        self.assertIn("EXACT_WHOLE_REGIMEN",
                      result["candidatePortfolioIdentities"][0]["methods"])
        self.assertIsNone(result["canonicalPortfolioMatch"])

    def test_similar_prefixes_not_fuzzy_matched(self):
        result = self.assess(self.src(asset="ALPHAMAB XR"),
                             [self.target()])
        self.assertEqual(result["candidatePortfolioIdentityCount"], 0)
        self.assertEqual(result["assetExistenceAssessment"],
                         "NO_DETERMINISTIC_IDENTITY_OBSERVED")

    def test_target_biomarker_not_used_as_drug_code(self):
        source = self.src(asset="CD19/CD20 bicistronic",
                          developmentCode="CD19")
        targets = [self.target(asset="Another therapy", molecule="another",
                               developmentCode="CD19")]
        result = self.assess(source, targets)
        self.assertEqual(result["candidatePortfolioIdentityCount"], 0)

    def test_actual_development_code_can_match_cross_field(self):
        source = self.src(asset="KITE-753 (PALISADES-1)",
                          developmentCode="CD19")
        targets = [self.target(asset="CAR T product", molecule="bicistronic CAR-T",
                               developmentCode="KITE-753")]
        result = self.assess(source, targets)
        self.assertEqual(result["exactIdentityCandidateCount"], 1)
        self.assertIn("EXACT_CROSS_FIELD_DEVELOPMENT_CODE",
                      result["candidatePortfolioIdentities"][0]["methods"])

    def test_code_only_in_target_display_is_review_not_exact(self):
        source = self.src(asset="GS-8824 (NAPISTAR 1-01)", developmentCode="GS-8824")
        targets = [self.target(asset="GS-8824 / TUB-040", molecule="ADC")]
        result = self.assess(source, targets)
        self.assertEqual(result["assetExistenceAssessment"],
                         "POSSIBLE_ASSET_IDENTITY_REVIEW")
        self.assertEqual(result["exactIdentityCandidateCount"], 0)
        self.assertEqual(result["candidatePortfolioIdentities"][0]["evidenceStrength"],
                         "REVIEW_ONLY_CODE_IN_DISPLAY")
        self.assertIsNone(result["canonicalPortfolioMatch"])

    def test_cross_company_is_not_a_verified_partner_programme(self):
        source = self.src(asset="ALPHAMAB")
        targets = [dict(self.target(), company="Partner Pharma")]
        result = self.assess(source, targets)
        self.assertEqual(result["candidatePortfolioIdentityCount"], 0)
        self.assertEqual(result["programmeIdentity"], "NOT_ASSESSED")

    def test_missing_source_company_fails_closed(self):
        source = self.src()
        source.pop("company")
        result = self.assess(source)
        self.assertEqual(result["assetExistenceAssessment"], "COMPANY_SCOPE_UNASSESSED")
        self.assertEqual(result["candidatePortfolioIdentityCount"], 0)

    def test_absence_is_not_proof_of_new_product(self):
        result = self.assess(self.src(asset="UNSEENNAME"), [self.target()])
        self.assertEqual(result["assetExistenceAssessment"],
                         "NO_DETERMINISTIC_IDENTITY_OBSERVED")
        self.assertEqual(result["classificationReview"], "NO_RECLASSIFICATION_PROPOSED")
        self.assertEqual(result["originalDiscoveryClassification"], "NEW ASSET")

    def test_duplicate_ids_hold_without_arbitrary_pick(self):
        targets = [self.target(), self.target()]
        with self.assertRaisesRegex(ValueError, "Duplicate in-scope"):
            self.assess(targets=targets)

    def test_observed_gilead_six_candidate_vs_55_portfolio_identity_preflight(self):
        from pathlib import Path
        observed = json.loads((Path(__file__).parent /
            "audits/STEP4_R1C_GILEAD_COMPARATOR_OBSERVED_INPUT.json").read_text())
        self.assertEqual(len(observed["candidateRows"]), 6)
        self.assertEqual(len(observed["portfolioRows"]), 55)
        self.assertEqual(len({x["recordId"] for x in observed["portfolioRows"]}), 55)
        for row in observed["candidateRows"]:
            result = self.assess(row["source"], observed["portfolioRows"],
                                 row["liveClassification"])
            expected = set(observed["proposedProgrammeTargets"][row["candidateRecordId"]])
            actual = {x["recordId"] for x in result["candidatePortfolioIdentities"]}
            self.assertTrue(expected.issubset(actual), row["candidateRecordId"])
            self.assertIn(result["assetExistenceAssessment"],
                          {"EXISTING_ASSET_IDENTITY_OBSERVED",
                           "POSSIBLE_ASSET_IDENTITY_REVIEW"})
            self.assertEqual(result["classificationReview"],
                             "REASSESS_NEW_ASSET_CLASSIFICATION")
            self.assertEqual(result["programmeIdentity"], "NOT_ASSESSED")
            self.assertFalse(result["autoLink"])
            self.assertIsNone(result["proposedDiscoveryClassification"])

    def test_existing_v16_comparator_kept_unmodified_and_overlay_held(self):
        # Supported service import order prevents the pre-existing AZ cycle.
        import service_entrypoint  # noqa: F401
        import portfolio_discovery_extension_v16  # noqa: F401
        import portfolio_discovery_extension_v11 as v
        from pathlib import Path
        observed = json.loads((Path(__file__).parent /
            "audits/STEP4_R1C_GILEAD_COMPARATOR_OBSERVED_INPUT.json").read_text())
        sources = [v.DiscoverySourceRow(**x["source"])
                   for x in observed["candidateRows"]]
        targets = [v.PortfolioSnapshotRow(**x)
                   for x in observed["portfolioRows"]]
        compared = v.compare_discovery(v.DiscoveryCompareRequest(
            company="Gilead Sciences", sourceRows=sources,
            portfolioRows=targets, batchRunId="SIX_CASE_READ_ONLY_TEST"))
        self.assertTrue(compared.readOnly)
        self.assertFalse(compared.guardrails["masterWrites"])
        self.assertEqual(len(compared.candidates), 6)
        for row, compared_row in zip(observed["candidateRows"], compared.candidates):
            assessment = self.assess(row["source"], observed["portfolioRows"],
                                     compared_row["classification"])
            self.assertFalse(assessment["autoLink"])
            self.assertEqual(assessment["originalDiscoveryClassification"],
                             compared_row["classification"])
            self.assertIsNone(assessment["proposedDiscoveryClassification"])



class ComparatorAssetPresenceIntegrationTests(unittest.TestCase):
    """Actual comparator contract tests: additive opt-in, no write decisions."""

    @staticmethod
    def inputs():
        import service_entrypoint  # noqa: F401 - supported extension import order
        import portfolio_discovery_extension_v16  # noqa: F401
        import portfolio_discovery_extension_v11 as v
        from pathlib import Path
        observed = json.loads((Path(__file__).parent /
            "audits/STEP4_R1C_GILEAD_COMPARATOR_OBSERVED_INPUT.json").read_text())
        sources = [v.DiscoverySourceRow(**row["source"])
                   for row in observed["candidateRows"]]
        portfolio = [v.PortfolioSnapshotRow(**row)
                     for row in observed["portfolioRows"]]
        return v, observed, sources, portfolio

    def compare(self, requested=False):
        v, observed, sources, portfolio = self.inputs()
        result = v.compare_discovery(v.DiscoveryCompareRequest(
            company="Gilead Sciences", sourceRows=sources,
            portfolioRows=portfolio, includeAssetPresence=requested,
            batchRunId="R1C_OPTIONAL_ASSET_PRESENCE_READ_ONLY"))
        return observed, result

    def test_default_request_retains_existing_response_contract(self):
        observed, output = self.compare()
        self.assertEqual(output.summary["NEW ASSET"], 6)
        self.assertTrue(output.readOnly)
        self.assertFalse(output.guardrails["masterWrites"])
        self.assertNotIn("assetPresenceOptIn", output.guardrails)
        for candidate in output.candidates:
            self.assertNotIn("assetPresence", candidate)
            self.assertEqual(candidate["classification"], "NEW ASSET")
            self.assertEqual(candidate["existingPortfolioRecordIds"], [])

    def test_optin_six_real_cases_find_expected_assets_without_approval(self):
        observed, output = self.compare(requested=True)
        self.assertEqual(output.summary["NEW ASSET"], 6)
        self.assertTrue(output.guardrails["assetPresenceOptIn"])
        self.assertFalse(output.guardrails["assetPresenceCandidateWrites"])
        self.assertFalse(output.guardrails["assetPresencePortfolioWrites"])
        self.assertFalse(output.guardrails["assetPresenceProgrammeApproval"])
        for source_row, candidate in zip(observed["candidateRows"], output.candidates):
            self.assertEqual(candidate["classification"], "NEW ASSET")
            self.assertEqual(candidate["existingPortfolioRecordIds"], [])
            a = candidate["assetPresence"]
            expected = set(observed["proposedProgrammeTargets"][
                source_row["candidateRecordId"]])
            got = {item["recordId"] for item in a["candidatePortfolioIdentities"]}
            self.assertTrue(expected.issubset(got), source_row["candidateRecordId"])
            self.assertEqual(a["classificationReview"],
                             "REASSESS_NEW_ASSET_CLASSIFICATION")
            self.assertEqual(a["programmeIdentity"], "NOT_ASSESSED")
            self.assertIsNone(a["canonicalPortfolioMatch"])
            self.assertIsNone(a["proposedDiscoveryClassification"])
            self.assertFalse(a["autoLink"])
            self.assertFalse(a["queueEligible"])
            self.assertFalse(a["portfolioWriteEligible"])
            self.assertEqual(a["masterWrites"], 0)

    def test_optin_is_strictly_additive_to_all_existing_decisions(self):
        _, default = self.compare()
        _, optin = self.compare(requested=True)
        self.assertEqual(optin.summary, default.summary)
        self.assertEqual(optin.version, default.version)
        self.assertEqual(optin.company, default.company)
        self.assertEqual(optin.sourceRowCount, default.sourceRowCount)
        self.assertEqual(optin.portfolioRowCount, default.portfolioRowCount)
        for before, after in zip(default.candidates, optin.candidates):
            self.assertEqual(before,
                             {k: v for k, v in after.items() if k != "assetPresence"})
        for k, value in default.guardrails.items():
            self.assertEqual(optin.guardrails[k], value)

    def test_already_matched_programme_is_not_reclassified(self):
        v, _, _, _ = self.inputs()
        source = v.DiscoverySourceRow(
            company="Example Pharma", sourceFamily="Company Pipeline",
            asset="ALPHAMAB", indication="Ovarian cancer", phase="Phase 3")
        target = v.PortfolioSnapshotRow(
            recordId="p1", company="Example Pharma", asset="ALPHAMAB",
            molecule="alphamab", indication="Ovarian cancer", phase="Phase 3")
        result = v.compare_discovery(v.DiscoveryCompareRequest(
            company="Example Pharma", sourceRows=[source],
            portfolioRows=[target], includeAssetPresence=True))
        self.assertEqual(result.candidates[0]["classification"], "MATCHED")
        self.assertEqual(result.candidates[0]["existingPortfolioRecordIds"], ["p1"])
        self.assertNotIn("assetPresence", result.candidates[0])

    def test_excluded_or_unavailable_source_never_gets_asset_presence(self):
        v, _, _, _ = self.inputs()
        src = v.DiscoverySourceRow(
            company="Example Pharma", sourceFamily="Company Pipeline",
            asset="ALPHAMAB", phase="Phase 3", programStatus="Discontinued")
        unavailable = src.model_copy(update={"programStatus": "Active",
                                              "sourceUnavailable": True})
        for s in [src, unavailable]:
            result = v.compare_discovery(v.DiscoveryCompareRequest(
                company="Example Pharma", sourceRows=[s],
                portfolioRows=[], includeAssetPresence=True))
            self.assertIn(result.candidates[0]["classification"],
                          {"EXCLUDED BY RULE", "SOURCE UNAVAILABLE"})
            self.assertNotIn("assetPresence", result.candidates[0])

    def test_cross_company_source_and_portfolio_disallowed(self):
        v, _, _, _ = self.inputs()
        source = v.DiscoverySourceRow(
            company="Wrong Pharma", sourceFamily="Company Pipeline",
            asset="ALPHAMAB", indication="Test indication", phase="Phase 3")
        # Wrong-company source must not use Example Pharma Portfolio even if
        # asset strings overlap.
        target = v.PortfolioSnapshotRow(
            recordId="p1", company="Example Pharma", asset="ALPHAMAB")
        result = v.compare_discovery(v.DiscoveryCompareRequest(
            company="Example Pharma", sourceRows=[source],
            portfolioRows=[target], includeAssetPresence=True))
        # The base comparator already fails closed on ownership, so the
        # optional overlay must not evaluate or downgrade that hold.
        self.assertEqual(result.candidates[0]["classification"], "OWNERSHIP REVIEW")
        self.assertNotIn("assetPresence", result.candidates[0])

    def test_foreign_portfolio_not_included_as_asset_identity(self):
        v, _, _, _ = self.inputs()
        source = v.DiscoverySourceRow(
            company="Example Pharma", sourceFamily="Company Pipeline",
            asset="ALPHAMAB", phase="Phase 3")
        foreign = v.PortfolioSnapshotRow(
            recordId="foreign", company="Partner Pharma", asset="ALPHAMAB")
        result = v.compare_discovery(v.DiscoveryCompareRequest(
            company="Example Pharma", sourceRows=[source],
            portfolioRows=[foreign], includeAssetPresence=True))
        self.assertEqual(result.candidates[0]["classification"], "NEW ASSET")
        a = result.candidates[0]["assetPresence"]
        self.assertEqual(a["candidatePortfolioIdentityCount"], 0)
        self.assertEqual(a["programmeIdentity"], "NOT_ASSESSED")
        self.assertIsNone(a["canonicalPortfolioMatch"])

    def test_duplicate_in_scope_portfolio_ids_fail_closed(self):
        v, _, _, _ = self.inputs()
        source = v.DiscoverySourceRow(
            company="Example Pharma", sourceFamily="Company Pipeline",
            asset="OMEGAMAB", indication="Test indication", phase="Phase 3")
        duplicate = v.PortfolioSnapshotRow(
            recordId="p1", company="Example Pharma", asset="ALPHAMAB")
        request = v.DiscoveryCompareRequest(
            company="Example Pharma", sourceRows=[source],
            portfolioRows=[duplicate, duplicate], includeAssetPresence=True)
        with self.assertRaisesRegex(ValueError, "Duplicate in-scope"):
            v.compare_discovery(request)



if __name__ == "__main__":
    unittest.main(verbosity=2)
