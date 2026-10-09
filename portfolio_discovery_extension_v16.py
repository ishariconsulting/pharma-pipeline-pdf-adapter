"""V1.6 additive deterministic identity-variant patch for Portfolio Discovery.

Purpose
-------
Recover exact product identity when an official source decorates the product
name with a development code, e.g. "PRODUCT (ABC-1234)", or when an existing
Portfolio molecule carries a standard four-letter biologic suffix.

Guardrails
----------
- deterministic exact variants only;
- no fuzzy matching;
- no company-specific branches;
- parenthetical text becomes a development-code variant only when it is
  compact and contains both letters and digits;
- combination identities remain combinations; component identities are not
  inferred from arbitrary slash/plus text;
- no master-data writes.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Set

import portfolio_discovery_extension_v11 as base
import portfolio_discovery_extension_v15  # noqa: F401 - installs V1.5 clinical aliases


DISCOVERY_VERSION = (
    "V1.6.0 PORTFOLIO DISCOVERY READ ONLY - DETERMINISTIC IDENTITY VARIANTS"
)

_PREVIOUS_COMPARE = base.compare_discovery
_PREVIOUS_SOURCE_IDENTITIES = base._identity_values_source
_PREVIOUS_PORTFOLIO_IDENTITIES = base._identity_values_portfolio


_PAREN_RE = re.compile(r"^(.+?)\s*\(([^()]*)\)\s*$")
_BIOLOGIC_SUFFIX_RE = re.compile(
    r"^([A-Za-z][A-Za-z0-9]*?(?:mab|cept|grastim|poetin|tide))-[a-z]{4}$",
    flags=re.I,
)


def _norm_set(values: Set[str]) -> Set[str]:
    return {base._norm(x) for x in values if base._norm(x)}


def _looks_like_development_code(value: Any) -> bool:
    raw = base._clean(value)
    if not raw or len(raw) > 48 or re.search(r"\s", raw):
        return False
    if not re.search(r"[A-Za-z]", raw) or not re.search(r"\d", raw):
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]*", raw))


def _identity_variants(value: Any) -> Set[str]:
    raw = base._clean(value)
    if not raw:
        return set()

    out: Set[str] = {base._norm(raw)}

    parenthetical = _PAREN_RE.match(raw)
    if parenthetical:
        outer = base._clean(parenthetical.group(1))
        if outer:
            out.add(base._norm(outer))

    biologic = _BIOLOGIC_SUFFIX_RE.match(raw)
    if biologic:
        out.add(base._norm(biologic.group(1)))

    return {x for x in out if x}


def _parenthetical_development_codes(value: Any) -> Set[str]:
    raw = base._clean(value)
    match = _PAREN_RE.match(raw)
    if not match:
        return set()

    inner = base._clean(match.group(2))
    candidates = [
        base._clean(x)
        for x in re.split(r"[,;|]+", inner)
        if base._clean(x)
    ]
    return _norm_set(
        {x for x in candidates if _looks_like_development_code(x)}
    )


def _identity_values_source_v16(
    row: base.DiscoverySourceRow,
) -> Dict[str, Set[str]]:
    prior = _PREVIOUS_SOURCE_IDENTITIES(row)

    development_codes = set(prior.get("developmentCode", set()))
    for value in (row.asset, row.molecule, row.brand):
        development_codes.update(_parenthetical_development_codes(value))

    return {
        "developmentCode": development_codes,
        "molecule": set(prior.get("molecule", set()))
        | _identity_variants(row.molecule),
        "brand": set(prior.get("brand", set()))
        | _identity_variants(row.brand),
        "asset": set(prior.get("asset", set()))
        | _identity_variants(row.asset),
    }


def _identity_values_portfolio_v16(
    row: base.PortfolioSnapshotRow,
) -> Dict[str, Set[str]]:
    prior = _PREVIOUS_PORTFOLIO_IDENTITIES(row)

    return {
        "developmentCode": set(prior.get("developmentCode", set()))
        | _identity_variants(row.developmentCode),
        "molecule": set(prior.get("molecule", set()))
        | _identity_variants(row.molecule),
        "brand": set(prior.get("brand", set()))
        | _identity_variants(row.brand),
        "asset": set(prior.get("asset", set()))
        | _identity_variants(row.asset),
        "aliases": set(prior.get("aliases", set()))
        | set().union(*[_identity_variants(x) for x in row.aliases])
        if row.aliases
        else set(prior.get("aliases", set())),
    }


base._identity_values_source = _identity_values_source_v16
base._identity_values_portfolio = _identity_values_portfolio_v16
base.DISCOVERY_VERSION = DISCOVERY_VERSION


def _compare_discovery_v16(
    request: base.DiscoveryCompareRequest,
) -> base.DiscoveryCompareResponse:
    result = _PREVIOUS_COMPARE(request)
    result.version = DISCOVERY_VERSION
    result.guardrails["deterministicIdentityVariants"] = True
    result.guardrails["parentheticalDevelopmentCodeVariants"] = True
    result.guardrails["biologicSuffixBaseVariant"] = True
    result.guardrails["componentInferenceFromCompositeIdentity"] = False
    result.guardrails["fuzzyMatching"] = False

    # Explicit opt-in ONLY: inspect possible pre-existing asset identities.
    # Existing comparator decisions, match fields, summary and default API
    # output are unchanged. This never establishes exact programme scope.
    if request.includeAssetPresence:
        from r1c_shared_lineage import assess_asset_presence

        if len(result.candidates) != len(request.sourceRows):
            raise RuntimeError(
                "Asset-presence assessment blocked: source/result count mismatch"
            )
        portfolio_snapshot = [p.model_dump() for p in request.portfolioRows]
        for source, candidate in zip(request.sourceRows, result.candidates):
            # Exclusions, missing sources, ownership-review cases and actual
            # matches must not be weakened by a parallel identity diagnostic.
            if candidate["classification"] != "NEW ASSET":
                continue
            source_snapshot = source.model_dump()
            if base._norm(source.company) != base._norm(request.company):
                # Reject inconsistent source→request company routing rather
                # than silently aliasing different company views.
                source_snapshot["company"] = ""
            candidate["assetPresence"] = assess_asset_presence(
                source_snapshot,
                portfolio_snapshot,
                observed_classification=candidate["classification"],
            )
        result.guardrails["assetPresenceOptIn"] = True
        result.guardrails["assetPresenceProgrammeApproval"] = False
        result.guardrails["assetPresenceCandidateWrites"] = False
        result.guardrails["assetPresencePortfolioWrites"] = False
        result.guardrails["assetPresenceVersion"] = "R1C_ASSET_PRESENCE_V1_READ_ONLY"
    return result


base.compare_discovery = _compare_discovery_v16


def _self_test_v16() -> Dict[str, Any]:
    source_parenthetical = base.DiscoverySourceRow(
        company="Example Pharma",
        sourceFamily="Company Pipeline",
        asset="ALPHAMAB (ABC-1234)",
        molecule="ALPHAMAB (ABC-1234)",
        indication="Example disease",
        phase="Phase 3",
        ownershipResolved=True,
    )
    portfolio_parenthetical = base.PortfolioSnapshotRow(
        recordId="p-parenthetical",
        company="Example Pharma",
        asset="ALPHAMAB",
        molecule="alphamab",
        developmentCode="ABC-1234",
        indication="Example disease",
        controlledIndication="Example disease",
        phase="Phase 3",
    )

    source_suffix = base.DiscoverySourceRow(
        company="Example Pharma",
        sourceFamily="Company Pipeline",
        asset="BETAMAB",
        molecule="betamab",
        indication="Second disease",
        phase="Phase 2",
        ownershipResolved=True,
    )
    portfolio_suffix = base.PortfolioSnapshotRow(
        recordId="p-suffix",
        company="Example Pharma",
        asset="BETA",
        molecule="betamab-abcd",
        indication="Second disease",
        controlledIndication="Second disease",
        phase="Phase 2",
    )

    source_component = base.DiscoverySourceRow(
        company="Example Pharma",
        sourceFamily="Company Pipeline",
        asset="GAMMAMAB",
        molecule="gammamab",
        indication="Third disease",
        phase="Phase 2",
        ownershipResolved=True,
    )
    portfolio_combo = base.PortfolioSnapshotRow(
        recordId="p-combo",
        company="Example Pharma",
        asset="GAMMAMAB + DELTAMAB",
        molecule="gammamab + deltamab",
        indication="Third disease",
        controlledIndication="Third disease",
        phase="Phase 2",
    )

    result = base.compare_discovery(
        base.DiscoveryCompareRequest(
            company="Example Pharma",
            sourceRows=[
                source_parenthetical,
                source_suffix,
                source_component,
            ],
            portfolioRows=[
                portfolio_parenthetical,
                portfolio_suffix,
                portfolio_combo,
            ],
            batchRunId="V16_SELF_TEST",
        )
    )
    by_asset = {base._clean(x["asset"]): x for x in result.candidates}

    checks = {
        "parenthetical_name_matches": (
            by_asset["ALPHAMAB (ABC-1234)"]["classification"] == "MATCHED"
        ),
        "biologic_suffix_matches": (
            by_asset["BETAMAB"]["classification"] == "MATCHED"
        ),
        "monotherapy_not_collapsed_into_combo": (
            by_asset["GAMMAMAB"]["classification"] == "NEW ASSET"
        ),
        "parenthetical_code_extracted": (
            "abc 1234"
            in _identity_values_source_v16(source_parenthetical)["developmentCode"]
        ),
    }
    return {"ok": all(checks.values()), "checks": checks}


V16_SELF_TEST_RESULTS = _self_test_v16()
if not V16_SELF_TEST_RESULTS["ok"]:
    raise RuntimeError(
        f"Portfolio Discovery V1.6 self-test failed: {V16_SELF_TEST_RESULTS}"
    )
