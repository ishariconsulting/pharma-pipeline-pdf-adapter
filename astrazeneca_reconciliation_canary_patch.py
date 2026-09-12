"""Read-only quality patch for the AstraZeneca reconciliation canary.

Fixes field-delta aggregation and emits compact diagnostic slices so the
comparator can be tuned before any candidate staging or master-data writes.
"""

from collections import Counter, defaultdict
from typing import Any, Dict, List

import astrazeneca_reconciliation_canary as canary


def _compact(candidate: Dict[str, Any]) -> str:
    asset = (
        candidate.get("asset")
        or candidate.get("brand")
        or candidate.get("molecule")
        or candidate.get("developmentCode")
        or "?"
    )
    indication = candidate.get("indication") or "?"
    phase = candidate.get("phase") or "?"
    classification = candidate.get("classification") or "?"
    existing = candidate.get("existingPortfolioRecordIds") or []
    method = candidate.get("matchMethod") or "No Match"
    evidence = candidate.get("matchEvidence") or []
    deltas = candidate.get("fieldDeltas") or []
    return (
        f"{classification}|{phase}|{asset}|{indication}|"
        f"existing={len(existing)}|method={method}|evidence={evidence}|delta={deltas}"
    )


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
    confidence_counts = Counter()
    method_counts = Counter()
    phase_class_counts = Counter()
    class_samples: Dict[str, List[str]] = defaultdict(list)

    for candidate in result.candidates:
        classification = str(candidate.get("classification") or "UNKNOWN")
        phase = str(candidate.get("phase") or "UNKNOWN")
        phase_class_counts[f"{phase}|{classification}"] += 1
        confidence_counts[str(candidate.get("matchConfidence") or "Unknown")] += 1
        method_counts[str(candidate.get("matchMethod") or "No Match")] += 1
        for delta in candidate.get("fieldDeltas") or []:
            if isinstance(delta, dict) and delta.get("field"):
                delta_counts[str(delta["field"])] += 1
        if len(class_samples[classification]) < 12:
            class_samples[classification].append(_compact(candidate))

    unresolved = [
        _compact(c)
        for c in result.candidates
        if c.get("classification") not in {"MATCHED", "EXCLUDED BY RULE"}
    ]

    return {
        "version": result.version,
        "sourceRows": len(source_all),
        "commercialInScopeRows": len(source_in_scope),
        "portfolioSnapshotRows": len(canary.PORTFOLIO_SNAPSHOT),
        "summary": summary,
        "phaseClassification": dict(sorted(phase_class_counts.items())),
        "fieldDeltaCounts": dict(delta_counts),
        "matchConfidence": dict(confidence_counts),
        "matchMethods": dict(method_counts),
        "classificationSamples": dict(class_samples),
        "unresolvedCount": len(unresolved),
        "unresolvedSample": unresolved[:30],
    }


canary.run_canary = run_canary_fixed
