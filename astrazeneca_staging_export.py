"""AstraZeneca Portfolio Discovery staging QA export.

This module is intentionally READ ONLY. It runs the validated Portfolio Discovery
comparator against the AstraZeneca official pipeline and the frozen AstraZeneca
Portfolio regression snapshot, then exposes/logs only actionable/review candidate
JSON for controlled staging QA. It never calls Airtable and never mutates
Portfolio, RPC, MRS, Queue, or existing automations.
"""

import asyncio
import json
from collections import Counter
from typing import Any, Dict, List, Tuple

import portfolio_discovery_extension_v11 as comparator
import portfolio_discovery_extension_v12  # noqa: F401
import portfolio_discovery_extension_v13  # noqa: F401
import portfolio_discovery_extension_v14  # noqa: F401
import astrazeneca_pipeline_adapter as az
import astrazeneca_pipeline_adapter_v13  # noqa: F401 - patches source parsing globals
from astrazeneca_reconciliation_canary import PORTFOLIO_SNAPSHOT, SNAPSHOT_AS_OF, _to_source_row


EXPORT_VERSION = "V1.2 ASTRAZENECA DISCOVERY STAGING EXPORT - SOURCE HYGIENE QA"
STAGE_CLASSES = {
    "NEW ASSET",
    "NEW INDICATION",
    "POSSIBLE DUPLICATE",
    "OWNERSHIP REVIEW",
}


def _compact(candidate: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "discoveryCandidateId": candidate.get("discoveryCandidateId"),
        "sourceFamily": candidate.get("sourceFamily"),
        "sourceRecordId": candidate.get("sourceRecordId"),
        "sourceUrl": candidate.get("sourceUrl"),
        "sourceWatchRecordId": candidate.get("sourceWatchRecordId"),
        "classification": candidate.get("classification"),
        "asset": candidate.get("asset"),
        "molecule": candidate.get("molecule"),
        "developmentCode": candidate.get("developmentCode"),
        "brand": candidate.get("brand"),
        "indication": candidate.get("indication"),
        "controlledIndicationCandidate": candidate.get("controlledIndicationCandidate"),
        "phase": candidate.get("phase"),
        "programStatus": candidate.get("programStatus"),
        "sponsorOwner": candidate.get("sponsorOwner"),
        "partners": candidate.get("partners") or [],
        "existingPortfolioRecordIds": candidate.get("existingPortfolioRecordIds") or [],
        "matchMethod": candidate.get("matchMethod"),
        "matchConfidence": candidate.get("matchConfidence"),
        "matchEvidence": candidate.get("matchEvidence") or [],
        "fieldDeltas": candidate.get("fieldDeltas") or [],
        "commercialInclusionDecision": candidate.get("commercialInclusionDecision"),
        "inclusionBasis": candidate.get("inclusionBasis") or [],
        "reviewReason": candidate.get("reviewReason"),
    }


async def _build_staging() -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    raw = await az._fetch_source_html()
    source_all = az.parse_pipeline_html(raw)
    source_in_scope = [r for r in source_all if r.commercialInScope]

    request = comparator.DiscoveryCompareRequest(
        company="AstraZeneca",
        sourceRows=[_to_source_row(r) for r in source_in_scope],
        portfolioRows=[comparator.PortfolioSnapshotRow(**row) for row in PORTFOLIO_SNAPSHOT],
        companyAliases=["AstraZeneca PLC"],
        batchRunId=f"AZ-STAGE-{SNAPSHOT_AS_OF}",
    )
    result = comparator.compare_discovery(request)
    stage = [_compact(c) for c in result.candidates if c.get("classification") in STAGE_CLASSES]
    counts = Counter(c.get("classification") for c in stage)
    summary = {
        "ok": True,
        "exportVersion": EXPORT_VERSION,
        "adapterVersion": az.AZ_PIPELINE_VERSION,
        "comparatorVersion": result.version,
        "batchRunId": request.batchRunId,
        "sourceRows": len(source_all),
        "commercialInScopeRows": len(source_in_scope),
        "portfolioSnapshotRows": len(PORTFOLIO_SNAPSHOT),
        "stagedCandidateCount": len(stage),
        "classificationCounts": dict(sorted(counts.items())),
        "masterWrites": False,
    }
    return summary, stage


async def run_staging_export() -> Dict[str, Any]:
    summary, stage = await _build_staging()
    for idx, candidate in enumerate(stage, start=1):
        print(
            "AZ_STAGE_CANDIDATE "
            + json.dumps(
                {
                    "exportVersion": EXPORT_VERSION,
                    "adapterVersion": summary["adapterVersion"],
                    "comparatorVersion": summary["comparatorVersion"],
                    "batchRunId": summary["batchRunId"],
                    "ordinal": idx,
                    "total": len(stage),
                    "candidate": candidate,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            flush=True,
        )
    print("AZ_STAGE_SUMMARY " + json.dumps(summary, separators=(",", ":")), flush=True)
    return summary


@az.app.get("/discover/astrazeneca/staging-candidates")
async def astrazeneca_staging_candidates() -> Dict[str, Any]:
    """Fixed-scope public-source QA snapshot; read-only and no arbitrary URL fetch."""
    summary, stage = await _build_staging()
    return {**summary, "readOnly": True, "candidates": stage}


@az.app.on_event("startup")
async def _schedule_staging_export() -> None:
    async def runner() -> None:
        try:
            await run_staging_export()
        except Exception as exc:
            print(
                f"AZ_STAGE_SUMMARY ok=False error={type(exc).__name__}:{exc}",
                flush=True,
            )

    asyncio.create_task(runner())
