"""Hotfix for the read-only AstraZeneca reconciliation canary.

The V1 canary represented fieldDeltas as a list of delta dictionaries, but its
summary loop treated that list as a dictionary. This patch replaces only the
read-only run_canary function. No Airtable/master-data writes are introduced.
"""

from collections import Counter
from typing import Any, Dict

import astrazeneca_reconciliation_canary as canary


async def run_canary_fixed() -> Dict[str, Any]:
    raw = await canary.az._fetch_source_html()
    source_all = canary.az.parse_pipeline_html(raw)
    source_in_scope = [r for r in source_all if r.commercialInScope]

    request = canary.comparator.DiscoveryCompareRequest(
        company="AstraZeneca",
        sourceRows=[canary._to_source_row(r) for r in source_in_scope],
        portfolioRows=[
            canary.comparator.PortfolioSnapshotRow(**row)
            for row in canary.PORTFOLIO_SNAPSHOT
        ],
        companyAliases=["AstraZeneca PLC"],
        batchRunId=f"AZ-CANARY-{canary.SNAPSHOT_AS_OF}",
    )
    result = canary.comparator.compare_discovery(request)
    summary = dict(result.summary)

    delta_counts = Counter()
    for candidate in result.candidates:
        for delta in candidate.get("fieldDeltas") or []:
            if isinstance(delta, dict) and delta.get("field"):
                delta_counts[str(delta["field"])] += 1

    unresolved = [
        canary._compact_candidate(c)
        for c in result.candidates
        if c.get("classification") not in {"MATCHED", "EXCLUDED BY RULE"}
    ]

    # Include small quality diagnostics so we can assess whether discovery is
    # producing useful candidates or systematic false positives before staging.
    confidence_counts = Counter(
        str(c.get("matchConfidence") or "Unknown") for c in result.candidates
    )
    method_counts = Counter(
        str(c.get("matchMethod") or "No Match") for c in result.candidates
    )

    return {
        "version": result.version,
        "sourceRows": len(source_all),
        "commercialInScopeRows": len(source_in_scope),
        "portfolioSnapshotRows": len(canary.PORTFOLIO_SNAPSHOT),
        "summary": summary,
        "fieldDeltaCounts": dict(delta_counts),
        "matchConfidence": dict(confidence_counts),
        "matchMethods": dict(method_counts),
        "unresolvedCount": len(unresolved),
        "unresolvedSample": unresolved[:30],
    }


canary.run_canary = run_canary_fixed
