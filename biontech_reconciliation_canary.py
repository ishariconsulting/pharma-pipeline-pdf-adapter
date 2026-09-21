"""Read-only BioNTech official pipeline -> current Portfolio reconciliation canary.

Validates the first-party BioNTech AEM GraphQL adapter against the current
BioNTech Portfolio snapshot. No Airtable or master-data writes.
"""
from __future__ import annotations

import asyncio
from collections import Counter
from typing import Any, Dict, List

import biontech_graphql_pipeline_extension as bio
import portfolio_discovery_extension_v11 as comparator
import portfolio_discovery_extension_v12  # noqa: F401 - applies verified alias patches


SNAPSHOT_AS_OF = "2026-09-21"
SOURCE_WATCH_RECORD_ID = "recvRfl2remCgdDxW"


def p(
    record_id: str,
    asset: str = "",
    molecule: str = "",
    code: str = "",
    indication: str = "",
    phase: str = "",
    aliases: List[str] | None = None,
) -> Dict[str, Any]:
    return {
        "recordId": record_id,
        "company": "BioNTech SE",
        "asset": asset or None,
        "molecule": molecule or None,
        "developmentCode": code or None,
        "brand": asset or None,
        "aliases": aliases or [],
        "indication": indication or None,
        "controlledIndication": None,
        "indicationAliases": [],
        "phase": phase or None,
    }


PORTFOLIO_SNAPSHOT: List[Dict[str, Any]] = [
    p("rec5cPHnDsqBTclzH", "BNT325", "", "BNT325", "Advanced / metastatic solid tumors", "Phase 1/2", ["DB-1305"]),
    p("rec8AEKcmroGGCenx", "elfetabart drozuntecan", "elfetabart drozuntecan", "BNT324", "Metastatic Castration-resistant Prostate Cancer", "Phase 3", ["BNT324", "DB-1311", "elfe-D"]),
    p("rec9cXA7CImqVT1ZM", "elfetabart drozuntecan + pumitamig", "elfetabart drozuntecan + pumitamig", "BNT324 + BNT327", "Advanced / metastatic small-cell lung cancer", "Phase 1/2", ["BNT324", "DB-1311", "elfe-D", "BNT327", "PM8002", "BMS-986545"]),
    p("recD7bYqdkJKpCw1Q", "BNT326", "", "BNT326", "Advanced / metastatic non-small cell lung cancer", "Phase 2", ["YL202"]),
    p("recDD3vBdc7inmtPn", "pumitamig", "pumitamig", "BNT327", "First-line MSS / pMMR metastatic colorectal cancer", "Phase 2", ["BNT327", "PM8002", "BMS-986545"]),
    p("recDcc3XxPEgiUCPU", "elfetabart drozuntecan", "elfetabart drozuntecan", "BNT324", "Advanced / metastatic solid tumors", "Phase 2", ["DB-1311", "BNT324", "elfe-D"]),
    p("recEdivTk3dhdgwDC", "BNT326", "", "BNT326", "Advanced solid tumors", "Phase 1/2", ["YL202"]),
    p("recGLavnD3q8KOq6W", "pumitamig", "pumitamig", "BNT327", "First-line advanced non-small cell lung cancer", "Phase 3", ["BNT327", "PM8002", "BMS-986545"]),
    p("recLEL6kXMnMJDaIQ", "RO7198457 intravenous (IV)", "", "RO7198457", "Colorectal Cancer Stage II", "Phase 2", ["BNT122", "autogene cevumeran"]),
    p("recNLdsZCzeAvi3YV", "BNT116", "", "BNT116", "Non-Small Cell Lung Cancer", "Phase 2"),
    p("recQQXws8Xd7aQmi7", "BNT168", "", "BNT168", "HIV -1 Infection", "Phase 1"),
    p("recQcmALlGxzxOu3A", "pumitamig", "pumitamig", "BNT327", "First-line metastatic pancreatic ductal adenocarcinoma", "Phase 2", ["BNT327", "PM8002", "BMS-986545"]),
    p("recQh2leDjLsKWZqX", "BNT3212", "", "BNT3212", "Advanced solid tumors", "Phase 1/2", ["PM1300"]),
    p("recRn42vL4rPpHGf8", "BNT314", "", "BNT314", "Metastatic colorectal cancer", "Phase 1/2"),
    p("recTShbadiRptEIOA", "BNT211", "", "BNT211", "Advanced Solid Tumours (Basket)", "Phase 1/2"),
    p("recWblv2aGWyD724A", "BNT113", "", "BNT113", "Head and Neck Squamous Cell Carcinoma", "Phase 3"),
    p("recYPqbkabNVto4Dq", "gotistobart", "", "BNT316", "Non-Small Cell Lung Cancer / Prostate Cancer / Ovarian Cancer / Advanced Solid Tumours (Basket)", "Phase 3", ["ONC-392"]),
    p("recaOt9ueohtl3dzY", "BNT351", "", "BNT351", "HIV -1 Infection", "Phase 1"),
    p("recaZVBZSwYm1Hjfi", "trastuzumab pamirtecan", "trastuzumab pamirtecan", "BNT323", "Advanced / metastatic breast cancer", "Phase 3", ["BNT323", "DB-1303"]),
    p("reccc4JYJqhetXw0K", "trastuzumab pamirtecan + pumitamig", "trastuzumab pamirtecan + pumitamig", "BNT323 + BNT327", "Advanced breast cancer", "Phase 1/2", ["BNT323", "DB-1303", "BNT327", "PM8002"]),
    p("recdqe7hsznm75JGI", "BNT326 + pumitamig", "BNT326 + pumitamig", "BNT326 + BNT327", "Advanced / metastatic non-small cell lung cancer", "Phase 1/2", ["YL202", "BNT327", "PM8002"]),
    p("recnRgToj8myvPUuN", "pumitamig", "pumitamig", "BNT327", "First-line triple-negative breast cancer", "Phase 3", ["BNT327", "PM8002", "BMS-986545"]),
    p("recoR514ESAJun3UC", "pumitamig", "pumitamig", "BNT327", "First-line extensive-stage small-cell lung cancer", "Phase 3", ["BNT327", "PM8002", "BMS-986545"]),
    p("rectSJmgWfrK5ArE2", "BNT3213", "", "BNT3213", "Hepatocellular Carcinoma", "Phase 2"),
    p("recusntAioAD4dFLu", "elfetabart drozuntecan + pumitamig", "elfetabart drozuntecan + pumitamig", "BNT324 + BNT327", "Advanced / metastatic non-small cell lung cancer", "Phase 1/2", ["BNT324", "DB-1311", "BNT327", "PM8002"]),
    p("reczClqyKh0vCPqcB", "pumitamig", "pumitamig", "BNT327", "Recurrent glioblastoma", "Phase 2", ["BNT327", "PM8002", "BMS-986545"]),
]


def _to_source_row(row: Dict[str, Any]) -> comparator.DiscoverySourceRow:
    phase = row.get("phase") or ""
    return comparator.DiscoverySourceRow(
        company="BioNTech SE",
        sourceFamily=row.get("sourceFamily") or "Company Pipeline",
        sourceRecordId=row.get("sourceRecordId"),
        sourceUrl=row.get("sourceUrl"),
        sourceWatchRecordId=SOURCE_WATCH_RECORD_ID,
        asset=row.get("asset"),
        molecule=row.get("molecule"),
        developmentCode=row.get("developmentCode"),
        brand=row.get("brand"),
        indication=row.get("indication"),
        phase=phase,
        programStatus=row.get("programStatus") or "Active",
        sponsorOwner="BioNTech SE",
        partners=row.get("partners") or [],
        ownershipResolved=True,
        strategicPhase1=False,
        importantLabelExpansion=False,
        marketedStrategicRx=(phase == "Approved"),
        genericCommodity=False,
    )


async def run_canary() -> Dict[str, Any]:
    source = await bio.extract_biontech_pipeline()
    request = comparator.DiscoveryCompareRequest(
        company="BioNTech SE",
        sourceRows=[_to_source_row(row) for row in source.rows],
        portfolioRows=[comparator.PortfolioSnapshotRow(**row) for row in PORTFOLIO_SNAPSHOT],
        companyAliases=["BioNTech", "BioNTech SE"],
        batchRunId=f"BIONTECH-CANARY-{SNAPSHOT_AS_OF}",
    )
    result = comparator.compare_discovery(request)

    classifications = Counter(c.get("classification") for c in result.candidates)
    decisions = Counter(c.get("commercialInclusionDecision") for c in result.candidates)
    methods = Counter(c.get("matchMethod") for c in result.candidates)
    confidence = Counter(c.get("matchConfidence") for c in result.candidates)
    field_deltas = Counter()
    for candidate in result.candidates:
        for delta in candidate.get("fieldDeltas") or []:
            field_deltas[delta.get("field") or "?"] += 1

    in_scope = [
        c for c in result.candidates
        if c.get("commercialInclusionDecision") == "Include"
    ]
    unresolved_in_scope = [
        c for c in in_scope
        if c.get("classification") not in {"MATCHED", "EXCLUDED BY RULE"}
    ]

    ready = bool(
        source.readyForDiscovery
        and source.rowCount >= bio.MIN_ROWS
        and classifications.get("SOURCE UNAVAILABLE", 0) == 0
        and classifications.get("OWNERSHIP REVIEW", 0) == 0
    )

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

    return {
        "version": "BIONTECH_RECONCILIATION_CANARY_V1",
        "readyForBindingValidation": ready,
        "sourceReadyForDiscovery": source.readyForDiscovery,
        "sourceRows": source.rowCount,
        "portfolioSnapshotRows": len(PORTFOLIO_SNAPSHOT),
        "classifications": dict(classifications),
        "commercialDecisions": dict(decisions),
        "matchMethods": dict(methods),
        "matchConfidence": dict(confidence),
        "fieldDeltaCounts": dict(field_deltas),
        "inScopeRows": len(in_scope),
        "unresolvedInScopeCount": len(unresolved_in_scope),
        "unresolvedInScopeSample": [compact(c) for c in unresolved_in_scope[:30]],
        "sourceIssues": source.issues,
        "masterWrites": 0,
    }


async def _startup() -> None:
    try:
        result = await run_canary()
        print(f"BIONTECH_RECONCILIATION_CANARY {result}", flush=True)
    except Exception as exc:
        print(
            f"BIONTECH_RECONCILIATION_CANARY readyForBindingValidation=False "
            f"error={type(exc).__name__}:{exc} masterWrites=0",
            flush=True,
        )


@bio.app.on_event("startup")
async def _schedule_biontech_reconciliation_canary() -> None:
    asyncio.create_task(_startup())
