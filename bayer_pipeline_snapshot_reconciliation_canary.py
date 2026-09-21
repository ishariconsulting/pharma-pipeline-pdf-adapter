"""Read-only Bayer official pipeline snapshot -> current Portfolio reconciliation.

The official Bayer Development Pipeline page states 29 projects and was last
updated 2026-08-04. This canary compares the captured first-party 29-row table
against the relevant current Airtable Portfolio snapshot. No master writes.
"""
from __future__ import annotations

import asyncio
import json
from collections import Counter
from typing import Any, Dict, List

import bayer_pipeline_snapshot_extension as bayer
import portfolio_discovery_extension_v11 as comparator
import portfolio_discovery_extension_v12  # noqa: F401 - patches comparator

SOURCE_WATCH_RECORD_ID = "recpYNnKjnaIg0UkV"
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
        "company": "Bayer",
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
        "rec80EGKma7BoiQMm","darolutamide","darolutamide",
        "High-risk localized prostate cancer after definitive local therapy","Phase 3",
        "Prostate Cancer","",[],
        ["Prostate Cancer","Adjuvant Prostate Cancer"],
    ),
    p(
        "recda4Ow2zDWzrADG","darolutamide / Nubeqa lifecycle","darolutamide",
        "High-risk biochemical recurrence of prostate cancer after local therapy","Phase 3",
        "Prostate Cancer","",["darolutamide"],
        ["Prostate Cancer","Prostate Cancer with Biochemical Recurrence after Curative Radiotherapy"],
    ),
    p(
        "recY6hGU05wUaUDUY","Kerendia","finerenone",
        "Non-diabetic chronic kidney disease","Phase 3","Chronic Kidney Disease","",[],
        ["Chronic Kidney Disease","Non-diabetic CKD (FIND-CKD)"],
    ),
    p(
        "rec89ygYEgFlow9OK","bemdaneprocel","bemdaneprocel",
        "Parkinson's disease","Phase 3","Parkinson's Disease","",[],
        ["Parkinson's Disease","Parkinson's Disease (exPDite-2)"],
    ),
    p(
        "rec4bW4H8brt3SzMc","124I-Evuzamitide","",
        "Cardiac Amyloidosis","Phase 3","Cardiac Amyloidosis","",
        ["I-124 evuzamitide"],["Cardiac Amyloidosis","Diagnosis of Cardiac Amyloidosis (REVEAL)"],
    ),
    p(
        "recCkJH61LhTqRYjw","I-124 evuzamitide","I-124 evuzamitide",
        "Diagnosis of cardiac amyloidosis","Phase 3","Cardiac Amyloidosis","",
        ["124I-Evuzamitide"],["Cardiac Amyloidosis","Diagnosis of Cardiac Amyloidosis (REVEAL)"],
    ),
    p(
        "recxkws9VdheWYC4K","sevabertinib","sevabertinib",
        "HER2-altered advanced solid tumors","Phase 2","Advanced Solid Tumours (Basket)","",[],
        ["Advanced Solid Tumours (Basket)","Metastatic or Unresectable Solid Tumors with HER2-activating Mutations (PanSOHO)"],
    ),
    p(
        "recmYUHF4PxkZdNvU","AB-1002","umiposgene parvec / AB-1002",
        "Non-ischemic congestive heart failure","Phase 2","Heart Failure","AB-1002",
        ["umiposgene parvec"],["Heart Failure","Congestive Heart Failure (GenePHIT)"],
    ),
    p(
        "recf4TJrDeRhmpW5A","inclocibart","BAY 3018250",
        "Symptomatic proximal deep vein thrombosis","Phase 2","Venous Thromboembolism","BAY 3018250",
        ["inclocibart"],["Venous Thromboembolism"],
    ),
    p(
        "recnX9HZsdhgqfFJD","Nurandociguat","",
        "Chronic Kidney Disease","Phase 2","Chronic Kidney Disease","BAY 3283142",
        ["nurandociguat"],["Chronic Kidney Disease","Chronic Kidney Disease (ALPINE-1)"],
    ),
    p(
        "recC2oMiExKMLgOqm","BAY 3401016","BAY 3401016",
        "Alport syndrome","Phase 2","Alport Syndrome","BAY 3401016",
        ["SEMA 3a","SEMA 3a Inhibitor"],["Alport Syndrome","Alport Syndrome (ASSESS)"],
    ),
    p(
        "recG7j8TgE3gRdgr7","ametefgene parvec / AB-1005","ametefgene parvec",
        "Parkinson's disease","Phase 2","Parkinson's Disease","AB-1005",
        ["Ametefgene Parvec"],["Parkinson's Disease","Parkinson's Disease (REGENERATE-PD)"],
    ),
    p(
        "recg6rJf1GK61sxbP","edonentan / PER-001","edonentan",
        "Non-proliferative diabetic retinopathy","Phase 2","Diabetic Retinopathy","",
        ["Edonentan","PER-001","BAY 3826827"],["Diabetic Retinopathy","Non-proliferative Diabetic Retinopathy"],
    ),
    p(
        "recWaQvGFhy4bRWmB","edonentan / PER-001","edonentan",
        "Glaucoma","Phase 2","Glaucoma","",
        ["Edonentan","PER-001","BAY 3826827"],["Glaucoma"],
    ),
]


CONTROLLED = {
    "adjuvant prostate cancer": "Prostate Cancer",
    "prostate cancer with biochemical recurrence after curative radiotherapy": "Prostate Cancer",
    "non-diabetic ckd (find-ckd)": "Chronic Kidney Disease",
    "parkinson's disease (expdite-2)": "Parkinson's Disease",
    "diagnosis of cardiac amyloidosis (reveal)": "Cardiac Amyloidosis",
    "metastatic or unresectable solid tumors with her2-activating mutations (pansoho)": "Advanced Solid Tumours (Basket)",
    "congestive heart failure (genephit)": "Heart Failure",
    "chronic kidney disease (alpine-1)": "Chronic Kidney Disease",
    "alport syndrome (assess)": "Alport Syndrome",
    "parkinson's disease (regenerate-pd)": "Parkinson's Disease",
    "non-proliferative diabetic retinopathy": "Diabetic Retinopathy",
    "glaucoma": "Glaucoma",
    "advanced solid tumors": "Advanced Solid Tumours (Basket)",
    "advanced solid cancers": "Advanced Solid Tumours (Basket)",
    "advanced prostate cancer": "Prostate Cancer",
    "atrial fibrillation": "Atrial Fibrillation",
    "multiple system atrophy": "Multiple System Atrophy",
    "pompe disease": "Pompe Disease",
    "limb girdle muscular dystrophy": "Limb Girdle Muscular Dystrophy",
    "primary photoreceptor disease": "Inherited Retinal Disease",
    "diagnosis of cardiac amyloidosis": "Cardiac Amyloidosis",
}


def source_row(row: Dict[str, Any]) -> comparator.DiscoverySourceRow:
    indication = str(row.get("indication") or "").strip()
    phase = str(row.get("phase") or "")
    return comparator.DiscoverySourceRow(
        company="Bayer",
        sourceFamily="Bayer Official Development Pipeline Snapshot",
        sourceRecordId=row.get("sourceRecordId"),
        sourceUrl=bayer.SOURCE_URL,
        sourceWatchRecordId=SOURCE_WATCH_RECORD_ID,
        asset=row.get("asset") or None,
        molecule=row.get("molecule") or None,
        developmentCode=row.get("developmentCode") or None,
        brand=None,
        indication=indication or None,
        controlledIndicationCandidate=CONTROLLED.get(indication.lower()) or None,
        phase=phase or None,
        programStatus="Active",
        sponsorOwner="Bayer",
        partners=[],
        ownershipResolved=True,
        strategicPhase1=False,
        importantLabelExpansion=False,
        marketedStrategicRx=False,
        genericCommodity=False,
    )


async def run_canary() -> Dict[str, Any]:
    snap = bayer.snapshot_response()
    req = comparator.DiscoveryCompareRequest(
        company="Bayer",
        sourceRows=[source_row(row) for row in snap.rows],
        portfolioRows=[comparator.PortfolioSnapshotRow(**row) for row in PORTFOLIO_SNAPSHOT],
        companyAliases=["Bayer", "Bayer AG", "Bayer Pharmaceuticals"],
        batchRunId="BAYER-SNAPSHOT-2026-09-21",
    )
    result = comparator.compare_discovery(req)

    classifications = Counter(c.get("classification") for c in result.candidates)
    decisions = Counter(c.get("commercialInclusionDecision") for c in result.candidates)
    methods = Counter(c.get("matchMethod") for c in result.candidates)
    confidence = Counter(c.get("matchConfidence") for c in result.candidates)

    in_scope = [c for c in result.candidates if c.get("commercialInclusionDecision") == "Include"]
    unresolved = [c for c in in_scope if c.get("classification") not in {"MATCHED", "EXCLUDED BY RULE"}]
    review_candidates = [
        {
            "classification": c.get("classification"),
            "asset": c.get("asset"),
            "indication": c.get("indication"),
            "phase": c.get("phase"),
            "existingPortfolioRecordIds": c.get("existingPortfolioRecordIds") or [],
            "matchMethod": c.get("matchMethod"),
            "matchConfidence": c.get("matchConfidence"),
            "reviewReason": c.get("reviewReason"),
        }
        for c in result.candidates
        if c.get("classification") == "POSSIBLE DUPLICATE"
    ]
    phase_deltas = []
    for c in result.candidates:
        for d in c.get("fieldDeltas") or []:
            if d.get("field") == "Development Phase":
                phase_deltas.append({
                    "asset": c.get("asset"),
                    "indication": c.get("indication"),
                    "source": d.get("sourceValue"),
                    "portfolio": d.get("portfolioValue"),
                })

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
        snap.readyForDiscovery
        and snap.rowCount == 29
        and classifications.get("SOURCE UNAVAILABLE", 0) == 0
        and classifications.get("OWNERSHIP REVIEW", 0) == 0
    )
    return {
        "version": "BAYER_PIPELINE_SNAPSHOT_RECONCILIATION_CANARY_V1",
        "readyForSnapshotBindingValidation": ready,
        "sourceAsOf": bayer.SOURCE_AS_OF,
        "sourceRows": snap.rowCount,
        "portfolioSnapshotRows": len(PORTFOLIO_SNAPSHOT),
        "classifications": dict(classifications),
        "commercialDecisions": dict(decisions),
        "matchMethods": dict(methods),
        "matchConfidence": dict(confidence),
        "inScopeRows": len(in_scope),
        "unresolvedInScopeCount": len(unresolved),
        "unresolvedInScopeSample": [compact(c) for c in unresolved[:20]],
        "possibleDuplicateCount": len(review_candidates),
        "possibleDuplicateSample": review_candidates[:10],
        "phaseDeltaCount": len(phase_deltas),
        "phaseDeltaSample": phase_deltas[:20],
        "sourceIssues": snap.issues,
        "liveRenderRetrievalAvailable": False,
        "masterWrites": 0,
    }


async def _startup() -> None:
    try:
        print(
            "BAYER_PIPELINE_SNAPSHOT_RECONCILIATION_CANARY "
            + json.dumps(await run_canary(), ensure_ascii=False),
            flush=True,
        )
    except Exception as exc:
        print(
            "BAYER_PIPELINE_SNAPSHOT_RECONCILIATION_CANARY "
            + json.dumps({
                "readyForSnapshotBindingValidation": False,
                "error": f"{type(exc).__name__}: {exc}",
                "masterWrites": 0,
            }),
            flush=True,
        )


@bayer.app.on_event("startup")
async def _schedule_bayer_snapshot_reconciliation() -> None:
    asyncio.create_task(_startup())
