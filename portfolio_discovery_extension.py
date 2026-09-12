import re
import unicodedata
from collections import Counter
from typing import Any, Dict, List, Optional, Set, Tuple

from fastapi import Header
from pydantic import BaseModel, Field

from main import _auth, app


DISCOVERY_VERSION = "V1.0.0 PORTFOLIO DISCOVERY READ ONLY"
DISCOVERY_CONTRACT = "PORTFOLIO_DISCOVERY_V1"
COMMERCIAL_POLICY = "COMMERCIAL_PORTFOLIO_V1"

INCLUDE_PHASES = {
    "phase 2",
    "phase 2 3",
    "phase 2/3",
    "phase 3",
    "filed",
    "filed registration",
    "registration",
    "filed / registration",
}

EXCLUDED_STATUS_TERMS = {
    "inactive",
    "discontinued",
    "terminated",
    "withdrawn",
    "suspended permanently",
}

CLASSIFICATIONS = {
    "MATCHED",
    "NEW ASSET",
    "NEW INDICATION",
    "POSSIBLE DUPLICATE",
    "OWNERSHIP REVIEW",
    "EXCLUDED BY RULE",
    "SOURCE UNAVAILABLE",
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
    )
    return re.sub(r"\s+", " ", value).strip()


def _norm(value: Any) -> str:
    value = _clean(value).lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


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


def _phase_norm(value: Any) -> str:
    n = _norm(value)
    n = n.replace("phase ii iii", "phase 2 3")
    n = n.replace("phase iii", "phase 3")
    n = n.replace("phase ii", "phase 2")
    n = n.replace("phase i", "phase 1")
    return n


def _commercial_decision(row: DiscoverySourceRow) -> Tuple[str, List[str], Optional[str]]:
    status = _norm(row.programStatus)
    if any(term in status for term in EXCLUDED_STATUS_TERMS):
        return "Exclude", ["Inactive / Discontinued"], "Source status is inactive/discontinued/terminated/withdrawn."

    if row.genericCommodity:
        return "Exclude", ["Generic / Commodity"], "Source identifies a generic/commodity product outside commercial scope."

    phase = _phase_norm(row.phase)

    if row.marketedStrategicRx:
        return "Include", ["Strategic Marketed Rx Brand"], None

    if row.importantLabelExpansion:
        return "Include", ["Important Label Expansion"], None

    if phase in INCLUDE_PHASES:
        if "filed" in phase or phase == "registration":
            return "Include", ["Filed / Registration"], None
        return "Include", ["Active Phase 2+"], None

    if phase == "phase 1":
        if row.strategicPhase1:
            return "Include", ["Strategic Phase 1"], None
        return "Exclude", ["Legacy / Low Commercial Value"], "Phase 1 is excluded unless explicitly strategic under COMMERCIAL_PORTFOLIO_V1."

    if not phase and not row.marketedStrategicRx and not row.importantLabelExpansion:
        return "Review", ["Insufficient Evidence"], "No source-backed commercial inclusion signal or eligible development phase."

    return "Review", ["Insufficient Evidence"], f"Phase/status '{_clean(row.phase)}' does not map deterministically to COMMERCIAL_PORTFOLIO_V1."


def _company_names(company: str, aliases: List[str]) -> Set[str]:
    out = {_norm(company)}
    out.update(_norm(x) for x in aliases if _norm(x))
    return {x for x in out if x}


def _ownership_issue(row: DiscoverySourceRow, target_company_names: Set[str]) -> Optional[str]:
    if row.ownershipResolved is False:
        return "Source explicitly indicates unresolved ownership/licensing."

    row_company = _norm(row.company)
    if row_company and row_company not in target_company_names:
        return f"Source company '{_clean(row.company)}' does not exactly resolve to target company/verified aliases."

    owner = _norm(row.sponsorOwner)
    if owner and owner not in target_company_names:
        partner_names = {_norm(x) for x in row.partners if _norm(x)}
        if owner not in partner_names:
            return (
                f"Source sponsor/owner '{_clean(row.sponsorOwner)}' does not exactly resolve "
                "to target company/verified aliases; ownership requires review."
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
    aliases = {_norm(x) for x in row.aliases if _norm(x)}
    return {
        "developmentCode": {_norm(row.developmentCode)} if _norm(row.developmentCode) else set(),
        "molecule": {_norm(row.molecule)} if _norm(row.molecule) else set(),
        "brand": {_norm(row.brand)} if _norm(row.brand) else set(),
        "asset": {_norm(row.asset)} if _norm(row.asset) else set(),
        "aliases": aliases,
    }


def _match_methods(source: DiscoverySourceRow, portfolio: PortfolioSnapshotRow) -> List[str]:
    s = _identity_values_source(source)
    p = _identity_values_portfolio(portfolio)
    methods: List[str] = []

    if s["developmentCode"] and (s["developmentCode"] & p["developmentCode"]):
        methods.append("Exact Development Code")
    if s["molecule"] and (s["molecule"] & p["molecule"]):
        methods.append("Exact Molecule / INN")
    if s["brand"] and (s["brand"] & p["brand"]):
        methods.append("Exact Brand")
    if s["asset"] and (s["asset"] & p["asset"]):
        methods.append("Exact Asset")

    source_all = set().union(*s.values())
    if source_all and p["aliases"] and (source_all & p["aliases"]):
        methods.append("Verified Alias")

    source_display = s["brand"] | s["asset"]
    portfolio_display = p["brand"] | p["asset"]
    if source_display and portfolio_display and (source_display & portfolio_display):
        if not any(x in methods for x in ["Exact Brand", "Exact Asset"]):
            methods.append("Composite Exact Identity")

    return methods


def _indication_set(row: PortfolioSnapshotRow) -> Set[str]:
    values = [row.indication, row.controlledIndication, *row.indicationAliases]
    return {_norm(v) for v in values if _norm(v)}


def _best_match_method(methods: List[str]) -> str:
    priority = [
        "Exact Development Code",
        "Exact Molecule / INN",
        "Exact Brand",
        "Exact Asset",
        "Verified Alias",
        "Composite Exact Identity",
    ]
    found = [x for x in priority if x in methods]
    if len(found) >= 2:
        return "Composite Exact Identity"
    if found:
        return found[0]
    return "No Match"


def _confidence(methods: List[str], indication_exact: bool) -> str:
    strong = {"Exact Development Code", "Exact Molecule / INN"}
    if len(set(methods) & strong) >= 1 and indication_exact:
        return "High"
    if len(methods) >= 2:
        return "High"
    if methods:
        return "Medium"
    return "Low"


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

        base = {
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
        }

        if source.sourceUnavailable:
            base["classification"] = "SOURCE UNAVAILABLE"
            base["commercialInclusionDecision"] = "Review"
            base["inclusionBasis"] = ["Insufficient Evidence"]
            base["reviewReason"] = "Authoritative discovery source was unavailable."
            candidates.append(base)
            continue

        if decision == "Exclude":
            base["classification"] = "EXCLUDED BY RULE"
            candidates.append(base)
            continue

        ownership_reason = _ownership_issue(source, target_names)
        if ownership_reason:
            base["classification"] = "OWNERSHIP REVIEW"
            base["commercialInclusionDecision"] = "Review"
            base["inclusionBasis"] = list(dict.fromkeys(inclusion_basis + ["Ownership Ambiguous"]))
            base["reviewReason"] = ownership_reason
            candidates.append(base)
            continue

        matched: List[Tuple[PortfolioSnapshotRow, List[str]]] = []
        for portfolio in request.portfolioRows:
            if portfolio.company and _norm(portfolio.company) not in target_names:
                continue
            methods = _match_methods(source, portfolio)
            if methods:
                matched.append((portfolio, methods))

        if not matched:
            base["classification"] = "NEW ASSET"
            candidates.append(base)
            continue

        matched_ids = [m[0].recordId for m in matched]
        base["existingPortfolioRecordIds"] = matched_ids

        source_indication = _norm(source.indication)
        indication_matches = [
            (portfolio, methods)
            for portfolio, methods in matched
            if source_indication and source_indication in _indication_set(portfolio)
        ]

        # Portfolio is asset x indication. One exact asset can legitimately have
        # several Portfolio rows, so duplicates are assessed only at exact
        # asset + exact indication grain.
        if len(indication_matches) > 1:
            distinct_methods = sorted({
                method
                for _, methods in indication_matches
                for method in methods
            })
            base["classification"] = "POSSIBLE DUPLICATE"
            base["existingPortfolioRecordIds"] = [m[0].recordId for m in indication_matches]
            base["matchMethod"] = _best_match_method(distinct_methods)
            base["matchConfidence"] = "Low"
            base["commercialInclusionDecision"] = "Review"
            base["reviewReason"] = (
                "More than one Portfolio record matches the same exact asset identity "
                "and exact indication; fail closed rather than selecting a record automatically."
            )
            candidates.append(base)
            continue

        if len(indication_matches) == 1:
            portfolio, methods = indication_matches[0]
            base["existingPortfolioRecordIds"] = [portfolio.recordId]
            base["matchMethod"] = _best_match_method(methods)
            base["matchConfidence"] = _confidence(methods, True)
            base["classification"] = "MATCHED"
            candidates.append(base)
            continue

        distinct_methods = sorted({method for _, methods in matched for method in methods})
        base["matchMethod"] = _best_match_method(distinct_methods)
        base["matchConfidence"] = "Medium" if distinct_methods else "Low"
        base["classification"] = "NEW INDICATION"

        if not source_indication:
            base["commercialInclusionDecision"] = "Review"
            base["reviewReason"] = (
                "Asset identity matched, but source indication is blank; "
                "indication-level comparison cannot be completed."
            )
        else:
            base["reviewReason"] = (
                "Asset identity matched exactly, but source indication did not exactly match "
                "any existing Portfolio indication/controlled indication/verified indication alias."
            )

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
            "ambiguousIdentityFailsClosed": True,
            "ambiguousOwnershipFailsClosed": True,
            "portfolioMutation": False,
            "rpcMutation": False,
            "mrsMutation": False,
            "existingAutomationMutation": False,
        },
    )


@app.get("/compare/portfolio-discovery/health")
async def portfolio_discovery_health() -> Dict[str, Any]:
    return {
        "ok": True,
        "version": DISCOVERY_VERSION,
        "contract": DISCOVERY_CONTRACT,
        "policy": COMMERCIAL_POLICY,
        "readOnly": True,
    }


@app.post("/compare/portfolio-discovery", response_model=DiscoveryCompareResponse)
async def portfolio_discovery_compare(
    request: DiscoveryCompareRequest,
    x_adapter_key: Optional[str] = Header(default=None),
) -> DiscoveryCompareResponse:
    _auth(x_adapter_key)
    return compare_discovery(request)
