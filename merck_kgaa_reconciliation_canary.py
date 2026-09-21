"""Read-only Merck KGaA first-party data.js -> current Portfolio reconciliation.

Uses the live first-party pipelineData source and a bounded snapshot of the
relevant current Airtable Portfolio rows. No Airtable/master-data writes.
"""
from __future__ import annotations

import asyncio
import json
from collections import Counter
from typing import Any, Dict, List

import merck_kgaa_js_pipeline_extension as merck
import portfolio_discovery_extension_v11 as comparator
import portfolio_discovery_extension_v12  # noqa: F401 - patches comparator

SOURCE_WATCH_RECORD_ID = "recbA1hFdzDrPgtyq"
SNAPSHOT_AS_OF = "2026-09-21"


def p(
    record_id: str,
    asset: str,
    molecule: str,
    indication: str,
    phase: str,
    controlled: str = "",
    code: str = "",
    aliases: List[str] | None = None,
    indication_aliases: List[str] | None = None,
) -> Dict[str, Any]:
    return {
        "recordId": record_id,
        "company": "Merck KGaA",
        "asset": asset or None,
        "molecule": molecule or None,
        "developmentCode": code or None,
        "brand": asset or None,
        "aliases": aliases or [],
        "indication": indication or None,
        "controlledIndication": controlled or None,
        "indicationAliases": indication_aliases or ([controlled] if controlled else []),
        "treatmentSettingLine": [],
        "biomarkerPatientSegment": None,
        "phase": phase or None,
    }


PORTFOLIO_SNAPSHOT: List[Dict[str, Any]] = [
    p(
        "recjNmPDzMHU3Gtsd",
        "pimicotinib",
        "pimicotinib",
        "Adult patients with symptomatic tenosynovial giant cell tumor where surgery may cause functional limitation or severe morbidity; approved in China, regulatory review ongoing in the US and Europe",
        "Filed / Registration",
        "Tenosynovial Giant Cell Tumor",
        "ABSK021",
    ),
    p(
        "recMleVZXCMTv6Jw0",
        "precemtabart tocentecan",
        "precemtabart tocentecan",
        "Previously treated metastatic colorectal cancer after fluoropyrimidine, oxaliplatin, irinotecan and bevacizumab-based therapy; no more than two prior systemic regimens in the metastatic setting",
        "Phase 3",
        "Colorectal Cancer",
        "M9140",
    ),
    p(
        "recgi2czPyhFUo2po",
        "M3554",
        "",
        "Advanced Solid Tumours (Basket)",
        "Phase 1",
        "Advanced Solid Tumours (Basket)",
        "M3554",
    ),
    p(
        "recz3Ch6F0xaxHRL7",
        "M0324",
        "",
        "Advanced Solid Tumours (Basket)",
        "Phase 1",
        "Advanced Solid Tumours (Basket)",
        "M0324",
    ),
    p(
        "recqEHOVIAiYVkQ5d",
        "Mavenclad",
        "cladribine",
        "Multiple sclerosis",
        "Approved",
        "Multiple Sclerosis",
        "",
        ["cladribine", "cladribine capsules"],
    ),
    p(
        "reccSW7qC8XTiTk9V",
        "enpatoran",
        "enpatoran",
        "Lupus with active cutaneous manifestations, including cutaneous lupus erythematosus with or without systemic lupus erythematosus",
        "Phase 3",
        "Systemic Lupus Erythematosus",
        "M5049",
        [],
        ["Systemic Lupus Erythematosus", "Cutaneous Lupus Erythematosus"],
    ),
]


CONTROLLED = {
    "tenosynovial giant cell tumor (tgct)": "Tenosynovial Giant Cell Tumor",
    "colorectal cancer": "Colorectal Cancer",
    "pan tumor (la or metastatic gc, pdac)": "Advanced Solid Tumours (Basket)",
    "advanced solid tumors": "Advanced Solid Tumours (Basket)",
    "generalized myasthenia gravis": "Generalized Myasthenia Gravis",
    "lupus erythematosus with cutaneous manifestations (lupus rash)": "Systemic Lupus Erythematosus",
    "t cell-mediated autoimmune diseases": "Autoimmune Disease",
}


def source_row(row: Dict[str, Any]) -> comparator.DiscoverySourceRow:
    indication = str(row.get("indication") or "").strip()
    return comparator.DiscoverySourceRow(
        company="Merck KGaA",
        sourceFamily="Company Pipeline",
        sourceRecordId=row.get("sourceRecordId"),
        sourceUrl=row.get("sourceUrl"),
        sourceWatchRecordId=SOURCE_WATCH_RECORD_ID,
        asset=row.get("asset") or None,
        molecule=row.get("molecule") or None,
        developmentCode=row.get("developmentCode") or None,
        brand=None,
        indication=indication or None,
        controlledIndicationCandidate=CONTROLLED.get(indication.lower()) or None,
        phase=row.get("phase") or None,
        programStatus=row.get("programStatus") or "Active",
        sponsorOwner="Merck KGaA",
        partners=[],
        ownershipResolved=True,
        strategicPhase1=False,
        importantLabelExpansion=False,
        marketedStrategicRx=False,
        genericCommodity=False,
    )


async def run_canary() -> Dict[str, Any]:
    source = await merck.extract_merck_pipeline(
        company="Merck KGaA",
        source_url=merck.DEFAULT_DATA_URL,
        timeout_seconds=35.0,
    )
    req = comparator.DiscoveryCompareRequest(
        company="Merck KGaA",
        sourceRows=[source_row(row) for row in source.rows],
        portfolioRows=[comparator.PortfolioSnapshotRow(**row) for row in PORTFOLIO_SNAPSHOT],
        companyAliases=["Merck KGaA", "Merck Healthcare KGaA", "EMD Serono"],
        batchRunId=f"MERCK-KGAA-JS-{SNAPSHOT_AS_OF}",
    )
    result = comparator.compare_discovery(req)

    classifications = Counter(c.get("classification") for c in result.candidates)
    decisions = Counter(c.get("commercialInclusionDecision") for c in result.candidates)
    methods = Counter(c.get("matchMethod") for c in result.candidates)
    confidence = Counter(c.get("matchConfidence") for c in result.candidates)

    in_scope = [c for c in result.candidates if c.get("commercialInclusionDecision") == "Include"]
    unresolved = [c for c in in_scope if c.get("classification") not in {"MATCHED", "EXCLUDED BY RULE"}]

    def compact(c: Dict[str, Any]) -> str:
        return "|".join([
            str(c.get("classification") or "?"),
            str(c.get("phase") or "?"),
            str(c.get("asset") or c.get("developmentCode") or "?"),
            str(c.get("indication") or "?"),
            f"existing={len(c.get('existingPortfolioRecordIds') or [])}",
            f"method={c.get('matchMethod') or '?'}",
            f"confidence={c.get('matchConfidence') or '?'}",
        ])

    ready = bool(
        source.readyForDiscovery
        and source.rowCount == 9
        and classifications.get("SOURCE UNAVAILABLE", 0) == 0
        and classifications.get("OWNERSHIP REVIEW", 0) == 0
    )

    return {
        "version": "MERCK_KGAA_RECONCILIATION_CANARY_V1",
        "readyForBindingValidation": ready,
        "sourceReadyForDiscovery": source.readyForDiscovery,
        "sourceRows": source.rowCount,
        "portfolioSnapshotRows": len(PORTFOLIO_SNAPSHOT),
        "classifications": dict(classifications),
        "commercialDecisions": dict(decisions),
        "matchMethods": dict(methods),
        "matchConfidence": dict(confidence),
        "inScopeRows": len(in_scope),
        "unresolvedInScopeCount": len(unresolved),
        "unresolvedInScopeSample": [compact(c) for c in unresolved[:20]],
        "sourceIssues": source.issues,
        "masterWrites": 0,
    }


async def _startup() -> None:
    try:
        print(
            "MERCK_KGAA_RECONCILIATION_CANARY "
            + json.dumps(await run_canary(), ensure_ascii=False),
            flush=True,
        )
    except Exception as exc:
        print(
            "MERCK_KGAA_RECONCILIATION_CANARY "
            + json.dumps({
                "readyForBindingValidation": False,
                "error": f"{type(exc).__name__}: {exc}",
                "masterWrites": 0,
            }),
            flush=True,
        )


@merck.app.on_event("startup")
async def _schedule_merck_reconciliation() -> None:
    asyncio.create_task(_startup())
