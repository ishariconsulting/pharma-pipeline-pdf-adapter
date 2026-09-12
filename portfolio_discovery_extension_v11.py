import re
import unicodedata
from collections import Counter
from typing import Any, Dict, List, Optional, Set, Tuple

from fastapi import Header
from pydantic import BaseModel, Field

from main import _auth, app


DISCOVERY_VERSION = "V1.1.0 PORTFOLIO DISCOVERY READ ONLY"
DISCOVERY_CONTRACT = "PORTFOLIO_DISCOVERY_V1"
COMMERCIAL_POLICY = "COMMERCIAL_PORTFOLIO_V1"

CLASSIFICATIONS = {
    "MATCHED",
    "NEW ASSET",
    "NEW INDICATION",
    "POSSIBLE DUPLICATE",
    "OWNERSHIP REVIEW",
    "EXCLUDED BY RULE",
    "SOURCE UNAVAILABLE",
}

EXCLUDED_STATUS_TERMS = {
    "inactive",
    "discontinued",
    "terminated",
    "withdrawn",
    "suspended permanently",
}


def _clean(value: Any) -> str:
    if value is None:
        return ""
    value = unicodedata.normalize("NFKC", str(value))
    value = (
        value.replace("\u2010", "-")
        .replace("\u2011", "-")
        .replace("\u2012", "-")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("\u2212", "-")
        .replace("\u2265", ">=")
        .replace("\u2264", "<=")
    )
    return re.sub(r"\s+", " ", value).strip()


def _norm(value: Any) -> str:
    value = _clean(value).lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _phrase_in(phrase: str, text: str) -> bool:
    phrase = _norm(phrase)
    text = _norm(text)
    if not phrase or not text:
        return False
    return re.search(rf"(?:^|\s){re.escape(phrase)}(?:$|\s)", text) is not None


def _phase_canonical(value: Any) -> str:
    n = _norm(value)
    roman = {
        "phase i": "phase 1",
        "phase ii": "phase 2",
        "phase iii": "phase 3",
    }
    for old, new in roman.items():
        if n == old:
            n = new
    if n in {"registration", "filed", "filed registration", "filed / registration"}:
        return "registration"
    if "phase 2 3" in n or "phase 2/3" in _clean(value).lower():
        return "phase 2 3"
    m = re.search(r"\bphase\s*([123])\b", n)
    return f"phase {m.group(1)}" if m else n


def _clinical_norm(value: Any) -> str:
    text = _clean(value).lower()
    # Remove source metadata annotations that are not indication identity.
    text = re.sub(r"\(\s*biologic\s*\)", " ", text, flags=re.I)
    text = re.sub(
        r"\([^)]*(?:orphan|fast\s*track|prime|breakthrough|priority\s*review|rpd)[^)]*\)",
        " ",
        text,
        flags=re.I,
    )
    replacements = [
        (r"\b1l\b", "first line"),
        (r"\b2l\+\b", "second line plus"),
        (r"\b2l\b", "second line"),
        (r"\b3l\+\b", "third line plus"),
        (r"\b3l\b", "third line"),
        (r"\bhr\+\b", "hr positive"),
        (r"\bhr-\b", "hr negative"),
        (r"\bher2\+\b", "her2 positive"),
        (r"\bher2-\b", "her2 negative"),
        (r"\brr\b", "relapsed refractory"),
    ]
    for pattern, repl in replacements:
        text = re.sub(pattern, repl, text, flags=re.I)
    return _norm(text)


def _line_qualifier(value: Any) -> str:
    t = _clean(value).lower()
    checks = [
        (r"\b(?:1l|first[- ]line)\b", "1L"),
        (r"\b(?:2l\+|second[- ]line\s*plus)\b", "2L+"),
        (r"\b(?:2l|second[- ]line)\b", "2L"),
        (r"\b(?:3l\+|third[- ]line\s*plus)\b", "3L+"),
        (r"\b(?:3l|third[- ]line)\b", "3L"),
    ]
    for pattern, label in checks:
        if re.search(pattern, t, flags=re.I):
            return label
    return ""


def _study_codes(value: Any) -> Set[str]:
    text = _clean(value)
    # Deliberately conservative: capture named trial/program tokens containing a
    # digit and hyphen or a known study-name + digit suffix. Avoid biomarkers.
    tokens = set()
    for raw in re.findall(r"\(([^()]*)\)", text):
        n = _norm(raw)
        if not n:
            continue
        if re.search(r"(?:mm|ev|dv|mevpro|fourlight|talapro|her2climb|symbiotic|mountaineer|padl1nk)[ -]?\d+", n):
            tokens.add(n)
    return tokens


def _qualifier_flags(value: Any) -> Set[str]:
    t = _clinical_norm(value)
    flags: Set[str] = set()
    if "post transplant" in t or ("transplant" in t and "maintenance" in t):
        flags.add("transplant-maintenance")
    if "transplant ineligible" in t:
        flags.add("transplant-ineligible")
    if "post cd38" in t or "post cd 38" in t:
        flags.add("post-cd38")
    if "double class exposed" in t:
        flags.add("double-class-exposed")
    if "adjuvant" in t:
        flags.add("adjuvant")
    if "neoadjuvant" in t:
        flags.add("neoadjuvant")
    if "maintenance" in t:
        flags.add("maintenance")
    if "metastatic" in t:
        flags.add("metastatic")
    if "early breast cancer" in t or "early stage breast cancer" in t:
        flags.add("early-stage")
    return flags


class DiscoverySourceRow(BaseModel):
    company: str
    sourceFamily: str
    sourceRecordId: Optional[str] = None
    sourceUrl: Optional[str] = None
    sourceWatchRecordId: Optional[str] = None

    asset: Optional[str] = None
    molecule: Optional[str] = None
    developmentCode: Optional[str] = None
    brand: Optional[str] = None
    indication: Optional[str] = None
    controlledIndicationCandidate: Optional[str] = None
    phase: Optional[str] = None
    programStatus: Optional[str] = None
    sponsorOwner: Optional[str] = None
    partners: List[str] = Field(default_factory=list)

    sourceUnavailable: bool = False
    ownershipResolved: Optional[bool] = None

    strategicPhase1: bool = False
    importantLabelExpansion: bool = False
    marketedStrategicRx: bool = False
    genericCommodity: bool = False


class PortfolioSnapshotRow(BaseModel):
    recordId: str
    company: Optional[str] = None
    asset: Optional[str] = None
    molecule: Optional[str] = None
    developmentCode: Optional[str] = None
    brand: Optional[str] = None
    aliases: List[str] = Field(default_factory=list)
    indication: Optional[str] = None
    controlledIndication: Optional[str] = None
    indicationAliases: List[str] = Field(default_factory=list)
    treatmentSettingLine: List[str] = Field(default_factory=list)
    biomarkerPatientSegment: Optional[str] = None
    portfolioStatus: Optional[str] = None
    phase: Optional[str] = None


class DiscoveryCompareRequest(BaseModel):
    company: str
    sourceRows: List[DiscoverySourceRow]
    portfolioRows: List[PortfolioSnapshotRow]
    companyAliases: List[str] = Field(default_factory=list)
    batchRunId: Optional[str] = None


class DiscoveryCompareResponse(BaseModel):
    version: str
    contract: str
    policy: str
    company: str
    batchRunId: Optional[str] = None
    readOnly: bool
    sourceRowCount: int
    portfolioRowCount: int
    summary: Dict[str, int]
    candidates: List[Dict[str, Any]]
    guardrails: Dict[str, Any]


def _commercial_decision(row: DiscoverySourceRow) -> Tuple[str, List[str], Optional[str]]:
    status = _norm(row.programStatus)
    if any(term in status for term in EXCLUDED_STATUS_TERMS):
        return "Exclude", ["Inactive / Discontinued"], "Source status is inactive/discontinued/terminated/withdrawn."

    if row.genericCommodity:
        return "Exclude", ["Generic / Commodity"], "Source identifies a generic/commodity product outside commercial scope."

    phase = _phase_canonical(row.phase)
    if row.marketedStrategicRx:
        return "Include", ["Strategic Marketed Rx Brand"], None
    if row.importantLabelExpansion:
        return "Include", ["Important Label Expansion"], None
    if phase == "registration":
        return "Include", ["Filed / Registration"], None
    if phase in {"phase 2", "phase 2 3", "phase 3"}:
        return "Include", ["Active Phase 2+"], None
    if phase == "phase 1":
        if row.strategicPhase1:
            return "Include", ["Strategic Phase 1"], None
        return "Exclude", ["Legacy / Low Commercial Value"], "Phase 1 is excluded unless explicitly strategic under COMMERCIAL_PORTFOLIO_V1."
    return "Review", ["Insufficient Evidence"], "No deterministic commercial inclusion signal or eligible development phase."


def _company_names(company: str, aliases: List[str]) -> Set[str]:
    out = {_norm(company)}
    out.update(_norm(x) for x in aliases if _norm(x))
    return {x for x in out if x}


def _ownership_issue(row: DiscoverySourceRow, target_names: Set[str]) -> Optional[str]:
    if row.ownershipResolved is False:
        return "Source explicitly indicates unresolved ownership/licensing."

    row_company = _norm(row.company)
    if row_company and row_company not in target_names:
        return f"Source company '{_clean(row.company)}' does not exactly resolve to target company/verified aliases."

    owner = _norm(row.sponsorOwner)
    if owner and owner not in target_names and row.ownershipResolved is not True:
        return (
            f"Source sponsor/owner '{_clean(row.sponsorOwner)}' does not exactly resolve "
            "to target company/verified aliases and ownershipResolved was not explicitly true."
        )
    return None


def _identity_values_source(row: DiscoverySourceRow) -> Dict[str, Set[str]]:
    return {
        "developmentCode": {_norm(row.developmentCode)} if _norm(row.developmentCode) else set(),
        "molecule": {_norm(row.molecule)} if _norm(row.molecule) else set(),
        "brand": {_norm(row.brand)} if _norm(row.brand) else set(),
        "asset": {_norm(row.asset)} if _norm(row.asset) else set(),
    }


def _identity_values_portfolio(row: PortfolioSnapshotRow) -> Dict[str, Set[str]]:
    return {
        "developmentCode": {_norm(row.developmentCode)} if _norm(row.developmentCode) else set(),
        "molecule": {_norm(row.molecule)} if _norm(row.molecule) else set(),
        "brand": {_norm(row.brand)} if _norm(row.brand) else set(),
        "asset": {_norm(row.asset)} if _norm(row.asset) else set(),
        "aliases": {_norm(x) for x in row.aliases if _norm(x)},
    }


def _identity_components(value: Any) -> List[str]:
    raw = _clean(value)
    if not raw or "+" not in raw:
        return []
    parts = [_norm(x) for x in raw.split("+")]
    return [x for x in parts if x and len(x) >= 3]


def _source_identity_universe(row: DiscoverySourceRow) -> str:
    return _norm(" ".join([
        _clean(row.asset),
        _clean(row.molecule),
        _clean(row.brand),
        _clean(row.indication),
        " ".join(_clean(x) for x in row.partners),
    ]))


def _component_match(source: DiscoverySourceRow, portfolio: PortfolioSnapshotRow) -> bool:
    universe = _source_identity_universe(source)
    for candidate in [portfolio.brand, portfolio.molecule, portfolio.asset]:
        components = _identity_components(candidate)
        if len(components) < 2:
            continue
        if all(_phrase_in(component, universe) for component in components):
            return True
    return False


def _match_methods(source: DiscoverySourceRow, portfolio: PortfolioSnapshotRow) -> List[str]:
    s = _identity_values_source(source)
    p = _identity_values_portfolio(portfolio)
    methods: List[str] = []

    if s["developmentCode"] and s["developmentCode"] & p["developmentCode"]:
        methods.append("Exact Development Code")
    if s["molecule"] and s["molecule"] & p["molecule"]:
        methods.append("Exact Molecule / INN")
    if s["brand"] and s["brand"] & p["brand"]:
        methods.append("Exact Brand")
    if s["asset"] and s["asset"] & p["asset"]:
        methods.append("Exact Asset")

    source_all = set().union(*s.values())
    if source_all and p["aliases"] and source_all & p["aliases"]:
        methods.append("Verified Alias")

    if _component_match(source, portfolio):
        methods.append("Exact Combination Components")

    return list(dict.fromkeys(methods))


def _portfolio_indication_values(row: PortfolioSnapshotRow) -> List[str]:
    return [x for x in [row.indication, row.controlledIndication, *row.indicationAliases] if _clean(x)]


def _indication_score(source: DiscoverySourceRow, portfolio: PortfolioSnapshotRow) -> Tuple[int, List[str]]:
    evidence: List[str] = []
    source_raw = _clinical_norm(source.indication)
    source_controlled = _norm(source.controlledIndicationCandidate)
    p_raw = _clinical_norm(portfolio.indication)
    p_controlled = _norm(portfolio.controlledIndication)
    p_aliases = {_norm(x) for x in portfolio.indicationAliases if _norm(x)}

    score = 0
    if source_raw and p_raw and source_raw == p_raw:
        score = max(score, 100)
        evidence.append("Exact normalized source-facing indication")

    if source_controlled and (source_controlled == p_controlled or source_controlled in p_aliases):
        score = max(score, 95)
        evidence.append("Exact controlled indication candidate")

    if source_raw and p_raw:
        source_tokens = source_raw.split()
        p_tokens = p_raw.split()
        shorter = source_raw if len(source_tokens) <= len(p_tokens) else p_raw
        longer = p_raw if shorter == source_raw else source_raw
        if len(shorter.split()) >= 3 and _phrase_in(shorter, longer):
            score = max(score, 82)
            evidence.append("Deterministic source-indication containment")

    if p_controlled and source_raw and _phrase_in(p_controlled, source_raw):
        score = max(score, 72)
        evidence.append("Controlled disease phrase present in source indication")

    for alias in p_aliases:
        if alias and source_raw and _phrase_in(alias, source_raw):
            score = max(score, 72)
            evidence.append("Verified indication alias present in source indication")
            break

    source_codes = _study_codes(source.indication)
    portfolio_codes = _study_codes(portfolio.indication)
    if source_codes and portfolio_codes and source_codes & portfolio_codes:
        score += 30
        evidence.append("Exact study/program code")

    source_line = _line_qualifier(source.indication)
    portfolio_line = _line_qualifier(portfolio.indication)
    if not portfolio_line and portfolio.treatmentSettingLine:
        for value in portfolio.treatmentSettingLine:
            q = _line_qualifier(value)
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

    source_flags = _qualifier_flags(source.indication)
    portfolio_flags = _qualifier_flags(
        " ".join([_clean(portfolio.indication), _clean(portfolio.biomarkerPatientSegment)])
    )
    common_flags = source_flags & portfolio_flags
    if common_flags:
        score += min(18, 6 * len(common_flags))
        evidence.append("Qualifier agreement: " + ", ".join(sorted(common_flags)))

    source_phase = _phase_canonical(source.phase)
    portfolio_phase = _phase_canonical(portfolio.phase)
    if source_phase and portfolio_phase and source_phase == portfolio_phase:
        score += 12
        evidence.append("Exact canonical phase")

    return score, evidence


def _best_match_method(methods: List[str]) -> str:
    priority = [
        "Exact Development Code",
        "Exact Molecule / INN",
        "Exact Brand",
        "Exact Asset",
        "Verified Alias",
        "Exact Combination Components",
    ]
    found = [x for x in priority if x in methods]
    if "Exact Combination Components" in found:
        return "Composite Exact Identity"
    if len(found) >= 2:
        return "Composite Exact Identity"
    if found:
        return found[0]
    return "No Match"


def _match_confidence(methods: List[str], score: int) -> str:
    strong_identity = any(x in methods for x in [
        "Exact Development Code",
        "Exact Molecule / INN",
        "Exact Combination Components",
    ])
    if strong_identity and score >= 72:
        return "High"
    if len(methods) >= 2 and score >= 72:
        return "High"
    if methods and score >= 60:
        return "Medium"
    return "Low"


def _field_deltas(source: DiscoverySourceRow, portfolio: PortfolioSnapshotRow) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    source_phase = _phase_canonical(source.phase)
    portfolio_phase = _phase_canonical(portfolio.phase)
    if source_phase and portfolio_phase and source_phase != portfolio_phase:
        out.append({
            "field": "Development Phase",
            "sourceValue": _clean(source.phase),
            "portfolioValue": _clean(portfolio.phase),
            "normalizedSource": source_phase,
            "normalizedPortfolio": portfolio_phase,
        })
    return out


def _candidate_id(company: str, row: DiscoverySourceRow) -> str:
    parts = [
        _norm(company).replace(" ", "_"),
        _norm(row.sourceFamily).replace(" ", "_"),
        _norm(row.sourceRecordId or "").replace(" ", "_"),
        _norm(row.asset or row.brand or row.molecule or row.developmentCode or "").replace(" ", "_"),
        _norm(row.indication or "").replace(" ", "_"),
    ]
    return "|".join(parts)


def compare_discovery(request: DiscoveryCompareRequest) -> DiscoveryCompareResponse:
    target_names = _company_names(request.company, request.companyAliases)
    candidates: List[Dict[str, Any]] = []

    for source in request.sourceRows:
        decision, inclusion_basis, review_reason = _commercial_decision(source)
        base: Dict[str, Any] = {
            "discoveryCandidateId": _candidate_id(request.company, source),
            "sourceFamily": source.sourceFamily,
            "sourceRecordId": source.sourceRecordId,
            "sourceUrl": source.sourceUrl,
            "sourceWatchRecordId": source.sourceWatchRecordId,
            "asset": source.asset,
            "molecule": source.molecule,
            "developmentCode": source.developmentCode,
            "brand": source.brand,
            "indication": source.indication,
            "controlledIndicationCandidate": source.controlledIndicationCandidate,
            "phase": source.phase,
            "programStatus": source.programStatus,
            "sponsorOwner": source.sponsorOwner,
            "partners": source.partners,
            "commercialInclusionDecision": decision,
            "inclusionBasis": inclusion_basis,
            "reviewReason": review_reason,
            "existingPortfolioRecordIds": [],
            "matchMethod": "No Match",
            "matchConfidence": "Low",
            "matchEvidence": [],
            "fieldDeltas": [],
        }

        if source.sourceUnavailable:
            base.update({
                "classification": "SOURCE UNAVAILABLE",
                "commercialInclusionDecision": "Review",
                "inclusionBasis": ["Insufficient Evidence"],
                "reviewReason": "Authoritative discovery source was unavailable.",
            })
            candidates.append(base)
            continue

        if decision == "Exclude":
            base["classification"] = "EXCLUDED BY RULE"
            candidates.append(base)
            continue

        ownership_reason = _ownership_issue(source, target_names)
        if ownership_reason:
            base.update({
                "classification": "OWNERSHIP REVIEW",
                "commercialInclusionDecision": "Review",
                "inclusionBasis": list(dict.fromkeys(inclusion_basis + ["Ownership Ambiguous"])),
                "reviewReason": ownership_reason,
            })
            candidates.append(base)
            continue

        identity_matches: List[Tuple[PortfolioSnapshotRow, List[str]]] = []
        for portfolio in request.portfolioRows:
            if portfolio.company and _norm(portfolio.company) not in target_names:
                continue
            methods = _match_methods(source, portfolio)
            if methods:
                identity_matches.append((portfolio, methods))

        if not identity_matches:
            base["classification"] = "NEW ASSET"
            candidates.append(base)
            continue

        ranked: List[Tuple[int, PortfolioSnapshotRow, List[str], List[str]]] = []
        for portfolio, methods in identity_matches:
            score, evidence = _indication_score(source, portfolio)
            ranked.append((score, portfolio, methods, evidence))
        ranked.sort(key=lambda x: x[0], reverse=True)

        best_score = ranked[0][0]
        plausible = [x for x in ranked if x[0] >= 72]
        tied_best = [x for x in plausible if x[0] == best_score]

        if plausible and len(tied_best) == 1:
            score, portfolio, methods, evidence = tied_best[0]
            base.update({
                "classification": "MATCHED",
                "existingPortfolioRecordIds": [portfolio.recordId],
                "matchMethod": _best_match_method(methods),
                "matchConfidence": _match_confidence(methods, score),
                "matchEvidence": evidence,
                "fieldDeltas": _field_deltas(source, portfolio),
                "reviewReason": (
                    "Existing Portfolio representation matched; read-only field delta requires downstream QA."
                    if _field_deltas(source, portfolio)
                    else review_reason
                ),
            })
            candidates.append(base)
            continue

        if plausible and len(tied_best) > 1:
            methods = sorted({m for _, _, ms, _ in tied_best for m in ms})
            base.update({
                "classification": "POSSIBLE DUPLICATE",
                "commercialInclusionDecision": "Review",
                "existingPortfolioRecordIds": [x[1].recordId for x in tied_best],
                "matchMethod": _best_match_method(methods),
                "matchConfidence": "Low",
                "matchEvidence": ["Multiple existing Portfolio rows remain equally plausible at asset/indication qualifier grain."],
                "reviewReason": "Fail closed: exact asset identity exists but qualifier-level reconciliation is ambiguous.",
            })
            candidates.append(base)
            continue

        # Exact identity exists, but no current Portfolio indication is a
        # deterministic disease/qualifier match. This is the only path to
        # NEW INDICATION. It deliberately avoids raw-string-only decisions.
        all_methods = sorted({m for _, _, ms, _ in ranked for m in ms})
        base.update({
            "classification": "NEW INDICATION",
            "existingPortfolioRecordIds": [x[1].recordId for x in ranked],
            "matchMethod": _best_match_method(all_methods),
            "matchConfidence": "Medium" if all_methods else "Low",
            "matchEvidence": ["Exact asset identity exists, but no deterministic indication/qualifier match reached threshold."],
            "reviewReason": "Asset exists in Portfolio; source indication appears distinct after deterministic normalization. Review before any master-data write.",
        })
        candidates.append(base)

    counts = Counter(c["classification"] for c in candidates)
    summary = {name: int(counts.get(name, 0)) for name in sorted(CLASSIFICATIONS)}

    return DiscoveryCompareResponse(
        version=DISCOVERY_VERSION,
        contract=DISCOVERY_CONTRACT,
        policy=COMMERCIAL_POLICY,
        company=request.company,
        batchRunId=request.batchRunId,
        readOnly=True,
        sourceRowCount=len(request.sourceRows),
        portfolioRowCount=len(request.portfolioRows),
        summary=summary,
        candidates=candidates,
        guardrails={
            "masterWrites": False,
            "fuzzyMatching": False,
            "deterministicClinicalNormalization": True,
            "componentAwareCombinationMatching": True,
            "ambiguousIdentityFailsClosed": True,
            "ambiguousOwnershipFailsClosed": True,
            "phaseStatusDeltasAreReadOnly": True,
            "portfolioMutation": False,
            "rpcMutation": False,
            "mrsMutation": False,
            "existingAutomationMutation": False,
        },
    )


def _self_test() -> Dict[str, Any]:
    portfolio = [
        PortfolioSnapshotRow(
            recordId="rec_exact",
            company="Pfizer",
            asset="atirmociclib",
            molecule="atirmociclib",
            developmentCode="PF-07220060",
            indication="First-line HR-positive, HER2-negative metastatic breast cancer",
            controlledIndication="Breast Cancer",
            phase="Phase 3",
        ),
        PortfolioSnapshotRow(
            recordId="rec_combo",
            company="Pfizer",
            asset="TALZENNA + XTANDI",
            molecule="talazoparib + enzalutamide",
            brand="TALZENNA + XTANDI",
            indication="HRR gene-altered metastatic castration-sensitive prostate cancer",
            controlledIndication="Prostate Cancer",
            phase="Filed / Registration",
        ),
        PortfolioSnapshotRow(
            recordId="rec_lyme",
            company="Pfizer",
            asset="VLA15",
            developmentCode="PF-07307405",
            indication="Prevention of Lyme disease",
            controlledIndication="Lyme Disease",
            phase="Filed / Registration",
        ),
    ]

    sources = [
        DiscoverySourceRow(
            company="Pfizer",
            sourceFamily="Company Pipeline",
            sourceRecordId="1",
            asset="atirmociclib (PF-07220060)",
            developmentCode="PF-07220060",
            indication="1L HR+/HER2- Metastatic Breast Cancer (FourLight-3)",
            phase="Phase 3",
        ),
        DiscoverySourceRow(
            company="Pfizer",
            sourceFamily="Company Pipeline",
            sourceRecordId="2",
            asset="TALZENNA (talazoparib)",
            indication="Combo w/ XTANDI (enzalutamide) for DNA Damage Repair (DDR)-Deficient Metastatic Castration Sensitive Prostate Cancer (TALAPRO-3)",
            phase="Registration",
        ),
        DiscoverySourceRow(
            company="Pfizer",
            sourceFamily="Company Pipeline",
            sourceRecordId="3",
            asset="PF-07307405",
            developmentCode="PF-07307405",
            indication="Lyme Disease",
            phase="Phase 3",
        ),
        DiscoverySourceRow(
            company="Pfizer",
            sourceFamily="Company Pipeline",
            sourceRecordId="4",
            asset="PF-NEW-ASSET",
            developmentCode="PF-NEW-ASSET",
            indication="Novel Disease",
            phase="Phase 2",
        ),
        DiscoverySourceRow(
            company="Pfizer",
            sourceFamily="Company Pipeline",
            sourceRecordId="5",
            asset="PF-PH1",
            developmentCode="PF-PH1",
            indication="Exploratory Disease",
            phase="Phase 1",
        ),
    ]

    result = compare_discovery(DiscoveryCompareRequest(
        company="Pfizer",
        companyAliases=["Pfizer Inc."],
        sourceRows=sources,
        portfolioRows=portfolio,
        batchRunId="SELF_TEST",
    ))
    by_id = {c["sourceRecordId"]: c for c in result.candidates}
    checks = {
        "clinical_normalization_match": by_id["1"]["classification"] == "MATCHED",
        "combination_component_match": by_id["2"]["classification"] == "MATCHED",
        "phase_delta_existing_identity": (
            by_id["3"]["classification"] == "MATCHED"
            and len(by_id["3"]["fieldDeltas"]) == 1
        ),
        "new_asset": by_id["4"]["classification"] == "NEW ASSET",
        "phase1_excluded": by_id["5"]["classification"] == "EXCLUDED BY RULE",
    }
    return {
        "ok": all(checks.values()),
        "checks": checks,
        "summary": result.summary,
    }


SELF_TEST_RESULTS = _self_test()
if not SELF_TEST_RESULTS["ok"]:
    raise RuntimeError(f"Portfolio discovery V1.1 self-test failed: {SELF_TEST_RESULTS}")


@app.get("/compare/portfolio-discovery/health")
async def portfolio_discovery_health() -> Dict[str, Any]:
    return {
        "ok": True,
        "version": DISCOVERY_VERSION,
        "contract": DISCOVERY_CONTRACT,
        "policy": COMMERCIAL_POLICY,
        "readOnly": True,
        "selfTest": SELF_TEST_RESULTS,
    }


@app.get("/compare/portfolio-discovery/self-test")
async def portfolio_discovery_self_test() -> Dict[str, Any]:
    return {
        "version": DISCOVERY_VERSION,
        "readOnly": True,
        **SELF_TEST_RESULTS,
    }


@app.post("/compare/portfolio-discovery", response_model=DiscoveryCompareResponse)
async def portfolio_discovery_compare(
    request: DiscoveryCompareRequest,
    x_adapter_key: Optional[str] = Header(default=None),
) -> DiscoveryCompareResponse:
    _auth(x_adapter_key)
    return compare_discovery(request)
