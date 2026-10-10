"""Isolated R1C evidence admission canaries; zero writes."""
import unittest
from shared_programme_grain_v1 import ProgrammeGrainHold, expand_verified_programmes
from shared_programme_evidence_qualification_v1 import qualify

HOSTS = {"www.gilead.com", "ionis.com"}
def src(parent, asset):
    return dict(company="Example Pharma", sourceFamily="Company Pipeline",
                sourceRecordId=parent, asset=asset, sourceUrl="https://example.org/pipeline")
def att(parent, indication, code, host="www.gilead.com"):
    return dict(sourceRecordId=parent, indication=indication,
                controlledIndicationId=code, reviewed=True, scopeVerified=True,
                assetVerified=True, evidenceUrl="https://"+host+"/pipeline")
class EvidenceQualificationTests(unittest.TestCase):
    def test_gilead_distinct_verified_indications(self):
        p="sitecore-source-47"
        a=att(p,"Platinum-resistant ovarian cancer","recQTqeeeQMyMKnOY")
        b=att(p,"Non-small cell lung cancer","recqTQTf5vXD7yKrn")
        rows=expand_verified_programmes(qualify(src(p,"GS-8824 / TUB-040"),[a,b],approved_hosts=HOSTS))
        self.assertEqual(len(rows),2)
        self.assertEqual(len({r["sourceRecordId"] for r in rows}),2)
    def test_ionis_legacy_parent_is_held(self):
        p="owned:1769806455"
        a=att(p,"Familial Chylomicronemia Syndrome","rec94PLEYL2UbVNgE","ionis.com")
        b=att(p,"Severe Hypertriglyceridemia","recww06D3PDJ7X67L","ionis.com")
        with self.assertRaisesRegex(ProgrammeGrainHold,"MIGRATION"):
            qualify(src(p,"TRYNGOLZA"),[a,b],approved_hosts=HOSTS,
                    existing_parent_candidate_ids={p})
    def test_composite_unreviewed_source_held(self):
        p="owned:1769806455"
        a=att(p,"FCS and sHTG","rec94PLEYL2UbVNgE","ionis.com")
        a["scopeVerified"]=False
        with self.assertRaises(ProgrammeGrainHold):
            qualify(src(p,"TRYNGOLZA"),[a],approved_hosts=HOSTS)
    def test_host_subdomain_spoof_rejected(self):
        p="sitecore-source-47"
        a=att(p,"Ovarian cancer","recQTqeeeQMyMKnOY","www.gilead.com.evil.example")
        with self.assertRaises(ProgrammeGrainHold):
            qualify(src(p,"GS-8824"),[a],approved_hosts=HOSTS)
    def test_missing_review_attestation_held(self):
        p="sitecore-source-47"
        a=att(p,"Ovarian cancer","recQTqeeeQMyMKnOY")
        a["reviewed"]=False
        with self.assertRaises(ProgrammeGrainHold):
            qualify(src(p,"GS-8824"),[a],approved_hosts=HOSTS)
if __name__=="__main__":
    unittest.main()
