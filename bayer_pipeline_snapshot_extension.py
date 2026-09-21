"""Read-only Bayer Pharmaceuticals development-pipeline snapshot adapter.

The official Bayer Development Pipeline page is publicly readable but is
currently blocked from the Render/browser retrieval runtime (direct fallback
ends in HTTP 403). This adapter preserves the complete 29-row first-party
pipeline table captured from the official page on 2026-09-21. Bayer marks the
page "Last Updated: August 04, 2026".

Snapshot/baseline use only; recurring current-state monitoring must continue
through Bayer news/IR, ClinicalTrials.gov and regulatory sources until the live
page is reliably machine-readable from production.

No Airtable or master-data writes.
"""
from __future__ import annotations

import hashlib
from typing import Any, Dict, List

from fastapi import Header
from pydantic import BaseModel

from main import _auth, app

ADAPTER_PROFILE = "PIPELINE_BAYER_STATIC_SNAPSHOT_V1"
ROUTE_VERSION = "BAYER_PIPELINE_SNAPSHOT_V1.0_READ_ONLY"
SOURCE_URL = "https://www.bayer.com/en/pharma/development-pipeline"
SOURCE_CAPTURED_AT = "2026-09-21T22:58:09Z"
SOURCE_AS_OF = "2026-08-04"
SOURCE_PROVENANCE = "FIRST_PARTY_BAYER_DEVELOPMENT_PIPELINE_PAGE_CAPTURED_2026-09-21"


def _row(
    phase: str,
    ta: str,
    asset: str,
    indication: str,
    *,
    development_code: str = "",
    molecule: str = "",
    aliases: List[str] | None = None,
    notes: str = "",
) -> Dict[str, Any]:
    aliases = aliases or []
    key = "|".join([phase, ta, asset, indication]).lower()
    rid = "BAYERSNAP-" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:16].upper()
    return {
        "company": "Bayer",
        "sourceFamily": "Bayer Official Development Pipeline Snapshot",
        "sourceRecordId": rid,
        "sourceUrl": SOURCE_URL,
        "sourceCapturedAt": SOURCE_CAPTURED_AT,
        "sourceAsOf": SOURCE_AS_OF,
        "asset": asset,
        "molecule": molecule,
        "developmentCode": development_code,
        "brand": "",
        "aliases": aliases,
        "indication": indication,
        "phase": phase,
        "programStatus": "Active",
        "sponsorOwner": "Bayer",
        "partners": [],
        "therapeuticArea": ta,
        "notes": notes,
        "sourceAdapter": ADAPTER_PROFILE,
    }


ROWS: List[Dict[str, Any]] = [
    _row("Phase 3","Oncology","Darolutamide","Adjuvant Prostate Cancer",molecule="darolutamide"),
    _row("Phase 3","Oncology","Darolutamide","Prostate Cancer with Biochemical Recurrence after Curative Radiotherapy",molecule="darolutamide"),
    _row("Phase 3","Cardiovascular / Renal","Finerenone","Non-diabetic CKD (FIND-CKD)",molecule="finerenone"),
    _row("Phase 3","Neurology & Rare Diseases","Bemdaneprocel","Parkinson's Disease (exPDite-2)",molecule="bemdaneprocel"),
    _row("Phase 3","Others","124I-Evuzamitide","Diagnosis of Cardiac Amyloidosis (REVEAL)",molecule="124I-Evuzamitide"),
    _row("Phase 2","Oncology","Sevabertinib","Metastatic or Unresectable Solid Tumors with HER2-activating Mutations (PanSOHO)",molecule="sevabertinib"),
    _row("Phase 2","Cardiovascular / Renal","Umiposgene Parvec","Congestive Heart Failure (GenePHIT)",molecule="umiposgene parvec"),
    _row("Phase 2","Cardiovascular / Renal","Inclocibart","Acute Ischemic Stroke; Pulmonary Embolism (SIRIUS)",molecule="inclocibart"),
    _row("Phase 2","Cardiovascular / Renal","Nurandociguat","Chronic Kidney Disease (ALPINE-1)",molecule="nurandociguat"),
    _row("Phase 2","Cardiovascular / Renal","SEMA 3a","Alport Syndrome (ASSESS)",aliases=["SEMA 3a Inhibitor"]),
    _row("Phase 2","Neurology & Rare Diseases","Ametefgene Parvec","Parkinson's Disease (REGENERATE-PD)",molecule="ametefgene parvec"),
    _row("Phase 2","Others","Edonentan","Non-proliferative Diabetic Retinopathy",development_code="BAY 3826827",molecule="edonentan",aliases=["PER-001"]),
    _row("Phase 2","Others","Edonentan","Glaucoma",development_code="BAY 3826827",molecule="edonentan",aliases=["PER-001"]),
    _row("Phase 1","Oncology","VVD Keap1 Act","Advanced Solid Tumors"),
    _row("Phase 1","Oncology","Actinium (225Ac) Felivotide Mopaxetan","Advanced Prostate Cancer"),
    _row("Phase 1","Oncology","SOS1 Inhibitor","Advanced Solid Cancers"),
    _row("Phase 1","Oncology","PRMT5 Inhibitor","MTAP-deleted Solid Tumors"),
    _row("Phase 1","Oncology","VVD RAS-PI3K Inhibitor","Advanced Solid Tumors"),
    _row("Phase 1","Oncology","225Ac-GPC3","Advanced Liver Cancer"),
    _row("Phase 1","Oncology","VVD WRN Inhibitor","Advanced Solid Tumors"),
    _row("Phase 1","Oncology","KRAS G12D Inhibitor","Advanced Solid Tumors"),
    _row("Phase 1","Cardiovascular / Renal","Dual FIIa/Xa Inhibitor","Anti-coagulation"),
    _row("Phase 1","Cardiovascular / Renal","GIRK4 Inhibitor","Atrial fibrillation"),
    _row("Phase 1","Cardiovascular / Renal","BAY 3620122","Vasoplegia",development_code="BAY 3620122"),
    _row("Phase 1","Neurology & Rare Diseases","Ametefgene Parvec","Multiple System Atrophy",molecule="ametefgene parvec"),
    _row("Phase 1","Neurology & Rare Diseases","Pompe Disease AAV Gene Therapy","Pompe Disease"),
    _row("Phase 1","Neurology & Rare Diseases","LGMD2I/R9 AAV Gene Therapy","Limb Girdle Muscular Dystrophy"),
    _row("Phase 1","Others","Primary Photoreceptor Diseases Cell Therapy","Primary Photoreceptor Disease"),
    _row("Phase 1","Others","AT-05 SPECT Tracer","Diagnosis of Cardiac Amyloidosis"),
]


class BayerSnapshotResponse(BaseModel):
    version: str
    routeVersion: str
    company: str
    sourceUrl: str
    sourceCapturedAt: str
    sourceAsOf: str
    sourceProvenance: str
    retrievalMode: str
    readOnly: bool
    readyForDiscovery: bool
    rowCount: int
    rows: List[Dict[str, Any]]
    summary: Dict[str, Any]
    issues: List[Dict[str, Any]]
    guardrails: Dict[str, Any]


def snapshot_response() -> BayerSnapshotResponse:
    phase_counts: Dict[str, int] = {}
    ta_counts: Dict[str, int] = {}
    for row in ROWS:
        phase_counts[row["phase"]] = phase_counts.get(row["phase"], 0) + 1
        ta_counts[row["therapeuticArea"]] = ta_counts.get(row["therapeuticArea"], 0) + 1

    sentinels = {
        "Darolutamide": any(r["asset"] == "Darolutamide" for r in ROWS),
        "Finerenone": any(r["asset"] == "Finerenone" for r in ROWS),
        "Bemdaneprocel": any(r["asset"] == "Bemdaneprocel" for r in ROWS),
        "Sevabertinib": any(r["asset"] == "Sevabertinib" for r in ROWS),
        "Edonentan": any(r["asset"] == "Edonentan" for r in ROWS),
        "BAY 3620122": any(r["asset"] == "BAY 3620122" for r in ROWS),
    }
    issues: List[Dict[str, Any]] = []
    if len(ROWS) != 29:
        issues.append({"issue": f"snapshot row count changed: {len(ROWS)} != 29"})
    if phase_counts != {"Phase 3": 5, "Phase 2": 8, "Phase 1": 16}:
        issues.append({"issue": f"unexpected phase counts: {phase_counts}"})
    if not all(sentinels.values()):
        issues.append({"issue": "one or more required sentinel assets missing"})

    return BayerSnapshotResponse(
        version=ADAPTER_PROFILE,
        routeVersion=ROUTE_VERSION,
        company="Bayer",
        sourceUrl=SOURCE_URL,
        sourceCapturedAt=SOURCE_CAPTURED_AT,
        sourceAsOf=SOURCE_AS_OF,
        sourceProvenance=SOURCE_PROVENANCE,
        retrievalMode="STATIC_SNAPSHOT",
        readOnly=True,
        readyForDiscovery=not issues,
        rowCount=len(ROWS),
        rows=ROWS,
        summary={
            "structuralValidationPass": not issues,
            "actual": {"Total": len(ROWS)},
            "phaseCounts": phase_counts,
            "therapeuticAreaCounts": ta_counts,
            "sentinels": sentinels,
            "sourceDeclaredClinicalProjects": 29,
            "productionStatus": "READY FOR DATED SNAPSHOT/BACKFILL COMPARISON" if not issues else "FAIL CLOSED",
            "liveSourceAvailableToRender": False,
            "snapshotOnly": True,
            "writeMode": "READ_ONLY",
        },
        issues=issues,
        guardrails={
            "airtableWrites": False,
            "portfolioWrites": False,
            "masterDataWrites": False,
            "snapshotOnly": True,
            "firstPartySource": True,
            "liveSourceSubstitution": False,
            "portfolioDependentValidation": False,
        },
    )


@app.get("/extract/bayer/pipeline-snapshot/health")
async def bayer_snapshot_health() -> Dict[str, Any]:
    return {
        "ok": True,
        "version": ADAPTER_PROFILE,
        "routeVersion": ROUTE_VERSION,
        "readOnly": True,
        "snapshotOnly": True,
    }


@app.get("/extract/bayer/pipeline-snapshot", response_model=BayerSnapshotResponse)
async def bayer_snapshot_route(
    x_adapter_key: str | None = Header(default=None),
) -> BayerSnapshotResponse:
    _auth(x_adapter_key)
    return snapshot_response()
