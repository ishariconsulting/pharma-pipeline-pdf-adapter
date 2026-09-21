"""Read-only Vertex official pipeline snapshot -> current Portfolio reconciliation.

The Vertex live pipeline page is currently inaccessible from the Render/browser
runtime. This canary reconciles the dated first-party snapshot captured on
2026-09-21 against the current Airtable Portfolio snapshot. It does not write
Airtable/master data.
"""
from __future__ import annotations

import asyncio
import json
from collections import Counter
from typing import Any, Dict, List

import portfolio_discovery_extension_v11 as comparator
import portfolio_discovery_extension_v12  # noqa: F401 - patches comparator
import vertex_pipeline_snapshot_extension as vertex

SNAPSHOT_AS_OF = "2026-09-21"
SOURCE_WATCH_RECORD_ID = "rececZFW3IobI19Ei"


def p(
    record_id: str,
    asset: str,
    molecule: str,
    indication: str,
    phase: str,
    controlled: str = "",
    code: str = "",
    aliases: List[str] | None = None,
) -> Dict[str, Any]:
    return {
        "recordId": record_id,
        "company": "Vertex Pharmaceuticals",
        "asset": asset or None,
        "molecule": molecule or None,
        "developmentCode": code or None,
        "brand": asset or None,
        "aliases": aliases or [],
        "indication": indication or None,
        "controlledIndication": controlled or None,
        "indicationAliases": [controlled] if controlled else [],
        "treatmentSettingLine": [],
        "biomarkerPatientSegment": None,
        "phase": phase or None,
    }


PORTFOLIO_SNAPSHOT: List[Dict[str, Any]] = [
    p("rec0L8lU1PiLlYpop","VX-993","", "Diabetic Peripheral Neuropathic Pain","Phase 2","Diabetic Peripheral Neuropathic Pain","VX-993"),
    p("rec48sO6SeOynhkUF","VX-670","", "Myotonic Dystrophy","Phase 1/2","Myotonic Dystrophy","VX-670"),
    p("rec4e54FKbByAEo69","zimislecel","zimislecel","Type 1 diabetes with impaired awareness of hypoglycemia and severe hypoglycemic events","Phase 3","Type 1 Diabetes","VX-880",["VX-880"]),
    p("rec8WYm4xRyl7p76t","VX-828","", "Cystic Fibrosis","Phase 1/2","Cystic Fibrosis","VX-828"),
    p("recH1YiTj2WuKF86e","atumelnant","atumelnant","Adults with classic congenital adrenal hyperplasia due to 21-hydroxylase deficiency; Phase 3 CALM-CAH","Phase 3","Congenital Adrenal Hyperplasia","CRN04894"),
    p("recLBCdzR7ZdWNpaQ","povetacicept","povetacicept","Generalized myasthenia gravis in adults; Phase 2 proof-of-concept","Phase 2","Generalized Myasthenia Gravis"),
    p("recP7eGUz6hJBebfE","JOURNAVX","suzetrigine","Moderate-to-severe acute pain in adults","Approved","Acute Pain","VX-548",["suzetrigine"]),
    p("recSoCHj49V7z6Gqr","VX-407","", "Autosomal Dominant Polycystic Kidney Disease","Phase 2","Autosomal Dominant Polycystic Kidney Disease","VX-407"),
    p("recUmgCcyz7A3crOE","CASGEVY","exagamglogene autotemcel","Sickle cell disease in patients age 2 years and older with recurrent vaso-occlusive crises","Approved","Sickle Cell Disease","exa-cel",["Exa-cel"]),
    p("recWWxklUomuWRUcf","ALYFTREK","vanzacaftor / tezacaftor / deutivacaftor","Cystic fibrosis in patients age 6 years and older with a CFTR variant that is responsive based on clinical/in-vitro data or results in CFTR protein production","Approved","Cystic Fibrosis","",["Vanzacaftor / Tezacaftor / Deutivacaftor"]),
    p("recWpASzQdHgAojgc","povetacicept","povetacicept","Adults with immunoglobulin A nephropathy; BLA accepted for accelerated approval supported by Phase 3 RAINIER interim analysis","Phase 3","IgA Nephropathy"),
    p("recZQOfq1XT6JUQOo","inaxaplin","inaxaplin","APOL1-mediated proteinuric kidney disease in patients with two APOL1 risk variants","Phase 3","APOL1-Mediated Kidney Disease","VX-147"),
    p("reccQp1TPFnXr7uBL","VX-522","", "Cystic Fibrosis","Phase 1/2","Cystic Fibrosis","VX-522"),
    p("reclX5ntrwyRwkKXG","VX-581","", "Cystic Fibrosis","Phase 1","Cystic Fibrosis","VX-581"),
    p("recoz0ncgptITarFv","suzetrigine / JOURNAVX","suzetrigine","Pain associated with diabetic peripheral neuropathy in adults","Phase 3","Diabetic Peripheral Neuropathic Pain","VX-548",["suzetrigine"]),
    p("recscKrEUs75dHSD6","povetacicept","povetacicept","Primary membranous nephropathy in adults; Phase 3 portion of OLYMPUS underway","Phase 3","Primary Membranous Nephropathy"),
    p("recsl8YNXQERCZR81","PALSONIFY","paltusotine","Adults with acromegaly who had an inadequate response to surgery and/or for whom surgery is not an option","Approved","Acromegaly","CRN00808"),
    p("recvuYGaSAU0AfX2n","TRIKAFTA / KAFTRIO","elexacaftor / tezacaftor / ivacaftor","Cystic fibrosis in eligible patients with responsive CFTR variants; established elexacaftor/tezacaftor/ivacaftor franchise","Approved","Cystic Fibrosis","",["Elexacaftor/Tezacaftor/Ivacaftor + Ivacaftor"]),
    p("recyZXMGlHxkAsBge","CASGEVY","exagamglogene autotemcel","Transfusion-dependent beta thalassemia in patients age 2 years and older","Approved","Beta Thalassemia","exa-cel",["Exa-cel"]),
]


CONTROLLED = {
    "apol1-mediated kidney disease (amkd)": "APOL1-Mediated Kidney Disease",
    "autosomal dominant polycystic kidney disease (adpkd)": "Autosomal Dominant Polycystic Kidney Disease",
    "beta thalassemia": "Beta Thalassemia",
    "cystic fibrosis": "Cystic Fibrosis",
    "generalized myasthenia gravis (gmg)": "Generalized Myasthenia Gravis",
    "iga nephropathy (igan)": "IgA Nephropathy",
    "myotonic dystrophy type 1 (dm1)": "Myotonic Dystrophy",
    "moderate-to-severe acute pain": "Acute Pain",
    "painful diabetic peripheral neuropathy": "Diabetic Peripheral Neuropathic Pain",
    "primary membranous nephropathy (pmn)": "Primary Membranous Nephropathy",
    "sickle cell disease (scd)": "Sickle Cell Disease",
    "type 1 diabetes (t1d)": "Type 1 Diabetes",
}


def _source_row(row: Dict[str, Any]) -> comparator.DiscoverySourceRow:
    phase = str(row.get("phase") or "")
    asset = str(row.get("asset") or "")
    indication = str(row.get("indication") or "")
    dev = str(row.get("developmentCode") or "")
    if asset == "Zimislecel":
        # The official page explicitly says "formerly VX-880".
        dev = "VX-880"
    return comparator.DiscoverySourceRow(
        company="Vertex Pharmaceuticals",
        sourceFamily="Vertex Official R&D Pipeline Snapshot",
        sourceRecordId=row.get("sourceRecordId"),
        sourceUrl=vertex.SOURCE_URL,
        sourceWatchRecordId=SOURCE_WATCH_RECORD_ID,
        asset=asset or None,
        molecule=row.get("molecule") or None,
        developmentCode=dev or None,
        brand=None,
        indication=indication or None,
        controlledIndicationCandidate=CONTROLLED.get(indication.lower()) or None,
        phase=phase or None,
        programStatus=row.get("programStatus") or None,
        sponsorOwner="Vertex Pharmaceuticals",
        partners=[],
        ownershipResolved=True,
        strategicPhase1=False,
        importantLabelExpansion=False,
        marketedStrategicRx=(phase == "Phase 4"),
        genericCommodity=False,
    )


async def run_canary() -> Dict[str, Any]:
    snap = vertex.snapshot_response()
    clinical = [row for row in snap.rows if row.get("phase") != "Research"]
    research = [row for row in snap.rows if row.get("phase") == "Research"]

    req = comparator.DiscoveryCompareRequest(
        company="Vertex Pharmaceuticals",
        sourceRows=[_source_row(row) for row in clinical],
        portfolioRows=[comparator.PortfolioSnapshotRow(**row) for row in PORTFOLIO_SNAPSHOT],
        companyAliases=["Vertex Pharmaceuticals", "Vertex Pharmaceuticals Incorporated"],
        batchRunId="VERTEX-SNAPSHOT-2026-09-21",
    )
    result = comparator.compare_discovery(req)

    classifications = Counter(c.get("classification") for c in result.candidates)
    decisions = Counter(c.get("commercialInclusionDecision") for c in result.candidates)
    methods = Counter(c.get("matchMethod") for c in result.candidates)
    confidence = Counter(c.get("matchConfidence") for c in result.candidates)

    unresolved = [
        c for c in result.candidates
        if c.get("commercialInclusionDecision") == "Include"
        and c.get("classification") not in {"MATCHED", "EXCLUDED BY RULE"}
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
        and snap.rowCount == 31
        and len(clinical) == 17
        and classifications.get("SOURCE UNAVAILABLE", 0) == 0
        and classifications.get("OWNERSHIP REVIEW", 0) == 0
    )

    return {
        "version": "VERTEX_PIPELINE_SNAPSHOT_RECONCILIATION_CANARY_V1",
        "readyForSnapshotBindingValidation": ready,
        "sourceAsOf": vertex.SOURCE_AS_OF,
        "sourceRows": snap.rowCount,
        "clinicalRowsCompared": len(clinical),
        "researchRowsRetainedButNotCommerciallyReconciled": len(research),
        "portfolioSnapshotRows": len(PORTFOLIO_SNAPSHOT),
        "classifications": dict(classifications),
        "commercialDecisions": dict(decisions),
        "matchMethods": dict(methods),
        "matchConfidence": dict(confidence),
        "unresolvedInScopeCount": len(unresolved),
        "unresolvedInScopeSample": [compact(c) for c in unresolved[:25]],
        "phaseDeltaCount": len(phase_deltas),
        "phaseDeltaSample": phase_deltas[:20],
        "sourceIssues": snap.issues,
        "liveRenderRetrievalAvailable": False,
        "masterWrites": 0,
    }


async def _startup() -> None:
    try:
        print(
            "VERTEX_PIPELINE_SNAPSHOT_RECONCILIATION_CANARY "
            + json.dumps(await run_canary(), ensure_ascii=False),
            flush=True,
        )
    except Exception as exc:
        print(
            "VERTEX_PIPELINE_SNAPSHOT_RECONCILIATION_CANARY "
            + json.dumps({
                "readyForSnapshotBindingValidation": False,
                "error": f"{type(exc).__name__}: {exc}",
                "masterWrites": 0,
            }),
            flush=True,
        )


@vertex.app.on_event("startup")
async def _schedule_vertex_snapshot_reconciliation() -> None:
    asyncio.create_task(_startup())
