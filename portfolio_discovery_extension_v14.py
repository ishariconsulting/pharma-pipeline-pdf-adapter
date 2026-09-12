"""V1.4 additive precision patch for Portfolio Discovery.

Adds two deterministic, company-agnostic reconciliation rules exposed by the
58-row Pfizer regression canary:
1) receptor-status shorthand such as HR+/HER2- and written HR-positive /
   HER2-negative are normalized before punctuation stripping, so polarity is
   never corrupted by the older shorthand normalizer;
2) an exact study/program code plus exact development-code identity receives a
   small corroboration boost. This allows the same programme to reconcile when
   source and Portfolio differ only by a generic disease descriptor while
   remaining fail-closed for rows with a different study code.

No fuzzy matching and no master-data writes are introduced.
"""

import re
from typing import Any, List, Set, Tuple

import portfolio_discovery_extension_v11 as base
import portfolio_discovery_extension_v13  # noqa: F401 - installs V1.3 logic


DISCOVERY_VERSION = "V1.4.1 PORTFOLIO DISCOVERY READ ONLY - PRECISION QUALIFIER NORMALIZATION"

_v13_clinical_norm = base._clinical_norm
_v13_compare = base.compare_discovery


def _clinical_norm_v14(value: Any) -> str:
    text = base._clean(value)
    if not text:
        return ""

    # First canonicalize already-written polarity terms so V1.1's historical
    # `hr-` / `her2-` regex cannot partially match the hyphen in `HR-positive`
    # and produce corrupted strings such as `hr negativepositive`.
    written = [
        (r"(?<![A-Za-z0-9])HR\s*[- ]\s*positive\b", "HR positive"),
        (r"(?<![A-Za-z0-9])HR\s*[- ]\s*negative\b", "HR negative"),
        (r"(?<![A-Za-z0-9])HER2\s*[- ]\s*positive\b", "HER2 positive"),
        (r"(?<![A-Za-z0-9])HER2\s*[- ]\s*negative\b", "HER2 negative"),
    ]
    for pattern, repl in written:
        text = re.sub(pattern, repl, text, flags=re.I)

    # Preserve +/- polarity before the lower-level normalizer removes
    # punctuation. Do not use a word-boundary after +/-: these symbols are
    # non-word characters and are frequently adjacent to '/' or whitespace.
    shorthand = [
        (r"(?<![A-Za-z0-9])HR\s*\+(?![A-Za-z0-9])", "HR positive"),
        (r"(?<![A-Za-z0-9])HR\s*-(?![A-Za-z0-9])", "HR negative"),
        (r"(?<![A-Za-z0-9])HER2\s*\+(?![A-Za-z0-9])", "HER2 positive"),
        (r"(?<![A-Za-z0-9])HER2\s*-(?![A-Za-z0-9])", "HER2 negative"),
    ]
    for pattern, repl in shorthand:
        text = re.sub(pattern, repl, text, flags=re.I)

    return _v13_clinical_norm(text)


def _study_codes_v14(value: Any) -> Set[str]:
    """Conservative named trial/program extraction with compound study names.

    V1.1 covered e.g. MM-5 and MEVPRO-1 but not compound programme identifiers
    such as Symbiotic-GI-16 / Symbiotic-Lung-01. We still only inspect text in
    parentheses and require a known study family plus a numeric suffix.
    """
    text = base._clean(value)
    tokens: Set[str] = set()
    families = (
        "mm|ev|dv|mevpro|fourlight|talapro|her2climb|symbiotic|"
        "mountaineer|padl1nk|be6a"
    )
    for raw in re.findall(r"\(([^()]*)\)", text):
        n = base._norm(raw)
        if not n:
            continue
        # Allow up to two intermediate alpha/alphanumeric components between
        # the known family and final number: `symbiotic gi 16`, `be6a lung 01`.
        if re.search(rf"\b(?:{families})(?:\s+[a-z0-9]+){{0,2}}\s+\d+\b", n):
            tokens.add(n)
            continue
        # Retain V1.1's compact family-number shape such as MM-5 -> `mm 5`.
        if re.search(rf"\b(?:{families})\s*\d+\b", n):
            tokens.add(n)
    return tokens


def _indication_score_v14(
    source: base.DiscoverySourceRow,
    portfolio: base.PortfolioSnapshotRow,
) -> Tuple[int, List[str]]:
    evidence: List[str] = []
    source_raw = _clinical_norm_v14(source.indication)
    source_controlled = _clinical_norm_v14(source.controlledIndicationCandidate)
    p_raw = _clinical_norm_v14(portfolio.indication)
    p_controlled = _clinical_norm_v14(portfolio.controlledIndication)
    p_aliases = {
        _clinical_norm_v14(x)
        for x in portfolio.indicationAliases
        if _clinical_norm_v14(x)
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

    source_codes = _study_codes_v14(source.indication)
    portfolio_codes = _study_codes_v14(portfolio.indication)
    exact_study_code = bool(source_codes and portfolio_codes and source_codes & portfolio_codes)
    if exact_study_code:
        score += 30
        evidence.append("Exact study/program code")

    # Same development asset + same named study is strong deterministic evidence
    # that a wording difference is not a new indication. The boost is purposely
    # unavailable if either identifier is absent or the study codes differ.
    source_dev = base._norm(source.developmentCode)
    portfolio_dev = base._norm(portfolio.developmentCode)
    if exact_study_code and source_dev and portfolio_dev and source_dev == portfolio_dev:
        score += 15
        evidence.append("Exact development code corroborates exact study/program code")

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


base._clinical_norm = _clinical_norm_v14
base._indication_score = _indication_score_v14
base._study_codes = _study_codes_v14
base.DISCOVERY_VERSION = DISCOVERY_VERSION


def _compare_discovery_v14(request: base.DiscoveryCompareRequest) -> base.DiscoveryCompareResponse:
    result = _v13_compare(request)
    result.version = DISCOVERY_VERSION
    result.guardrails["receptorPolarityNormalization"] = True
    result.guardrails["compoundStudyCodeNormalization"] = True
    result.guardrails["exactStudyAndDevelopmentCodeCorroboration"] = True
    result.guardrails["fuzzyMatching"] = False
    return result


base.compare_discovery = _compare_discovery_v14


def _self_test_v14() -> dict:
    checks = {}

    # Pfizer FourLight wording: receptor polarity must survive normalization.
    s1 = base.DiscoverySourceRow(
        company="Pfizer",
        sourceFamily="Company Pipeline",
        asset="Atirmociclib",
        molecule="atirmociclib",
        developmentCode="PF-07220060",
        indication="1L HR+/HER2- Metastatic Breast Cancer (FourLight-3)",
        phase="Phase 3",
        ownershipResolved=True,
    )
    p1 = base.PortfolioSnapshotRow(
        recordId="p1",
        company="Pfizer",
        asset="Atirmociclib",
        molecule="atirmociclib",
        developmentCode="PF-07220060",
        indication="First-line HR-positive, HER2-negative metastatic breast cancer",
        phase="Phase 3",
    )
    score1, _ = _indication_score_v14(s1, p1)
    checks["receptor_polarity_match"] = score1 >= 72

    # Same Symbiotic study + same exact development code must reconcile despite
    # the source adding the generic noun 'Cancer'.
    s2 = base.DiscoverySourceRow(
        company="Pfizer",
        sourceFamily="Company Pipeline",
        asset="PF-08634404",
        developmentCode="PF-08634404",
        indication="1L Gastroesophageal Cancer (Symbiotic-GI-16)",
        phase="Phase 2",
        ownershipResolved=True,
    )
    p2 = base.PortfolioSnapshotRow(
        recordId="p2",
        company="Pfizer",
        asset="PF-08634404",
        developmentCode="PF-08634404",
        indication="1L Gastroesophageal (Symbiotic-GI-16)",
        phase="Phase 2",
    )
    score2, evidence2 = _indication_score_v14(s2, p2)
    checks["study_plus_development_code_match"] = (
        score2 >= 72
        and "Exact study/program code" in evidence2
        and "Exact development code corroborates exact study/program code" in evidence2
    )

    # Different study code must not receive the corroboration boost.
    p3 = base.PortfolioSnapshotRow(
        recordId="p3",
        company="Pfizer",
        asset="PF-08634404",
        developmentCode="PF-08634404",
        indication="1L Metastatic Colorectal Cancer (Symbiotic-GI-03)",
        phase="Phase 2",
    )
    score3, evidence3 = _indication_score_v14(s2, p3)
    checks["different_study_fails_closed"] = (
        "Exact development code corroborates exact study/program code" not in evidence3
        and score3 < 72
    )

    checks["symbiotic_code_extracted"] = (
        _study_codes_v14(s2.indication) == {"symbiotic gi 16"}
        and _study_codes_v14(p2.indication) == {"symbiotic gi 16"}
    )

    return {"ok": all(checks.values()), "checks": checks}


V14_SELF_TEST_RESULTS = _self_test_v14()
if not V14_SELF_TEST_RESULTS["ok"]:
    raise RuntimeError(f"Portfolio Discovery V1.4 self-test failed: {V14_SELF_TEST_RESULTS}")
