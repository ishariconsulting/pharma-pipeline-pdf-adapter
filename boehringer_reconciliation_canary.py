"""Read-only Boehringer 2025 annual-report snapshot -> current Portfolio reconciliation.

The source is a dated 2025-12-31 annual-report snapshot, while the Portfolio
snapshot is current as of 2026-09-21. Phase differences are therefore
historical variance signals only and MUST NOT be applied as current phase
downgrades. No Airtable/master writes.
"""
from __future__ import annotations

import asyncio
import json
from collections import Counter
from typing import Any, Dict, List

import boehringer_annual_report_pipeline_extension as bi
import portfolio_discovery_extension_v11 as comparator
import portfolio_discovery_extension_v12  # noqa: F401


SNAPSHOT_AS_OF = "2026-09-21"
SOURCE_AS_OF = "2025-12-31"
SOURCE_WATCH_RECORD_ID = "recTJixjrXbSdVt53"


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
    treatment: List[str] | None = None,
    biomarker: str = "",
) -> Dict[str, Any]:
    return {
        "recordId": record_id,
        "company": "Boehringer Ingelheim",
        "asset": asset or None,
        "molecule": molecule or None,
        "developmentCode": code or None,
        "brand": asset or None,
        "aliases": aliases or [],
        "indication": indication or None,
        "controlledIndication": controlled or None,
        "indicationAliases": indication_aliases or ([controlled] if controlled else []),
        "treatmentSettingLine": treatment or [],
        "biomarkerPatientSegment": biomarker or None,
        "phase": phase or None,
    }


PORTFOLIO_SNAPSHOT: List[Dict[str, Any]] = [
    p("rec1Wy5om4RnqUL6Z","BI 1815368","BI 1815368","Diabetic macular edema","Phase 2","Diabetic Macular Edema"),
    p("rec2IufAoD77Cfeq9","OFEV","nintedanib","Idiopathic pulmonary fibrosis","Approved","Idiopathic Pulmonary Fibrosis"),
    p("rec2JHbtFwrzTje2t","BI 771716","BI 771716","Geographic atrophy secondary to age-related macular degeneration","Phase 2","Geographic Atrophy"),
    p("rec3ciLGFqz3uwGKO","JASCAYD","nerandomilast","Progressive pulmonary fibrosis","Approved","Progressive Pulmonary Fibrosis"),
    p("rec4pXhTmu6BS9ZrQ","BI 765423","BI 765423","Idiopathic pulmonary fibrosis","Phase 2","Idiopathic Pulmonary Fibrosis"),
    p("rec50P5OpSIeXAmDT","zongertinib","zongertinib","Resectable HER2-mutant non-small cell lung cancer","Phase 3","Non-Small Cell Lung Cancer",biomarker="HER2-mutant"),
    p("rec6lb0BIicCEwJWM","SPEVIGO","spesolimab","Generalized pustular psoriasis - prevention of flares","Approved","Psoriasis"),
    p("rec7ZzyIJPkvw1J3P","apecotrep","apecotrep / BI 764198","Primary focal segmental glomerulosclerosis (FSGS)","Phase 3","Focal Segmental Glomerulosclerosis",aliases=["BI 764198"]),
    p("rec8uTcCSQ4bI1MzH","HERNEXEOS","zongertinib","Initial treatment of HER2-mutant advanced non-small cell lung cancer","Approved","Non-Small Cell Lung Cancer",treatment=["1L"],biomarker="HER2-mutant"),
    p("recBAk1XV4l80ratu","avenciguat / BI 685509","avenciguat / BI 685509","Systemic sclerosis","Phase 2","Systemic Sclerosis",aliases=["avenciguat","BI 685509"]),
    p("recE2q8NnJrAIkbqP","BI 770371","BI 770371","Metabolic dysfunction-associated steatohepatitis (MASH)","Phase 2","Metabolic Dysfunction-Associated Steatohepatitis"),
    p("recEfhiGaxaHRVtDF","survodutide","survodutide / BI 456906","Obesity or overweight without type 2 diabetes","Phase 3","Obesity",aliases=["BI 456906"]),
    p("recHJq5xL6YkeDnQ4","vicadrostat + empagliflozin","vicadrostat / BI 690517 + empagliflozin","Chronic kidney disease","Phase 3","Chronic Kidney Disease",aliases=["BI 690517"]),
    p("recOYDsyrbnl7FANU","survodutide","survodutide / BI 456906","Metabolic dysfunction-associated steatohepatitis (MASH) with fibrosis","Phase 3","Metabolic Dysfunction-Associated Steatohepatitis",aliases=["BI 456906"]),
    p("recVLvlWVfSHowOeF","JASCAYD","nerandomilast","Idiopathic pulmonary fibrosis","Approved","Idiopathic Pulmonary Fibrosis"),
    p("recVe4l4bwaGmgeWV","obrixtamig","obrixtamig / BI 764532","Extensive-stage small cell lung cancer - first line","Phase 3","Small Cell Lung Cancer",aliases=["BI 764532"]),
    p("recVpEu71lIhjeGHN","nerandomilast","nerandomilast","Systemic sclerosis","Phase 2","Systemic Sclerosis"),
    p("recWJWyElnaDVOZWP","CT-155","CT-155 prescription digital therapeutic","Schizophrenia - negative symptoms and functional impairment","Phase 3","Schizophrenia",aliases=["CT-155"]),
    p("recY2KMRMJuxpiliG","BI 1584862","BI 1584862","Geographic atrophy secondary to age-related macular degeneration","Phase 2","Geographic Atrophy"),
    p("recaKvJ3Yau5zsre2","obrixtamig","obrixtamig / BI 764532","Advanced extrapulmonary neuroendocrine carcinoma - first line","Phase 3","Extrapulmonary Neuroendocrine Carcinoma",aliases=["BI 764532"]),
    p("recaXaICEsAr64CFN","JARDIANCE","empagliflozin","Type 2 diabetes mellitus","Approved","Type 2 Diabetes"),
    p("receg3RgmjZTGVO1E","OFEV","nintedanib","Progressive pulmonary fibrosis / progressive fibrosing interstitial lung disease","Approved","Progressive Pulmonary Fibrosis"),
    p("recfQ9rStBsGqyTyG","vicadrostat + empagliflozin","vicadrostat / BI 690517 + empagliflozin","Cardiovascular risk reduction in type 2 diabetes, hypertension and established cardiovascular disease","Phase 3","",aliases=["BI 690517"],indication_aliases=["Type 2 Diabetes","Hypertension"]),
    p("rech9UgmSb0Su5UoM","vicadrostat + empagliflozin","vicadrostat / BI 690517 + empagliflozin","Heart failure with reduced ejection fraction","Phase 3","Heart Failure",aliases=["BI 690517"],biomarker="Reduced ejection fraction"),
    p("rechPSattqq9RoSDr","SPEVIGO","spesolimab","Generalized pustular psoriasis - treatment of flares","Approved","Psoriasis"),
    p("reclhto1cwEkIw7Fk","zongertinib","zongertinib","HER2-altered advanced solid tumors including breast, colorectal and esophageal cancers","Phase 2","Advanced Solid Tumours (Basket)"),
    p("recmkFJNfWE86zXwM","JARDIANCE","empagliflozin","Heart failure across the ejection-fraction spectrum","Approved","Heart Failure"),
    p("recnDendIAMp86Ikz","SPIRIVA","tiotropium","Chronic obstructive pulmonary disease","Approved","Chronic Obstructive Pulmonary Disease"),
    p("recq79jntAOxg6lI4","verducatib / BI 1291583","verducatib / BI 1291583","Bronchiectasis","Phase 3","Bronchiectasis",aliases=["verducatib","BI 1291583"]),
    p("recqoZIowixHn033c","OFEV","nintedanib","Systemic sclerosis-associated interstitial lung disease","Approved","Systemic Sclerosis"),
    p("recrnOINXaHVtrXJh","TRAJENTA / JENTADUETO","linagliptin / linagliptin-metformin","Type 2 diabetes mellitus","Approved","Type 2 Diabetes"),
    p("recsS0GHatsDIGnkd","vicadrostat + empagliflozin","vicadrostat / BI 690517 + empagliflozin","Heart failure with preserved ejection fraction","Phase 3","Heart Failure",aliases=["BI 690517"],biomarker="Preserved ejection fraction"),
    p("rect6381xr1HemiYc","JARDIANCE","empagliflozin","Chronic kidney disease","Approved","Chronic Kidney Disease"),
    p("recvxhCENX9Ayc0Ug","HERNEXEOS","zongertinib","Adults with unresectable or metastatic non-squamous non-small cell lung cancer whose tumors have HER2 (ERBB2) tyrosine kinase domain activating mutations, as detected by an FDA-authorized test","Approved","Non-Small Cell Lung Cancer",biomarker="Adults; HER2 (ERBB2) TKD activating mutation"),
    p("recyYjS4wIsXV9AAy","BI 764524","BI 764524","Diabetic retinopathy","Phase 2","Diabetic Retinopathy"),
    p("reczuif6TqYKrbj5j","BI 1819479","BI 1819479","Idiopathic pulmonary fibrosis and progressive pulmonary fibrosis","Phase 2","",indication_aliases=["Idiopathic Pulmonary Fibrosis","Progressive Pulmonary Fibrosis"]),
]


INDICATION_MAP = {
    "obesity": "Obesity",
    "mash": "Metabolic Dysfunction-Associated Steatohepatitis",
    "ckd": "Chronic Kidney Disease",
    "hfpEF".lower(): "Heart Failure",
    "hfrEF".lower(): "Heart Failure",
    "fsgs": "Focal Segmental Glomerulosclerosis",
    "nsclc": "Non-Small Cell Lung Cancer",
    "epnec": "Extrapulmonary Neuroendocrine Carcinoma",
    "ipf": "Idiopathic Pulmonary Fibrosis",
    "ppf": "Progressive Pulmonary Fibrosis",
    "be": "Bronchiectasis",
    "ssc": "Systemic Sclerosis",
    "schizophrenia": "Schizophrenia",
    "dr": "Diabetic Retinopathy",
    "dme": "Diabetic Macular Edema",
    "ga": "Geographic Atrophy",
}


def _to_source_row(row: Dict[str, Any]) -> comparator.DiscoverySourceRow:
    raw_indication = str(row.get("indication") or "").strip()
    controlled = INDICATION_MAP.get(raw_indication.lower(), "")
    return comparator.DiscoverySourceRow(
        company="Boehringer Ingelheim",
        sourceFamily="Boehringer Ingelheim 2025 Highlights",
        sourceRecordId=row.get("sourceRecordId"),
        sourceUrl=row.get("sourceUrl"),
        sourceWatchRecordId=SOURCE_WATCH_RECORD_ID,
        asset=row.get("asset"),
        molecule=row.get("molecule"),
        developmentCode=row.get("developmentCode"),
        brand=row.get("brand"),
        indication=raw_indication or None,
        controlledIndicationCandidate=controlled or None,
        phase=row.get("phase"),
        programStatus="Active",
        sponsorOwner="Boehringer Ingelheim",
        partners=[],
        ownershipResolved=True,
        strategicPhase1=False,
        importantLabelExpansion=False,
        marketedStrategicRx=False,
        genericCommodity=False,
    )


async def run_canary() -> Dict[str, Any]:
    source = await bi.extract_boehringer_annual_pipeline()
    request = comparator.DiscoveryCompareRequest(
        company="Boehringer Ingelheim",
        sourceRows=[_to_source_row(row) for row in source.rows],
        portfolioRows=[comparator.PortfolioSnapshotRow(**row) for row in PORTFOLIO_SNAPSHOT],
        companyAliases=["Boehringer Ingelheim", "Boehringer Ingelheim International GmbH"],
        batchRunId=f"BOEHRINGER-AR25-CANARY-{SNAPSHOT_AS_OF}",
    )
    result = comparator.compare_discovery(request)

    classifications = Counter(c.get("classification") for c in result.candidates)
    decisions = Counter(c.get("commercialInclusionDecision") for c in result.candidates)
    methods = Counter(c.get("matchMethod") for c in result.candidates)
    confidence = Counter(c.get("matchConfidence") for c in result.candidates)
    phase_deltas = []
    for c in result.candidates:
        for d in c.get("fieldDeltas") or []:
            if d.get("field") == "Development Phase":
                phase_deltas.append({
                    "asset": c.get("asset"),
                    "indication": c.get("indication"),
                    "source2025": d.get("sourceValue"),
                    "currentPortfolio2026": d.get("portfolioValue"),
                    "historicalOnly": True,
                })

    in_scope = [c for c in result.candidates if c.get("commercialInclusionDecision") == "Include"]
    unresolved = [c for c in in_scope if c.get("classification") not in {"MATCHED", "EXCLUDED BY RULE"}]

    ready = bool(
        source.readyForDiscovery
        and source.rowCount == 47
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
        "version": "BOEHRINGER_AR25_RECONCILIATION_CANARY_V1",
        "readyForSnapshotBindingValidation": ready,
        "sourceAsOf": SOURCE_AS_OF,
        "portfolioSnapshotAsOf": SNAPSHOT_AS_OF,
        "historicalSnapshotComparison": True,
        "phaseDeltasAreCurrentWrites": False,
        "sourceReadyForDiscovery": source.readyForDiscovery,
        "sourceRows": source.rowCount,
        "portfolioSnapshotRows": len(PORTFOLIO_SNAPSHOT),
        "classifications": dict(classifications),
        "commercialDecisions": dict(decisions),
        "matchMethods": dict(methods),
        "matchConfidence": dict(confidence),
        "inScopeRows": len(in_scope),
        "unresolvedInScopeCount": len(unresolved),
        "unresolvedInScopeSample": [compact(c) for c in unresolved[:30]],
        "historicalPhaseDeltaCount": len(phase_deltas),
        "historicalPhaseDeltaSample": phase_deltas[:20],
        "sourceIssues": source.issues,
        "masterWrites": 0,
    }


async def _startup() -> None:
    try:
        print(
            "BOEHRINGER_AR25_RECONCILIATION_CANARY "
            + json.dumps(await run_canary(), ensure_ascii=False),
            flush=True,
        )
    except Exception as exc:
        print(
            "BOEHRINGER_AR25_RECONCILIATION_CANARY "
            + json.dumps({
                "readyForSnapshotBindingValidation": False,
                "error": f"{type(exc).__name__}: {exc}",
                "masterWrites": 0,
            }),
            flush=True,
        )


@bi.app.on_event("startup")
async def _schedule_boehringer_ar25_reconciliation() -> None:
    asyncio.create_task(_startup())
