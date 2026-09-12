"""AstraZeneca source-to-Portfolio reconciliation canary.

This is a dated READ-ONLY snapshot used only to validate Portfolio Discovery
against the current 70 AstraZeneca Portfolio rows. It does not write to
Airtable and must not be used as a production source of Portfolio truth.
"""

import asyncio
from collections import Counter
from typing import Any, Dict, List

import portfolio_discovery_extension_v11 as comparator
import portfolio_discovery_extension_v12  # noqa: F401 - patches comparator globals
import astrazeneca_pipeline_adapter as az


SNAPSHOT_AS_OF = "2026-09-12"


def p(record_id: str, asset: str = "", molecule: str = "", code: str = "", indication: str = "", controlled: str = "", phase: str = "", aliases: List[str] | None = None) -> Dict[str, Any]:
    return {
        "recordId": record_id,
        "company": "AstraZeneca",
        "asset": asset or None,
        "molecule": molecule or None,
        "developmentCode": code or None,
        "brand": asset or None,
        "aliases": aliases or [],
        "indication": indication or None,
        "controlledIndication": controlled or None,
        "indicationAliases": [],
        "phase": phase or None,
    }


PORTFOLIO_SNAPSHOT: List[Dict[str, Any]] = [
    p("rec0hQevUGgEEEBhH", "Brilinta", "ticagrelor", "AZD6140", "Acute coronary syndrome", "Acute Coronary Syndrome", "Approved"),
    p("rec2zPsp7rIwKg1Yv", "Lynparza", "olaparib", "AZD2281", "Ovarian cancer", "Ovarian Cancer", "Approved"),
    p("rec5Iab4XF57UReBe", "Airsupra", "albuterol/budesonide", "PT027", "Asthma", "Asthma", "Approved"),
    p("rec5MdHRvueybrTz5", "Tezspire", "tezepelumab", "AMG 157 / MEDI9929", "Chronic rhinosinusitis with nasal polyps", "Chronic Rhinosinusitis with Nasal Polyps", "Approved"),
    p("rec6py8PG8XOIh6kJ", "Imfinzi", "durvalumab", "MEDI4736", "Small cell lung cancer", "Small Cell Lung Cancer", "Approved"),
    p("rec7mq3SbkmNpC9Ja", "Tagrisso", "osimertinib", "AZD9291", "Completely resected EGFR exon 19 deletion or exon 21 L858R-mutated non-small cell lung cancer - adjuvant", "Non-Small Cell Lung Cancer", "Approved"),
    p("rec85zF9x79TEyjdU", "Farxiga", "dapagliflozin", "AZD2843", "Type 2 diabetes", "Type 2 Diabetes", "Approved"),
    p("rec8F3tsnXdaQdvB9", "Lynparza", "olaparib", "AZD2281", "Germline BRCA-mutated, HER2-negative high-risk early breast cancer after neoadjuvant or adjuvant chemotherapy - adjuvant olaparib", "Breast Cancer", "Approved"),
    p("rec8ZeXsqHCFwgzKF", "saruparib", "saruparib", "AZD5305", "Breast cancer", "Breast Cancer", "Phase 3"),
    p("recAmO3xTszjgIgYN", "Truqap", "capivasertib", "AZD5363", "Prostate cancer", "Prostate Cancer", "Approved"),
    p("recBYUwBlge9dFUuy", "Calquence", "acalabrutinib", "ACP-196", "Chronic lymphocytic leukaemia", "Chronic Lymphocytic Leukemia", "Approved"),
    p("recBu9bc3CoNa7pxN", "Enhertu", "trastuzumab deruxtecan", "DS-8201", "HER2-positive locally advanced or metastatic gastric/GEJ adenocarcinoma after a prior trastuzumab-based regimen", "Gastric and Gastroesophageal Junction Adenocarcinoma", "Approved"),
    p("recDBA0LsqNUPPAsg", "Imfinzi", "durvalumab", "MEDI4736", "Hepatocellular carcinoma", "Hepatocellular Carcinoma", "Approved"),
    p("recDHEkHiWfgcvTYY", "Baxfendy", "baxdrostat", "AZD4831", "Hypertension", "Hypertension", "Approved"),
    p("recDJejOA0ilqbw1E", "Farxiga", "dapagliflozin", "AZD2843", "Chronic kidney disease", "Chronic Kidney Disease", "Approved"),
    p("recDfJ8aigaLt71I6", "Enhertu", "trastuzumab deruxtecan", "DS-8201", "Non-small cell lung cancer", "Non-Small Cell Lung Cancer", "Approved"),
    p("recE1f4BqtxhDjq5p", "Ultomiris", "ravulizumab", "ALXN1210", "Atypical haemolytic uraemic syndrome", "Atypical Hemolytic Uremic Syndrome", "Approved"),
    p("recEoZ4Mi3ZtegHh0", "Koselugo", "selumetinib", "AZD6244", "Neurofibromatosis type 1", "Neurofibromatosis Type 1", "Approved"),
    p("recFyOPCWi3XPXr1O", "Ultomiris", "ravulizumab", "ALXN1210", "Generalised myasthenia gravis", "Generalized Myasthenia Gravis", "Approved"),
    p("recGNTT2Nwn9dlVOy", "Fasenra", "benralizumab", "MEDI-563", "Eosinophilic granulomatosis with polyangiitis", "Eosinophilic Granulomatosis with Polyangiitis", "Approved"),
    p("recGPCubXdDklAAIr", "Imfinzi", "durvalumab", "MEDI4736", "Endometrial cancer", "Endometrial Cancer", "Approved"),
    p("recHjuSGlYS1RMqSk", "Breztri", "budesonide/glycopyrrolate/formoterol", "PT010", "Asthma", "Asthma", "Approved"),
    p("recIHWoxjEH7KPW8H", "Koselugo", "selumetinib", "AZD6244", "Neurofibromatosis type 1", "Neurofibromatosis Type 1", "Approved"),
    p("recIePkk4TUtJ3llI", "Tezspire", "tezepelumab", "AMG 157 / MEDI9929", "Severe asthma", "Asthma", "Approved"),
    p("recKIYcNQynbcnAdT", "Lynparza", "olaparib", "AZD2281", "Germline BRCA-mutated, HER2-negative metastatic breast cancer after prior chemotherapy", "Breast Cancer", "Approved"),
    p("recKN79cJ3UKpfDXB", "Soliris", "eculizumab", "", "Paroxysmal nocturnal haemoglobinuria", "Paroxysmal Nocturnal Hemoglobinuria", "Approved"),
    p("recNbirigeJqynzrk", "Saphnelo", "anifrolumab", "MEDI-546", "Lupus nephritis", "Lupus Nephritis", "Phase 3"),
    p("recPNgmvmMes2jFF3", "rilvegostomig", "rilvegostomig", "AZD2936", "Non-small cell lung cancer", "Non-Small Cell Lung Cancer", "Phase 3"),
    p("recPcePlwoPZQu93U", "Lynparza", "olaparib", "AZD2281", "Prostate cancer", "Prostate Cancer", "Approved"),
    p("recQqTU2IxP8H07L1", "Enhertu", "trastuzumab deruxtecan", "DS-8201", "HER2-positive unresectable or metastatic breast cancer after prior HER2-targeted therapy - second line", "Breast Cancer", "Approved"),
    p("recSVilH9OChJ5AIP", "Enhertu", "trastuzumab deruxtecan", "DS-8201", "HR-positive, HER2-low or HER2-ultralow unresectable or metastatic breast cancer after progression on one or more endocrine therapies in the metastatic setting", "Breast Cancer", "Approved"),
    p("recSepNqqmP3OukVB", "sonesitatug vedotin", "sonesitatug vedotin", "AZD0901", "CLDN18.2-positive locally advanced or metastatic gastric/GEJ adenocarcinoma in second and later lines - sonesitatug vedotin", "Gastric and Gastroesophageal Junction Adenocarcinoma", "Phase 3"),
    p("recTt7bz6NL3S47Eh", "Lokelma", "sodium zirconium cyclosilicate", "ZS-9", "Hyperkalaemia", "Hyperkalemia", "Approved"),
    p("recUYAnYLlPUikfNc", "Breztri", "budesonide/glycopyrrolate/formoterol", "PT010", "Chronic obstructive pulmonary disease", "Chronic Obstructive Pulmonary Disease", "Approved"),
    p("recXm75zZoRhoKBqy", "Calquence", "acalabrutinib", "ACP-196", "Mantle cell lymphoma", "Mantle Cell Lymphoma", "Approved"),
    p("recY0Gc0NbgQZA4IH", "AZD6234", "elecoglipron", "AZD6234", "Obesity", "Obesity", "Phase 2"),
    p("recYfOqJIy8tVKoOM", "ALXN1850", "efzimfotase alfa", "ALXN1850", "Hypophosphatasia", "Hypophosphatasia", "Phase 3"),
    p("recajca7rD4km1RLl", "Imfinzi", "durvalumab", "MEDI4736", "Resectable muscle-invasive bladder cancer - perioperative durvalumab with gemcitabine/cisplatin followed by adjuvant durvalumab", "Urothelial Carcinoma", "Approved"),
    p("recb67N1ACMG9imj8", "Voydeya", "danicopan", "ALXN2040", "Paroxysmal nocturnal haemoglobinuria", "Paroxysmal Nocturnal Hemoglobinuria", "Approved"),
    p("recbCnyP2IFGJDmtH", "Datroway", "datopotamab deruxtecan", "DS-1062", "HR-positive, HER2-negative unresectable or metastatic breast cancer after prior endocrine-based therapy and chemotherapy", "Breast Cancer", "Approved"),
    p("recbxWdAJwizzq16Q", "Tagrisso", "osimertinib", "AZD9291", "Non-small cell lung cancer", "Non-Small Cell Lung Cancer", "Approved"),
    p("recc6gK9OU5tpwFZG", "AZP-3601", "eneboparatide", "AZP-3601", "Chronic hypoparathyroidism", "Hypoparathyroidism", "Phase 3"),
    p("reccsYzku0psvd7iB", "Farxiga", "dapagliflozin", "AZD2843", "Heart failure", "Heart Failure", "Approved"),
    p("reccx2ZNlOlw9lXvd", "Imfinzi", "durvalumab", "MEDI4736", "Unresectable stage III NSCLC without progression after concurrent chemoradiotherapy - durvalumab consolidation", "Non-Small Cell Lung Cancer", "Approved"),
    p("recd5HoO7f1mgqxA1", "Wainua", "eplontersen", "ION-682884", "Hereditary transthyretin amyloidosis", "Hereditary Transthyretin Amyloidosis with Polyneuropathy (hATTR-PN)", "Approved"),
    p("rece8hNa4agXgArb8", "tozorakimab", "tozorakimab", "MEDI3506", "Chronic obstructive pulmonary disease", "Chronic Obstructive Pulmonary Disease", "Phase 3"),
    p("recfeYlusPVCZNM8D", "Saphnelo", "anifrolumab", "MEDI-546", "Systemic lupus erythematosus", "Systemic Lupus Erythematosus", "Approved"),
    p("recg2x8H9gsfUQVRS", "Datroway", "datopotamab deruxtecan", "DS-1062", "Non-small cell lung cancer", "Non-Small Cell Lung Cancer", "Approved"),
    p("rechhiXZjVMcBYdfN", "Imfinzi", "durvalumab", "MEDI4736", "Resectable NSCLC, tumour ≥4 cm and/or node-positive, no known EGFR mutation or ALK rearrangement - perioperative durvalumab", "Non-Small Cell Lung Cancer", "Approved"),
    p("recjQY9NzJJLzxOJj", "Imfinzi", "durvalumab", "MEDI4736", "Small cell lung cancer", "Small Cell Lung Cancer", "Approved"),
    p("recjSJSEtNpgRQOwt", "Truqap", "capivasertib", "AZD5363", "HR-positive, HER2-negative locally advanced or metastatic breast cancer with PIK3CA/AKT1/PTEN alteration after progression on at least one endocrine-based regimen or early recurrence after adjuvant therapy", "Breast Cancer", "Approved"),
    p("recjvhQTccBdCFzzA", "Ultomiris", "ravulizumab", "ALXN1210", "Neuromyelitis optica spectrum disorder", "Neuromyelitis Optica Spectrum Disorder", "Approved"),
    p("reckaZiCahEbzyFgM", "Tagrisso", "osimertinib", "AZD9291", "Locally advanced unresectable stage III EGFR exon 19 deletion or L858R-mutated NSCLC without progression during or after platinum chemoradiotherapy", "Non-Small Cell Lung Cancer", "Approved"),
    p("reckdnBKHQBj7s9Ad", "Imfinzi", "durvalumab", "MEDI4736", "Biliary tract cancer", "Biliary Tract Cancer", "Approved"),
    p("reclsqpKrcgXLnYFC", "camizestrant", "camizestrant", "AZD9833", "HR-positive, HER2-negative advanced breast cancer with emergent ESR1 mutation", "Breast Cancer", "Approved", ["Etcamah"]),
    p("reclxR1GrLelrHOZC", "camizestrant", "camizestrant", "AZD9833", "ER-positive, HER2-negative early breast cancer with intermediate-high or high recurrence risk after locoregional therapy - adjuvant camizestrant", "Early Stage Breast Cancer", "Phase 3", ["Etcamah"]),
    p("recm5S6FKvXCqFvVK", "Symbicort", "budesonide/formoterol", "", "Asthma", "Asthma", "Approved"),
    p("recn9AZWW1pNuwHup", "Datroway", "datopotamab deruxtecan", "DS-1062", "Breast cancer", "Breast Cancer", "Approved"),
    p("recpiEHYWJCO0MYfi", "ALXN2220", "cliramitug", "ALXN2220", "Transthyretin amyloid cardiomyopathy", "Transthyretin Amyloid Cardiomyopathy (ATTR-CM)", "Phase 3"),
    p("recpwOuN6NVfW61JL", "Imjudo", "tremelimumab", "CP-675206", "Hepatocellular carcinoma", "Hepatocellular Carcinoma", "Approved"),
    p("recrEUJ9cq2tBpWK4", "Imfinzi", "durvalumab", "MEDI4736", "BCG-naïve, high-risk non-muscle-invasive bladder cancer", "Urothelial Carcinoma", "Approved"),
    p("recs1NPSJHsqBZ7yi", "volrustomig", "volrustomig", "AZD5115", "Solid tumours", "Advanced Solid Tumours (Basket)", "Phase 3"),
    p("recs7RLFzXULCoDkJ", "Ultomiris", "ravulizumab", "ALXN1210", "Paroxysmal nocturnal haemoglobinuria", "Paroxysmal Nocturnal Hemoglobinuria", "Approved"),
    p("rectHCOaDYO8ySwko", "Fasenra", "benralizumab", "MEDI-563", "Severe asthma", "Asthma", "Approved"),
    p("recu5xloTeSl0vvMy", "Strensiq", "asfotase alfa", "", "Hypophosphatasia", "Hypophosphatasia", "Approved"),
    p("recw7fFQdBk604mBm", "ALXN1720", "gefurulimab", "ALXN1720", "Generalised myasthenia gravis", "Generalized Myasthenia Gravis", "Phase 3"),
    p("recw80zShZAsgIwYL", "Imfinzi", "durvalumab ± tremelimumab + platinum/gemcitabine", "MEDI4736 / NILE", "First-line unresectable locally advanced or metastatic urothelial carcinoma - durvalumab ± tremelimumab with platinum/gemcitabine", "Urothelial Carcinoma", "Phase 3"),
    p("recwPqJDRJuiJVYIk", "Enhertu", "trastuzumab deruxtecan", "DS-8201", "Breast cancer", "Breast Cancer", "Approved"),
    p("recySxxODoQnFQe32", "Tagrisso", "osimertinib", "AZD9291", "Locally advanced or metastatic EGFR T790M mutation-positive non-small cell lung cancer", "Non-Small Cell Lung Cancer", "Approved"),
    p("recyWu4YmaFSEzJco", "rilvegostomig", "rilvegostomig", "AZD2936", "Resected biliary tract cancer at high risk of recurrence - adjuvant rilvegostomig plus chemotherapy", "Biliary Tract Cancer", "Phase 3"),
]


def _to_source_row(row: az.AZPipelineRow) -> comparator.DiscoverySourceRow:
    return comparator.DiscoverySourceRow(
        company="AstraZeneca",
        sourceFamily=row.sourceFamily,
        sourceRecordId=row.sourceRecordId,
        sourceUrl=row.sourceUrl,
        asset=row.asset,
        molecule=row.molecule,
        developmentCode=row.developmentCode,
        brand=row.brand,
        indication=row.indication,
        phase=row.phase,
        programStatus="Active" if not row.removedSinceLastQuarter else "Removed",
        sponsorOwner="AstraZeneca",
        ownershipResolved=True,
        importantLabelExpansion=row.importantLabelExpansion,
        strategicPhase1=False,
    )


def _compact_candidate(candidate: Dict[str, Any]) -> str:
    asset = candidate.get("asset") or candidate.get("brand") or candidate.get("molecule") or candidate.get("developmentCode") or "?"
    indication = candidate.get("indication") or "?"
    classification = candidate.get("classification") or "?"
    delta = candidate.get("fieldDeltas") or {}
    return f"{classification}|{asset}|{indication}|delta={delta}"


async def run_canary() -> Dict[str, Any]:
    raw = await az._fetch_source_html()
    source_all = az.parse_pipeline_html(raw)
    source_in_scope = [r for r in source_all if r.commercialInScope]

    request = comparator.DiscoveryCompareRequest(
        company="AstraZeneca",
        sourceRows=[_to_source_row(r) for r in source_in_scope],
        portfolioRows=[comparator.PortfolioSnapshotRow(**row) for row in PORTFOLIO_SNAPSHOT],
        companyAliases=["AstraZeneca PLC"],
        batchRunId=f"AZ-CANARY-{SNAPSHOT_AS_OF}",
    )
    result = comparator.compare_discovery(request)
    summary = dict(result.summary)
    delta_counts = Counter()
    for candidate in result.candidates:
        for key in (candidate.get("fieldDeltas") or {}).keys():
            delta_counts[key] += 1

    unresolved = [
        _compact_candidate(c)
        for c in result.candidates
        if c.get("classification") not in {"MATCHED", "EXCLUDED BY RULE"}
    ]
    return {
        "version": result.version,
        "sourceRows": len(source_all),
        "commercialInScopeRows": len(source_in_scope),
        "portfolioSnapshotRows": len(PORTFOLIO_SNAPSHOT),
        "summary": summary,
        "fieldDeltaCounts": dict(delta_counts),
        "unresolvedCount": len(unresolved),
        "unresolvedSample": unresolved[:30],
    }


async def _startup_reconciliation_canary() -> None:
    try:
        result = await run_canary()
        print(f"AZ_RECONCILIATION_CANARY {result}", flush=True)
    except Exception as exc:
        print(f"AZ_RECONCILIATION_CANARY ok=False error={type(exc).__name__}:{exc}", flush=True)


# Register the canary on the same FastAPI app. It is background/read-only.
@az.app.on_event("startup")
async def _schedule_reconciliation_canary() -> None:
    asyncio.create_task(_startup_reconciliation_canary())
