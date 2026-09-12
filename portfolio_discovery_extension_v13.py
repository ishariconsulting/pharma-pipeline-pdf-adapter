"""V1.3 additive clinical-normalization patch for Portfolio Discovery.

Extends V1.2 with deterministic, company-agnostic clinical abbreviation and
spelling normalization. This specifically reduces false NEW INDICATION results
when authoritative company pipeline pages use common disease abbreviations
(NSCLC, HCC, DLBCL, mCRPC, etc.) while Portfolio stores canonical disease names.
No fuzzy matching and no master-data writes are introduced.
"""

import re
from typing import Any, List, Set, Tuple

import portfolio_discovery_extension_v11 as base
import portfolio_discovery_extension_v12  # noqa: F401 - installs V1.2 phase logic


DISCOVERY_VERSION = "V1.3.0 PORTFOLIO DISCOVERY READ ONLY - CLINICAL NORMALIZATION"

_original_clinical_norm = base._clinical_norm
_original_indication_score = base._indication_score

# High-specificity clinical abbreviations only. Ambiguous abbreviations such as
# AD, PD, BC and EC are deliberately excluded and must resolve via the controlled
# Indications taxonomy/aliases supplied by the calling workflow.
_ABBREVIATIONS = [
    (r"\bnsclc\b", "non small cell lung cancer"),
    (r"\bsclc\b", "small cell lung cancer"),
    (r"\bhcc\b", "hepatocellular carcinoma"),
    (r"\bmcrc\b", "metastatic colorectal cancer"),
    (r"\bcrc\b", "colorectal cancer"),
    (r"\bmcrpc\b", "metastatic castration resistant prostate cancer"),
    (r"\bmcspc\b", "metastatic castration sensitive prostate cancer"),
    (r"\bdlbcl\b", "diffuse large b cell lymphoma"),
    (r"\bcll\b", "chronic lymphocytic leukemia"),
    (r"\bmcl\b", "mantle cell lymphoma"),
    (r"\bchl\b", "classical hodgkin lymphoma"),
    (r"\bbtc\b", "biliary tract cancer"),
    (r"\bpnh\b", "paroxysmal nocturnal hemoglobinuria"),
    (r"\bgmg\b", "generalized myasthenia gravis"),
    (r"\battr[- ]?cm\b", "transthyretin amyloid cardiomyopathy"),
    (r"\bcopd\b", "chronic obstructive pulmonary disease"),
    (r"\bcrswnp\b", "chronic rhinosinusitis with nasal polyps"),
    (r"\bmibc\b", "muscle invasive bladder cancer"),
    (r"\bnmibc\b", "non muscle invasive bladder cancer"),
    (r"\brrmm\b", "relapsed refractory multiple myeloma"),
]


def _clinical_norm_v13(value: Any) -> str:
    text = base._clean(value).lower()
    if not text:
        return ""

    # Harmonise common UK/US clinical spelling differences before phrase tests.
    spelling = [
        (r"\btumours\b", "tumors"),
        (r"\btumour\b", "tumor"),
        (r"\bleukaemia\b", "leukemia"),
        (r"\bhaemoglobin\b", "hemoglobin"),
        (r"\boesophageal\b", "esophageal"),
        (r"\bpaediatric\b", "pediatric"),
        (r"\bgeneralised\b", "generalized"),
        (r"\bhyperkalaemia\b", "hyperkalemia"),
    ]
    for pattern, repl in spelling:
        text = re.sub(pattern, repl, text, flags=re.I)

    for pattern, repl in _ABBREVIATIONS:
        text = re.sub(pattern, repl, text, flags=re.I)

    # Let the proven V1.1 logic normalize treatment-line/biomarker shorthand.
    return _original_clinical_norm(text)


def _indication_score_v13(
    source: base.DiscoverySourceRow,
    portfolio: base.PortfolioSnapshotRow,
) -> Tuple[int, List[str]]:
    evidence: List[str] = []
    source_raw = _clinical_norm_v13(source.indication)
    source_controlled = _clinical_norm_v13(source.controlledIndicationCandidate)
    p_raw = _clinical_norm_v13(portfolio.indication)
    p_controlled = _clinical_norm_v13(portfolio.controlledIndication)
    p_aliases = {
        _clinical_norm_v13(x)
        for x in portfolio.indicationAliases
        if _clinical_norm_v13(x)
    }

    score = 0
    if source_raw and p_raw and source_raw == p_raw:
        score = max(score, 100)
        evidence.append("Exact normalized source-facing indication")

    if source_controlled and (
        source_controlled == p_controlled or source_controlled in p_aliases
    ):
        score = max(score, 95)
        evidence.append("Exact controlled indication candidate")

    if source_raw and p_raw:
        source_tokens = source_raw.split()
        p_tokens = p_raw.split()
        shorter = source_raw if len(source_tokens) <= len(p_tokens) else p_raw
        longer = p_raw if shorter == source_raw else source_raw
        if len(shorter.split()) >= 3 and base._phrase_in(shorter, longer):
            score = max(score, 82)
            evidence.append("Deterministic source-indication containment")

    if p_controlled and source_raw and base._phrase_in(p_controlled, source_raw):
        score = max(score, 72)
        evidence.append("Controlled disease phrase present in source indication")

    for alias in p_aliases:
        if alias and source_raw and base._phrase_in(alias, source_raw):
            score = max(score, 72)
            evidence.append("Verified indication alias present in source indication")
            break

    source_codes = base._study_codes(source.indication)
    portfolio_codes = base._study_codes(portfolio.indication)
    if source_codes and portfolio_codes and source_codes & portfolio_codes:
        score += 30
        evidence.append("Exact study/program code")

    source_line = base._line_qualifier(source.indication)
    portfolio_line = base._line_qualifier(portfolio.indication)
    if not portfolio_line and portfolio.treatmentSettingLine:
        for value in portfolio.treatmentSettingLine:
            q = base._line_qualifier(value)
            if q:
                portfolio_line = q
                break
    if source_line and portfolio_line:
        if source_line == portfolio_line:
            score += 18
            evidence.append("Exact treatment-line qualifier")
        else:
            score -= 15
            evidence.append("Treatment-line conflict")

    source_flags = base._qualifier_flags(source.indication)
    portfolio_flags = base._qualifier_flags(
        " ".join([
            base._clean(portfolio.indication),
            base._clean(portfolio.biomarkerPatientSegment),
        ])
    )
    common_flags = source_flags & portfolio_flags
    if common_flags:
        score += min(18, 6 * len(common_flags))
        evidence.append("Qualifier agreement: " + ", ".join(sorted(common_flags)))

    source_phase = base._phase_canonical(source.phase)
    portfolio_phase = base._phase_canonical(portfolio.phase)
    if source_phase and portfolio_phase and source_phase == portfolio_phase:
        score += 12
        evidence.append("Exact canonical phase")

    return score, evidence


base._clinical_norm = _clinical_norm_v13
base._indication_score = _indication_score_v13
base.DISCOVERY_VERSION = DISCOVERY_VERSION

# V1.2 compare wrapper reads base.DISCOVERY_VERSION when its inner V1.1
# response is created, then V1.2 overwrites response.version with its constant.
# Wrap once more so the externally reported comparator version is V1.3.
_v12_compare = base.compare_discovery


def _compare_discovery_v13(request: base.DiscoveryCompareRequest) -> base.DiscoveryCompareResponse:
    result = _v12_compare(request)
    result.version = DISCOVERY_VERSION
    result.guardrails["clinicalAbbreviationNormalization"] = True
    result.guardrails["clinicalSpellingNormalization"] = True
    result.guardrails["fuzzyMatching"] = False
    return result


base.compare_discovery = _compare_discovery_v13


def _self_test_v13() -> dict:
    cases = {
        "NSCLC": "non small cell lung cancer",
        "HCC": "hepatocellular carcinoma",
        "mCRC": "metastatic colorectal cancer",
        "mCRPC": "metastatic castration resistant prostate cancer",
        "DLBCL": "diffuse large b cell lymphoma",
        "PNH": "paroxysmal nocturnal hemoglobinuria",
        "generalised myasthenia gravis": "generalized myasthenia gravis",
        "solid tumours": "solid tumors",
    }
    checks = {
        key: base._phrase_in(expected, _clinical_norm_v13(key))
        for key, expected in cases.items()
    }

    p = base.PortfolioSnapshotRow(
        recordId="p1",
        company="AstraZeneca",
        asset="Imfinzi",
        molecule="durvalumab",
        controlledIndication="Hepatocellular Carcinoma",
        indication="Hepatocellular carcinoma",
        phase="Approved",
    )
    s = base.DiscoverySourceRow(
        company="AstraZeneca",
        sourceFamily="Company Pipeline",
        asset="Imfinzi",
        brand="Imfinzi",
        indication="+ Imjudo HIMALAYA 1L unresectable HCC",
        phase="Phase 3",
        ownershipResolved=True,
    )
    score, _ = _indication_score_v13(s, p)
    checks["HCC_phrase_match"] = score >= 72

    return {"ok": all(checks.values()), "checks": checks}


V13_SELF_TEST_RESULTS = _self_test_v13()
if not V13_SELF_TEST_RESULTS["ok"]:
    raise RuntimeError(f"Portfolio Discovery V1.3 self-test failed: {V13_SELF_TEST_RESULTS}")
