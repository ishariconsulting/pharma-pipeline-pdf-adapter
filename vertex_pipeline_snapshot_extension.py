"""Read-only Vertex current-pipeline snapshot adapter.

Vertex's live R&D pipeline page is publicly readable, but the Render service and
browser worker are currently blocked/timed out by the source's edge controls.
This module therefore preserves a dated first-party snapshot captured from the
official Vertex R&D pipeline page on 2026-09-21.

It is a baseline/backfill source only. Ongoing change detection must continue
through Vertex Newsroom/IR, ClinicalTrials.gov and regulatory sources until a
stable machine-readable live route is available.

No Airtable/master-data writes.
"""
from __future__ import annotations

import hashlib
from typing import Any, Dict, List

from fastapi import Header
from pydantic import BaseModel

from main import _auth, app

ADAPTER_PROFILE = "PIPELINE_VERTEX_STATIC_SNAPSHOT_V1"
ROUTE_VERSION = "VERTEX_PIPELINE_SNAPSHOT_V1.0_READ_ONLY"
SOURCE_URL = "https://www.vrtx.com/our-science/pipeline/"
SOURCE_CAPTURED_AT = "2026-09-21T22:35:00Z"
SOURCE_AS_OF = "2026-09-21"
SOURCE_PROVENANCE = "FIRST_PARTY_VERTEX_PIPELINE_PAGE_CAPTURED_2026-09-21"


def _row(
    ta: str,
    indication: str,
    asset: str,
    phase_label: str,
    *,
    molecule: str = "",
    development_code: str = "",
    aliases: List[str] | None = None,
    notes: str = "",
) -> Dict[str, Any]:
    aliases = aliases or []
    key = "|".join([ta, indication, asset, phase_label]).lower()
    rid = "VRTXSNAP-" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:16].upper()
    return {
        "company": "Vertex Pharmaceuticals",
        "sourceFamily": "Vertex Official R&D Pipeline Snapshot",
        "sourceRecordId": rid,
        "sourceUrl": SOURCE_URL,
        "sourceCapturedAt": SOURCE_CAPTURED_AT,
        "asset": asset,
        "molecule": molecule,
        "developmentCode": development_code,
        "brand": "",
        "aliases": aliases,
        "indication": indication,
        "phase": phase_label,
        "sourcePhaseLabel": phase_label,
        "programStatus": "Research" if phase_label == "Research" else "Active",
        "sponsorOwner": "Vertex Pharmaceuticals",
        "partners": [],
        "therapeuticArea": ta,
        "notes": notes,
        "sourceAdapter": ADAPTER_PROFILE,
    }


ROWS: List[Dict[str, Any]] = [
    _row("Renal","APOL1-mediated kidney disease (AMKD)","Inaxaplin","Phase 3",molecule="inaxaplin"),
    _row("Renal","APOL1-mediated kidney disease (AMKD)","Additional Small Molecules","Research"),
    _row("Renal","Autosomal dominant polycystic kidney disease (ADPKD)","VX-407","Phase 2",development_code="VX-407"),
    _row("Hematology","Beta thalassemia","Exa-cel","Phase 4",development_code="exa-cel"),
    _row("Hematology","Beta thalassemia","Conditioning Regimens","Research"),
    _row("Hematology","Beta thalassemia","In vivo Gene Editing","Research"),
    _row("Hematology","Beta thalassemia","Small Molecules","Research"),
    _row("Cystic Fibrosis","Cystic fibrosis","Ivacaftor","Phase 4",molecule="ivacaftor"),
    _row("Cystic Fibrosis","Cystic fibrosis","Lumacaftor/Ivacaftor","Phase 4"),
    _row("Cystic Fibrosis","Cystic fibrosis","Tezacaftor/Ivacaftor + Ivacaftor","Phase 4"),
    _row("Cystic Fibrosis","Cystic fibrosis","Elexacaftor/Tezacaftor/Ivacaftor + Ivacaftor","Phase 4"),
    _row("Cystic Fibrosis","Cystic fibrosis","Vanzacaftor / Tezacaftor / Deutivacaftor","Phase 4"),
    _row("Cystic Fibrosis","Cystic fibrosis","Additional Small Molecules","Research"),
    _row("Cystic Fibrosis","Cystic fibrosis","Additional Genetic Therapies","Research",notes="Source text names CRISPR and Moderna as external partners for genetic approaches."),
    _row("Neuromuscular","Duchenne muscular dystrophy (DMD)","DMD","Research"),
    _row("Immunology","Generalized myasthenia gravis (gMG)","Povetacicept","Phase 2",molecule="povetacicept"),
    _row("Renal","IgA nephropathy (IgAN)","Povetacicept","Phase 3",molecule="povetacicept"),
    _row("Neuromuscular","Myotonic dystrophy type 1 (DM1)","VX-670","Phase 1/2",development_code="VX-670"),
    _row("Neuromuscular","Myotonic dystrophy type 1 (DM1)","Small Molecules","Research"),
    _row("Pain","Moderate-to-severe acute pain","Suzetrigine","Phase 4",molecule="suzetrigine",notes="Displayed by source as Suzetrigine (Moderate-to-Severe Acute Pain)."),
    _row("Pain","Painful diabetic peripheral neuropathy","Suzetrigine","Phase 3",molecule="suzetrigine",notes="Displayed by source as Suzetrigine (Painful Diabetic Peripheral Neuropathy)."),
    _row("Pain","Painful diabetic peripheral neuropathy","VX-993","Phase 2",development_code="VX-993",notes="Displayed by source as VX-993 (Painful Diabetic Peripheral Neuropathy)."),
    _row("Pain","Acute and neuropathic pain","Additional Small Molecules","Research"),
    _row("Renal","Primary membranous nephropathy (pMN)","Povetacicept","Phase 2/3",molecule="povetacicept"),
    _row("Hematology","Sickle cell disease (SCD)","Exa-cel","Phase 4",development_code="exa-cel"),
    _row("Hematology","Sickle cell disease (SCD)","Conditioning Regimens","Research"),
    _row("Hematology","Sickle cell disease (SCD)","In vivo Gene Editing","Research"),
    _row("Hematology","Sickle cell disease (SCD)","Small Molecules","Research"),
    _row("Cell Therapy","Type 1 diabetes (T1D)","Zimislecel","Phase 1/2/3",molecule="zimislecel",aliases=["VX-880"],notes="Source explicitly states formerly VX-880."),
    _row("Cell Therapy","Type 1 diabetes (T1D)","Device With Cell Therapy","Research"),
    _row("Cell Therapy","Type 1 diabetes (T1D)","Hypoimmune Cell Therapy","Research"),
]


class VertexSnapshotResponse(BaseModel):
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


def snapshot_response() -> VertexSnapshotResponse:
    phase_counts: Dict[str, int] = {}
    ta_counts: Dict[str, int] = {}
    for row in ROWS:
        phase_counts[row["phase"]] = phase_counts.get(row["phase"], 0) + 1
        ta_counts[row["therapeuticArea"]] = ta_counts.get(row["therapeuticArea"], 0) + 1

    sentinel = {
        "Inaxaplin": any(r["asset"] == "Inaxaplin" for r in ROWS),
        "VX-407": any(r["asset"] == "VX-407" for r in ROWS),
        "Povetacicept": any(r["asset"] == "Povetacicept" for r in ROWS),
        "VX-670": any(r["asset"] == "VX-670" for r in ROWS),
        "Suzetrigine": any(r["asset"] == "Suzetrigine" for r in ROWS),
        "VX-993": any(r["asset"] == "VX-993" for r in ROWS),
        "Zimislecel": any(r["asset"] == "Zimislecel" for r in ROWS),
    }
    issues = []
    if len(ROWS) != 31:
        issues.append({"issue": f"snapshot row count changed: {len(ROWS)} != 31"})
    if not all(sentinel.values()):
        issues.append({"issue": "one or more required sentinel assets missing"})

    return VertexSnapshotResponse(
        version=ADAPTER_PROFILE,
        routeVersion=ROUTE_VERSION,
        company="Vertex Pharmaceuticals",
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
            "sentinels": sentinel,
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


@app.get("/extract/vertex/pipeline-snapshot/health")
async def vertex_snapshot_health() -> Dict[str, Any]:
    return {
        "ok": True,
        "version": ADAPTER_PROFILE,
        "routeVersion": ROUTE_VERSION,
        "readOnly": True,
        "snapshotOnly": True,
    }


@app.get("/extract/vertex/pipeline-snapshot", response_model=VertexSnapshotResponse)
async def vertex_snapshot_route(
    x_adapter_key: str | None = Header(default=None),
) -> VertexSnapshotResponse:
    _auth(x_adapter_key)
    return snapshot_response()
