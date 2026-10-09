"""Independent-authority bridge safety fixtures: entirely synthetic, not Gilead."""
from copy import deepcopy
import json
import unittest

from r1c_shared_lineage import SCOPE_FIELDS
from test_r1c_shared_lineage import fixture, run


def bridge_fixture():
    data = json.loads(json.dumps(fixture()))
    data['sources'][0]['trialReferences'] = {}
    data['enableIndependentAuthorityBridge'] = True
    scope = data['arms'][0]['scope']
    proofs = {field: ' | '.join(scope[field]) if isinstance(scope[field], list)
              else scope[field] for field in SCOPE_FIELDS}
    proofs.update(programme='ALPHAMAB exact programme', trial='NCT00000001',
                  experimentalArm='Synthetic arm A experimental',
                  companyRole='Example Pharma owner of ALPHAMAB programme')
    text = '\n'.join(proofs.values())
    for record in data['trials'] + data['arms'] + data['evidence']:
        record['provenance']['originalText'] = text
    data['authorityBridges'] = [dict(
        recordId='synthetic-bridge', relationId='fixture-relation',
        evidenceId='fixture-evidence', stableKey='opaque-fixture-key',
        trialRecordId='fixture-trial', armId='fixture-arm', verified=True,
        sourceProvenance=deepcopy(data['sources'][0]['provenance']),
        trialProvenance=deepcopy(data['trials'][0]['provenance']),
        armProvenance=deepcopy(data['arms'][0]['provenance']), proofExcerpts=proofs)]
    return data


class AuthorityBridgeTests(unittest.TestCase):
    def setUp(self):
        self.data = bridge_fixture()

    def assessment(self, result):
        return result['rows'][0]['relations'][0]['evidence'][0]['bridgeAssessment']

    def held(self, code):
        result = run(self.data)
        self.assertEqual(self.assessment(result)['status'], 'HELD')
        self.assertIn(code, self.assessment(result)['reasonCodes'])
        self.assertNotEqual(result['rows'][0]['status'], 'PASS')
        self.assertFalse(result['rows'][0]['portfolioWriteEligible'])
        self.assertFalse(result['rows'][0]['queueEligible'])

    def test_verified_bridge_and_immutable_replay(self):
        before = deepcopy(self.data)
        result = run(self.data)
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(self.assessment(result)['pathway'], 'INDEPENDENT_AUTHORITY_BRIDGE')
        self.assertEqual(result['rows'][0]['independentSourceCount'], 2)
        self.assertFalse(self.assessment(result)['writeEligible'])
        self.assertEqual(result, run(self.data))
        self.assertEqual(self.data, before)

    def test_opt_in_is_required(self):
        self.data['enableIndependentAuthorityBridge'] = False
        r = run(self.data)
        self.assertIn('OFFICIAL_SOURCE_NCT_RELATION_UNPROVEN', r['rows'][0]['reasonCodes'])
        self.assertNotIn('bridgeAssessment', r['rows'][0]['relations'][0]['evidence'][0])

    def test_direct_path_unchanged(self):
        self.data['sources'][0]['trialReferences'] = {'NCT00000001': 'synthetic-direct-proof'}
        self.data['authorityBridges'] = []
        r = run(self.data)
        self.assertEqual(r['status'], 'PASS')
        self.assertEqual(self.assessment(r)['pathway'], 'PIPELINE_DIRECT_NCT')

    def test_no_bridge(self):
        self.data['authorityBridges'] = []
        self.held('NO_BRIDGE_EVIDENCE')

    def test_duplicate_bridge_is_ambiguous(self):
        other = deepcopy(self.data['authorityBridges'][0])
        other['recordId'] = 'synthetic-second-bridge'
        self.data['authorityBridges'].append(other)
        self.held('BRIDGE_AMBIGUOUS')

    def test_republication_not_independent(self):
        self.data['evidence'][0]['independent'] = False
        self.held('BRIDGE_NOT_INDEPENDENTLY_VERIFIED')

    def test_unverified_bridge(self):
        self.data['authorityBridges'][0]['verified'] = False
        self.held('BRIDGE_NOT_INDEPENDENTLY_VERIFIED')

    def test_wrong_key(self):
        self.data['authorityBridges'][0]['stableKey'] = 'other-key'
        self.held('BRIDGE_IDENTITY_BINDING_MISMATCH')

    def test_stale_source(self):
        self.data['authorityBridges'][0]['sourceProvenance']['version'] = 'old'
        self.held('BRIDGE_STALE_PROVENANCE')

    def test_mismatched_registry_version(self):
        self.data['evidence'][0]['provenance']['version'] = 'other-version'
        self.held('BRIDGE_REGISTRY_VERSION_MISMATCH')

    def test_unaligned_dates(self):
        self.data['sources'][0]['provenance']['asOf'] = '2026-09-30'
        self.held('BRIDGE_TEMPORAL_ALIGNMENT_UNPROVEN')

    def test_missing_original_proof(self):
        self.data['authorityBridges'][0]['proofExcerpts']['programme'] = 'invented ALPHAMAB'
        self.held('BRIDGE_UNPROVEN_PROGRAMME')

    def test_sponsor_association_not_company_role(self):
        self.data['authorityBridges'][0]['proofExcerpts']['companyRole'] = 'Example Pharma'
        self.held('BRIDGE_COMPANY_ROLE_UNPROVEN')

    def test_scope_conflicts(self):
        for field in ('indication', 'population', 'line', 'setting', 'route', 'dose'):
            with self.subTest(field=field):
                original = deepcopy(self.data)
                self.data['arms'][0]['scope'][field] = 'other'
                self.held('CONFLICT_' + field.upper())
                self.data = original

    def test_mixed_experimental_arms(self):
        self.data['arms'][0]['scope']['components'].append('other-component')
        self.held('CONFLICT_COMPONENTS')

    def test_nonexperimental_roles(self):
        for role in ('placebo', 'comparator', 'background', 'supportive'):
            with self.subTest(role=role):
                self.data['arms'][0]['interventionRole'] = role
                self.held('NON_FOCAL_INTERVENTION_ROLE')

    def test_parent_trial_without_focal_arm(self):
        self.data['arms'] = []
        self.data['trials'][0]['armIds'] = []
        self.held('NCT_WITHOUT_FOCAL_ARM_PROOF')

    def test_unproven_alias(self):
        self.data['arms'][0]['comparison']['asset'] = 'BETAMAB'
        self.held('BRIDGE_ALIAS_UNPROVEN')

    def test_registry_url_must_identify_exact_trial(self):
        self.data['evidence'][0]['provenance']['url'] += '9'
        self.held('BRIDGE_REGISTRY_URL_UNPROVEN')

    def test_unrelated_protocol_authority(self):
        self.data['authorityBridges'][0]['protocol'] = deepcopy(self.data['sources'][0]['provenance'])
        self.data['authorityBridges'][0]['protocol']['authorityId'] = 'republisher'
        self.held('BRIDGE_PROTOCOL_AUTHORITY_UNPROVEN')

    def test_verified_original_protocol_alias(self):
        self.data['arms'][0]['comparison']['asset'] = 'ALPHAMAB-CODE'
        b = self.data['authorityBridges'][0]
        b['aliasProof'] = 'ALPHAMAB-CODE is the exact official alias for ALPHAMAB'
        b['protocol'] = deepcopy(self.data['sources'][0]['provenance'])
        b['protocol']['originalText'] = b['aliasProof']
        b['proofExcerpts']['programme'] = b['aliasProof']
        r = run(self.data)
        self.assertEqual(self.assessment(r)['status'], 'SUPPORTED_FOR_READ_ONLY_REVIEW')
        self.assertEqual(r['status'], 'PASS')
        self.assertEqual(r['rows'][0]['independentSourceCount'], 2)

    def test_duplicate_bridge_ids_fail_whole_snapshot(self):
        self.data['authorityBridges'].append(deepcopy(self.data['authorityBridges'][0]))
        r = run(self.data)
        self.assertEqual(r['status'], 'FAIL')
        self.assertIn('DUPLICATE_AUTHORITY_BRIDGE_IDS', r['issues'])

    def test_r1a_held_preserved(self):
        self.data['sources'][0].update(baselineDisposition='HELD', baselineReason='unresolved historical grain')
        self.data['expectedDispositionCounts'] = {'HELD': 1}
        r = run(self.data)
        self.assertEqual(r['rows'][0]['status'], 'HOLD')
        self.assertIn('R1A_HELD_PRESERVED:unresolved historical grain', r['rows'][0]['reasonCodes'])

    def test_missing_history_preserved(self):
        self.data['sources'][0].update(baselineDisposition='UNVERIFIED', baselineProof='')
        r = run(self.data)
        self.assertEqual(r['rows'][0]['status'], 'HOLD')
        self.assertIn('R1A_HISTORICAL_DISPOSITION_UNVERIFIED', r['rows'][0]['reasonCodes'])


if __name__ == '__main__':
    unittest.main()
