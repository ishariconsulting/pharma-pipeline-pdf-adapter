"""V1.5 additive verified-disease-alias patch for Portfolio Discovery.

Adds one narrow, deterministic clinical synonym family exposed by AstraZeneca
candidate QA: hereditary transthyretin amyloidosis with polyneuropathy is
commonly written as hATTR-PN, ATTRv-PN, or hereditary transthyretin-mediated
amyloid polyneuropathy.

The rule is disease-specific and exact-pattern based. It does not use fuzzy
matching and deliberately does not normalize ATTR-CM/cardiomyopathy to the
polyneuropathy concept.

No master-data writes are introduced.
"""

import re
from typing import Any, Dict

import portfolio_discovery_extension_v11 as base
import portfolio_discovery_extension_v14 as v14


DISCOVERY_VERSION = "V1.5.0 PORTFOLIO DISCOVERY READ ONLY - VERIFIED DISEASE ALIASES"

_PREVIOUS_CLINICAL_NORM = v14._clinical_norm_v14
_PREVIOUS_COMPARE = base.compare_discovery

_ATTR_PN_CANON = "hereditary transthyretin amyloidosis with polyneuropathy"
_ATTR_PN_FULL = re.compile(
    r"\b(?:"
    r"hereditary\s+transthyretin(?:-\s*|\s+)mediated\s+amyloid\s+polyneuropathy|"
    r"hereditary\s+transthyretin(?:-\s*|\s+)mediated\s+amyloidosis\s+with\s+polyneuropathy|"
    r"hereditary\s+transthyretin\s+amyloidosis\s+with\s+polyneuropathy"
    r")\b",
    flags=re.I,
)
_ATTR_PN_ABBR = re.compile(r"\b(?:hATTR[- ]?PN|ATTRv[- ]?PN)\b", flags=re.I)
_ATTR_PN_PAREN = re.compile(r"\(\s*(?:hATTR[- ]?PN|ATTRv[- ]?PN)\s*\)", flags=re.I)


def _clinical_norm_v15(value: Any) -> str:
    text = base._clean(value)
    if not text:
        return ""

    # When a full verified disease phrase is present, canonicalize the phrase
    # and drop a redundant parenthetical shorthand rather than duplicating the
    # canonical disease text.
    if _ATTR_PN_FULL.search(text):
        text = _ATTR_PN_FULL.sub(_ATTR_PN_CANON, text)
        text = _ATTR_PN_PAREN.sub(" ", text)
        text = _ATTR_PN_ABBR.sub(" ", text)
    else:
        text = _ATTR_PN_ABBR.sub(_ATTR_PN_CANON, text)

    return _PREVIOUS_CLINICAL_NORM(text)


# V1.4's indication scorer resolves this module-global normalizer at call time.
# Patch both the V1.4 module global and the shared comparator reference so every
# scoring path uses the same exact alias rule.
v14._clinical_norm_v14 = _clinical_norm_v15
base._clinical_norm = _clinical_norm_v15
base.DISCOVERY_VERSION = DISCOVERY_VERSION


def _compare_discovery_v15(request: base.DiscoveryCompareRequest) -> base.DiscoveryCompareResponse:
    result = _PREVIOUS_COMPARE(request)
    result.version = DISCOVERY_VERSION
    result.guardrails["verifiedDiseaseAliasNormalization"] = True
    result.guardrails["attrPolyneuropathyAliasNormalization"] = True
    result.guardrails["attrCardiomyopathyKeptDistinct"] = True
    result.guardrails["fuzzyMatching"] = False
    return result


base.compare_discovery = _compare_discovery_v15


def _self_test_v15() -> Dict[str, Any]:
    portfolio = base.PortfolioSnapshotRow(
        recordId="p-wainua-pn",
        company="AstraZeneca",
        asset="Wainua",
        molecule="eplontersen",
        developmentCode="ION-682884",
        indication="Hereditary transthyretin amyloidosis",
        controlledIndication="Hereditary Transthyretin Amyloidosis with Polyneuropathy (hATTR-PN)",
        phase="Approved",
    )

    source_pn = base.DiscoverySourceRow(
        company="AstraZeneca",
        sourceFamily="Company Pipeline",
        asset="Wainua",
        brand="Wainua",
        indication="patients with hereditary transthyretin-mediated amyloid polyneuropathy (ATTRv-PN)",
        phase="Phase 3",
        ownershipResolved=True,
    )
    score_pn, evidence_pn = base._indication_score(source_pn, portfolio)

    source_cm = base.DiscoverySourceRow(
        company="AstraZeneca",
        sourceFamily="Company Pipeline",
        asset="Wainua",
        brand="Wainua",
        indication="patients with hereditary or wild-type transthyretin-mediated amyloid cardiomyopathy (ATTR-CM)",
        phase="LCM",
        ownershipResolved=True,
    )
    score_cm, _ = base._indication_score(source_cm, portfolio)

    checks = {
        "attrv_pn_matches_hattr_pn": score_pn >= 72,
        "pn_match_has_deterministic_evidence": bool(evidence_pn),
        "attr_cm_remains_distinct": score_cm < 72,
        "standalone_hattr_pn_normalizes": (
            _clinical_norm_v15("hATTR-PN") == _clinical_norm_v15(_ATTR_PN_CANON)
        ),
        "standalone_attrv_pn_normalizes": (
            _clinical_norm_v15("ATTRv-PN") == _clinical_norm_v15(_ATTR_PN_CANON)
        ),
    }
    return {"ok": all(checks.values()), "checks": checks}


V15_SELF_TEST_RESULTS = _self_test_v15()
if not V15_SELF_TEST_RESULTS["ok"]:
    raise RuntimeError(f"Portfolio Discovery V1.5 self-test failed: {V15_SELF_TEST_RESULTS}")
