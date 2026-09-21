"""Read-only Wave pipeline binding/reconciliation canary.

Validates the source-specific rendered-layout adapter against the current five
named Wave Portfolio assets. Wave's company page supplies broad development
stage only, so this canary intentionally does not compare or write numeric
clinical phase. Exact phase remains a ClinicalTrials.gov / trial-layer fact.

No Airtable or master-data writes.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List

import wave_pipeline_extension as wave


SNAPSHOT_AS_OF = "2026-09-21"
SOURCE_WATCH_RECORD_ID = "recwLacs1eKjbAUIX"

PORTFOLIO_SNAPSHOT: List[Dict[str, Any]] = [
    {
        "recordId": "recQt6LOCukkvd0Vq",
        "developmentCode": "WVE-007",
        "indication": "Obesity",
        "phase": "Phase 2",
    },
    {
        "recordId": "recRmWosPNYCL4qAE",
        "developmentCode": "WVE-006",
        "indication": "Alpha-1 Antitrypsin Deficiency",
        "phase": "Phase 1/2",
    },
    {
        "recordId": "recmGUXKEdWyBJkOt",
        "developmentCode": "WVE-008",
        "indication": "PNPLA3 I148M Liver Disease",
        "phase": "Preclinical",
    },
    {
        "recordId": "recn3RbPzHiytOMAA",
        "developmentCode": "WVE-N531",
        "indication": "Duchenne Muscular Dystrophy",
        "phase": "Phase 1/2",
    },
    {
        "recordId": "recBoB2UJXxBNsgQX",
        "developmentCode": "WVE-003",
        "indication": "Huntington's Disease",
        "phase": "Phase 1/2",
    },
]


async def run_canary() -> Dict[str, Any]:
    source = await wave.extract_wave_pipeline()

    source_by_code = {
        str(row.get("developmentCode") or "").upper(): row
        for row in source.rows
        if row.get("developmentCode")
    }
    portfolio_by_code = {
        str(row.get("developmentCode") or "").upper(): row
        for row in PORTFOLIO_SNAPSHOT
    }

    source_codes = set(source_by_code)
    portfolio_codes = set(portfolio_by_code)
    matched = sorted(source_codes & portfolio_codes)
    source_only = sorted(source_codes - portfolio_codes)
    portfolio_only = sorted(portfolio_codes - source_codes)

    stage_counts: Dict[str, int] = {}
    mappings = []
    for code in matched:
        s = source_by_code[code]
        p = portfolio_by_code[code]
        stage = str(s.get("sourceStage") or "")
        stage_counts[stage] = stage_counts.get(stage, 0) + 1
        mappings.append({
            "developmentCode": code,
            "sourceIndication": s.get("indication"),
            "sourceStage": stage,
            "portfolioRecordId": p.get("recordId"),
            "portfolioIndication": p.get("indication"),
            "portfolioExactPhase": p.get("phase"),
            "phaseWriteSuppressed": True,
        })

    ready = bool(
        source.readyForDiscovery
        and len(source.rows) == 5
        and not source_only
        and not portfolio_only
        and len(matched) == 5
        and all(source_by_code[c].get("sourceStage") for c in matched)
    )

    return {
        "version": "WAVE_RECONCILIATION_CANARY_V1",
        "readyForBindingValidation": ready,
        "sourceReadyForDiscovery": source.readyForDiscovery,
        "sourceRows": source.rowCount,
        "portfolioSnapshotRows": len(PORTFOLIO_SNAPSHOT),
        "matchedExactDevelopmentCodes": matched,
        "matchedCount": len(matched),
        "sourceOnlyCodes": source_only,
        "portfolioOnlyCodes": portfolio_only,
        "sourceStageCounts": stage_counts,
        "mappings": mappings,
        "phasePolicy": "COMPANY_PAGE_BROAD_STAGE_ONLY; EXACT_PHASE_REMAINS_TRIAL_LAYER",
        "numericPhaseWrites": 0,
        "sourceIssues": source.issues,
        "masterWrites": 0,
    }


async def _startup() -> None:
    try:
        result = await run_canary()
        print("WAVE_RECONCILIATION_CANARY " + json.dumps(result, ensure_ascii=False), flush=True)
    except Exception as exc:
        print(
            "WAVE_RECONCILIATION_CANARY "
            + json.dumps({
                "readyForBindingValidation": False,
                "error": f"{type(exc).__name__}: {exc}",
                "masterWrites": 0,
            }),
            flush=True,
        )


@wave.app.on_event("startup")
async def _schedule_wave_reconciliation_canary() -> None:
    asyncio.create_task(_startup())
