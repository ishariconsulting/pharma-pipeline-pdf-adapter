"""Read-only J&J official development pipeline -> current Portfolio reconciliation canary.

Uses the validated reusable browser-required generic pipeline route and a dated
snapshot of the current Johnson & Johnson Portfolio rows from Airtable.
No Airtable or master-data writes.
"""
from __future__ import annotations

import asyncio
from collections import Counter
import json
import re
from typing import Any, Dict, List

import generic_pipeline_extension as gp
import portfolio_discovery_extension_v11 as comparator
import portfolio_discovery_extension_v12  # noqa: F401 - verified alias patches


SNAPSHOT_AS_OF = "2026-09-21"
SOURCE_WATCH_RECORD_ID = "recUaq5w669zo4Uyi"
SOURCE_URL = "https://www.investor.jnj.com/pipeline/development-pipeline/default.aspx"
PORTFOLIO_SNAPSHOT: List[Dict[str, Any]] = json.loads("[{\"recordId\":\"rec0dwVJQfE0vifTM\",\"company\":\"Johnson & Johnson\",\"asset\":\"CAPLYTA\",\"molecule\":\"lumateperone\",\"developmentCode\":null,\"brand\":\"CAPLYTA\",\"aliases\":[],\"indication\":\"Bipolar mania\",\"controlledIndication\":null,\"indicationAliases\":[],\"treatmentSettingLine\":[],\"biomarkerPatientSegment\":null,\"portfolioStatus\":null,\"phase\":\"Phase 3\"},{\"recordId\":\"rec32p8pboZNSz6g3\",\"company\":\"Johnson & Johnson\",\"asset\":\"CAPLYTA\",\"molecule\":\"lumateperone\",\"developmentCode\":null,\"brand\":\"CAPLYTA\",\"aliases\":[],\"indication\":\"Depressive episodes associated with bipolar I or II disorder (bipolar depression) in adults\",\"controlledIndication\":null,\"indicationAliases\":[],\"treatmentSettingLine\":[],\"biomarkerPatientSegment\":\"Adults\",\"portfolioStatus\":null,\"phase\":\"Approved\"},{\"recordId\":\"rec3eJOWW9gBqOSK2\",\"company\":\"Johnson & Johnson\",\"asset\":\"TECVAYLI + DARZALEX\",\"molecule\":\"teclistamab + daratumumab\",\"developmentCode\":null,\"brand\":\"TECVAYLI + DARZALEX\",\"aliases\":[],\"indication\":\"Relapsed/refractory multiple myeloma after 1-3 prior lines\",\"controlledIndication\":null,\"indicationAliases\":[],\"treatmentSettingLine\":[],\"biomarkerPatientSegment\":null,\"portfolioStatus\":null,\"phase\":\"Approved\"},{\"recordId\":\"rec4lkyrlTG26X4nz\",\"company\":\"Johnson & Johnson\",\"asset\":\"AKEEGA\",\"molecule\":\"niraparib + abiraterone acetate\",\"developmentCode\":null,\"brand\":\"AKEEGA\",\"aliases\":[],\"indication\":\"BRCA-positive metastatic castration-resistant prostate cancer\",\"controlledIndication\":null,\"indicationAliases\":[],\"treatmentSettingLine\":[],\"biomarkerPatientSegment\":\"BRCA-positive\",\"portfolioStatus\":null,\"phase\":\"Approved\"},{\"recordId\":\"rec5VtdV54LIYohee\",\"company\":\"Johnson & Johnson\",\"asset\":\"TREMFYA\",\"molecule\":\"guselkumab\",\"developmentCode\":null,\"brand\":\"TREMFYA\",\"aliases\":[],\"indication\":\"Active psoriatic arthritis\",\"controlledIndication\":null,\"indicationAliases\":[],\"treatmentSettingLine\":[],\"biomarkerPatientSegment\":null,\"portfolioStatus\":null,\"phase\":\"Approved\"},{\"recordId\":\"rec7hcnERgqfBRWno\",\"company\":\"Johnson & Johnson\",\"asset\":\"INLEXZO\",\"molecule\":\"gemcitabine intravesical system\",\"developmentCode\":null,\"brand\":\"INLEXZO\",\"aliases\":[],\"indication\":\"High-risk BCG-experienced non-muscle invasive bladder cancer\",\"controlledIndication\":null,\"indicationAliases\":[],\"treatmentSettingLine\":[],\"biomarkerPatientSegment\":null,\"portfolioStatus\":null,\"phase\":\"Phase 3\"},{\"recordId\":\"rec7me0Cr2yzzCtQ4\",\"company\":\"Johnson & Johnson\",\"asset\":\"ramantamig\",\"molecule\":null,\"developmentCode\":null,\"brand\":\"ramantamig\",\"aliases\":[],\"indication\":\"Multiple Myeloma\",\"controlledIndication\":null,\"indicationAliases\":[],\"treatmentSettingLine\":[],\"biomarkerPatientSegment\":null,\"portfolioStatus\":null,\"phase\":\"Phase 3\"},{\"recordId\":\"recAnDbeKgVF0EsJR\",\"company\":\"Johnson & Johnson\",\"asset\":\"IMAAVY\",\"molecule\":\"nipocalimab-aahu\",\"developmentCode\":null,\"brand\":\"IMAAVY\",\"aliases\":[],\"indication\":\"Generalized myasthenia gravis\",\"controlledIndication\":null,\"indicationAliases\":[],\"treatmentSettingLine\":[],\"biomarkerPatientSegment\":null,\"portfolioStatus\":null,\"phase\":\"Approved\"},{\"recordId\":\"recBB1y1TKH0PtUzr\",\"company\":\"Johnson & Johnson\",\"asset\":\"SPRAVATO\",\"molecule\":\"esketamine\",\"developmentCode\":null,\"brand\":\"SPRAVATO\",\"aliases\":[],\"indication\":\"Treatment-resistant depression / major depressive disorder\",\"controlledIndication\":null,\"indicationAliases\":[],\"treatmentSettingLine\":[],\"biomarkerPatientSegment\":null,\"portfolioStatus\":null,\"phase\":\"Approved\"},{\"recordId\":\"recBUGHXm28goplwS\",\"company\":\"Johnson & Johnson\",\"asset\":\"Bleximenib\",\"molecule\":\"bleximenib\",\"developmentCode\":\"JNJ-75276617\",\"brand\":\"Bleximenib\",\"aliases\":[],\"indication\":\"KMT2A- or NPM1-altered relapsed/refractory acute myeloid leukemia\",\"controlledIndication\":null,\"indicationAliases\":[],\"treatmentSettingLine\":[],\"biomarkerPatientSegment\":null,\"portfolioStatus\":null,\"phase\":\"Phase 2\"},{\"recordId\":\"recBzHWZbM5omD2Bx\",\"company\":\"Johnson & Johnson\",\"asset\":\"DARZALEX\",\"molecule\":\"daratumumab\",\"developmentCode\":null,\"brand\":\"DARZALEX\",\"aliases\":[],\"indication\":\"Multiple myeloma\",\"controlledIndication\":null,\"indicationAliases\":[],\"treatmentSettingLine\":[],\"biomarkerPatientSegment\":null,\"portfolioStatus\":null,\"phase\":\"Approved\"},{\"recordId\":\"recCrMGM1y6YTpEXT\",\"company\":\"Johnson & Johnson\",\"asset\":\"IMAAVY\",\"molecule\":\"nipocalimab-aahu\",\"developmentCode\":null,\"brand\":\"IMAAVY\",\"aliases\":[],\"indication\":\"Warm autoimmune hemolytic anemia\",\"controlledIndication\":null,\"indicationAliases\":[],\"treatmentSettingLine\":[],\"biomarkerPatientSegment\":null,\"portfolioStatus\":null,\"phase\":\"Approved\"},{\"recordId\":\"recCxalBR3NCv4w9A\",\"company\":\"Johnson & Johnson\",\"asset\":\"JNJ-5120\",\"molecule\":null,\"developmentCode\":\"JNJ-5120\",\"brand\":\"JNJ-5120\",\"aliases\":[],\"indication\":\"Major Depressive Disorder\",\"controlledIndication\":null,\"indicationAliases\":[],\"treatmentSettingLine\":[],\"biomarkerPatientSegment\":null,\"portfolioStatus\":null,\"phase\":\"Phase 2\"},{\"recordId\":\"recDr9b7u3twKEgyp\",\"company\":\"Johnson & Johnson\",\"asset\":\"TREMFYA\",\"molecule\":\"guselkumab\",\"developmentCode\":null,\"brand\":\"TREMFYA\",\"aliases\":[],\"indication\":\"Plaque psoriasis\",\"controlledIndication\":null,\"indicationAliases\":[],\"treatmentSettingLine\":[],\"biomarkerPatientSegment\":null,\"portfolioStatus\":null,\"phase\":\"Approved\"},{\"recordId\":\"recEefzPco9ps6pBX\",\"company\":\"Johnson & Johnson\",\"asset\":\"STELARA\",\"molecule\":\"ustekinumab\",\"developmentCode\":null,\"brand\":\"STELARA\",\"aliases\":[],\"indication\":\"Active psoriatic arthritis\",\"controlledIndication\":null,\"indicationAliases\":[],\"treatmentSettingLine\":[],\"biomarkerPatientSegment\":null,\"portfolioStatus\":null,\"phase\":\"Approved\"},{\"recordId\":\"recEemcecWhZTeiBF\",\"company\":\"Johnson & Johnson\",\"asset\":\"OPSYNVI\",\"molecule\":\"macitentan + tadalafil\",\"developmentCode\":null,\"brand\":\"OPSYNVI\",\"aliases\":[],\"indication\":\"Pulmonary arterial hypertension\",\"controlledIndication\":null,\"indicationAliases\":[],\"treatmentSettingLine\":[],\"biomarkerPatientSegment\":null,\"portfolioStatus\":null,\"phase\":\"Approved\"},{\"recordId\":\"recGO45oO9bd3IW6p\",\"company\":\"Johnson & Johnson\",\"asset\":\"JNJ-5223\",\"molecule\":null,\"developmentCode\":\"JNJ-5223\",\"brand\":\"JNJ-5223\",\"aliases\":[],\"indication\":\"Psoriatic Arthritis\",\"controlledIndication\":null,\"indicationAliases\":[],\"treatmentSettingLine\":[],\"biomarkerPatientSegment\":null,\"portfolioStatus\":null,\"phase\":\"Phase 2\"},{\"recordId\":\"recH8TUoboHXCNFVc\",\"company\":\"Johnson & Johnson\",\"asset\":\"ITI-1284\",\"molecule\":null,\"developmentCode\":\"ITI-1284\",\"brand\":\"ITI-1284\",\"aliases\":[],\"indication\":\"Generalized Anxiety Disorder / Alzheimer's Disease\",\"controlledIndication\":null,\"indicationAliases\":[],\"treatmentSettingLine\":[],\"biomarkerPatientSegment\":null,\"portfolioStatus\":null,\"phase\":\"Phase 2\"},{\"recordId\":\"recHNvWw0RVF9gY7v\",\"company\":\"Johnson & Johnson\",\"asset\":\"ERLEADA\",\"molecule\":\"apalutamide\",\"developmentCode\":null,\"brand\":\"ERLEADA\",\"aliases\":[],\"indication\":\"High-risk localized prostate cancer\",\"controlledIndication\":null,\"indicationAliases\":[],\"treatmentSettingLine\":[],\"biomarkerPatientSegment\":\"High-risk\",\"portfolioStatus\":null,\"phase\":\"Phase 3\"},{\"recordId\":\"recIEJBqlGAutV9vO\",\"company\":\"Johnson & Johnson\",\"asset\":\"Milvexian\",\"molecule\":\"milvexian\",\"developmentCode\":null,\"brand\":\"Milvexian\",\"aliases\":[],\"indication\":\"Secondary prevention after acute ischemic stroke or high-risk TIA\",\"controlledIndication\":null,\"indicationAliases\":[],\"treatmentSettingLine\":[],\"biomarkerPatientSegment\":null,\"portfolioStatus\":null,\"phase\":\"Phase 3\"},{\"recordId\":\"recIXUlkVfhJ6Kz6K\",\"company\":\"Johnson & Johnson\",\"asset\":\"Milvexian\",\"molecule\":\"milvexian\",\"developmentCode\":null,\"brand\":\"Milvexian\",\"aliases\":[],\"indication\":\"Atrial fibrillation\",\"controlledIndication\":null,\"indicationAliases\":[],\"treatmentSettingLine\":[],\"biomarkerPatientSegment\":null,\"portfolioStatus\":null,\"phase\":\"Phase 3\"},{\"recordId\":\"recJSz4g402EtQNoY\",\"company\":\"Johnson & Johnson\",\"asset\":\"AKEEGA\",\"molecule\":\"niraparib + abiraterone acetate\",\"developmentCode\":null,\"brand\":\"AKEEGA\",\"aliases\":[],\"indication\":\"BRCA1/2-mutated metastatic hormone-sensitive prostate cancer\",\"controlledIndication\":null,\"indicationAliases\":[],\"treatmentSettingLine\":[],\"biomarkerPatientSegment\":\"BRCA1/2-mutated\",\"portfolioStatus\":null,\"phase\":\"Approved\"},{\"recordId\":\"recLVleo7ydRtcIOi\",\"company\":\"Johnson & Johnson\",\"asset\":\"INLEXZO\",\"molecule\":\"gemcitabine\",\"developmentCode\":null,\"brand\":\"INLEXZO\",\"aliases\":[],\"indication\":\"BCG-unresponsive non-muscle invasive bladder cancer with CIS\",\"controlledIndication\":null,\"indicationAliases\":[],\"treatmentSettingLine\":[],\"biomarkerPatientSegment\":null,\"portfolioStatus\":null,\"phase\":\"Approved\"},{\"recordId\":\"recM3HBI8fpztBTGa\",\"company\":\"Johnson & Johnson\",\"asset\":\"TREMFYA\",\"molecule\":\"guselkumab\",\"developmentCode\":null,\"brand\":\"TREMFYA\",\"aliases\":[],\"indication\":\"Crohn's disease\",\"controlledIndication\":null,\"indicationAliases\":[],\"treatmentSettingLine\":[],\"biomarkerPatientSegment\":null,\"portfolioStatus\":null,\"phase\":\"Approved\"},{\"recordId\":\"recPldTYF1tVXbGp3\",\"company\":\"Johnson & Johnson\",\"asset\":\"IMAAVY\",\"molecule\":\"nipocalimab\",\"developmentCode\":null,\"brand\":\"IMAAVY\",\"aliases\":[],\"indication\":\"Systemic lupus erythematosus\",\"controlledIndication\":null,\"indicationAliases\":[],\"treatmentSettingLine\":[],\"biomarkerPatientSegment\":null,\"portfolioStatus\":null,\"phase\":\"Phase 3\"},{\"recordId\":\"recTL7Y25peRmYu9l\",\"company\":\"Johnson & Johnson\",\"asset\":\"TREMFYA\",\"molecule\":\"guselkumab\",\"developmentCode\":null,\"brand\":\"TREMFYA\",\"aliases\":[],\"indication\":\"Plaque psoriasis and psoriatic arthritis\",\"controlledIndication\":null,\"indicationAliases\":[],\"treatmentSettingLine\":[],\"biomarkerPatientSegment\":null,\"portfolioStatus\":null,\"phase\":\"Approved\"},{\"recordId\":\"recU6m3My0s7NAGJn\",\"company\":\"Johnson & Johnson\",\"asset\":\"ICOTYDE\",\"molecule\":\"icotrokinra\",\"developmentCode\":null,\"brand\":\"ICOTYDE\",\"aliases\":[],\"indication\":\"Moderate-to-severe plaque psoriasis\",\"controlledIndication\":null,\"indicationAliases\":[],\"treatmentSettingLine\":[],\"biomarkerPatientSegment\":null,\"portfolioStatus\":null,\"phase\":\"Approved\"},{\"recordId\":\"recWLJiVIlAstXosK\",\"company\":\"Johnson & Johnson\",\"asset\":\"JNJ-4804\",\"molecule\":\"JNJ-78934804\",\"developmentCode\":null,\"brand\":\"JNJ-4804\",\"aliases\":[],\"indication\":\"Ulcerative colitis\",\"controlledIndication\":null,\"indicationAliases\":[],\"treatmentSettingLine\":[],\"biomarkerPatientSegment\":null,\"portfolioStatus\":null,\"phase\":\"Phase 2\"},{\"recordId\":\"recWXKhEeHs61GOxY\",\"company\":\"Johnson & Johnson\",\"asset\":\"JNJ-2056\",\"molecule\":null,\"developmentCode\":\"JNJ-2056\",\"brand\":\"JNJ-2056\",\"aliases\":[],\"indication\":\"Alzheimer's Disease\",\"controlledIndication\":null,\"indicationAliases\":[],\"treatmentSettingLine\":[],\"biomarkerPatientSegment\":null,\"portfolioStatus\":null,\"phase\":\"Phase 2\"},{\"recordId\":\"recYPXCSQ9U9fnTTg\",\"company\":\"Johnson & Johnson\",\"asset\":\"TECVAYLI\",\"molecule\":\"teclistamab\",\"developmentCode\":null,\"brand\":\"TECVAYLI\",\"aliases\":[],\"indication\":\"Late-line relapsed/refractory multiple myeloma\",\"controlledIndication\":null,\"indicationAliases\":[],\"treatmentSettingLine\":[],\"biomarkerPatientSegment\":null,\"portfolioStatus\":null,\"phase\":\"Approved\"},{\"recordId\":\"recYSY2IgHYIWTVWO\",\"company\":\"Johnson & Johnson\",\"asset\":\"CAPLYTA\",\"molecule\":\"lumateperone\",\"developmentCode\":null,\"brand\":\"CAPLYTA\",\"aliases\":[],\"indication\":\"Schizophrenia in adults\",\"controlledIndication\":null,\"indicationAliases\":[],\"treatmentSettingLine\":[],\"biomarkerPatientSegment\":null,\"portfolioStatus\":null,\"phase\":\"Approved\"},{\"recordId\":\"recZXqOeAp9rQ80d5\",\"company\":\"Johnson & Johnson\",\"asset\":\"RYBREVANT + LAZCLUZE\",\"molecule\":\"amivantamab + lazertinib\",\"developmentCode\":null,\"brand\":\"RYBREVANT + LAZCLUZE\",\"aliases\":[],\"indication\":\"First-line EGFR exon 19 deletion or L858R-mutated advanced NSCLC\",\"controlledIndication\":null,\"indicationAliases\":[],\"treatmentSettingLine\":[],\"biomarkerPatientSegment\":null,\"portfolioStatus\":null,\"phase\":\"Approved\"},{\"recordId\":\"recaMTYJImgNhhqHZ\",\"company\":\"Johnson & Johnson\",\"asset\":\"CARVYKTI\",\"molecule\":\"ciltacabtagene autoleucel\",\"developmentCode\":null,\"brand\":\"CARVYKTI\",\"aliases\":[],\"indication\":\"Relapsed/refractory multiple myeloma\",\"controlledIndication\":null,\"indicationAliases\":[],\"treatmentSettingLine\":[],\"biomarkerPatientSegment\":null,\"portfolioStatus\":null,\"phase\":\"Approved\"},{\"recordId\":\"recamPkCfup3BoTlc\",\"company\":\"Johnson & Johnson\",\"asset\":\"CAPLYTA\",\"molecule\":\"lumateperone\",\"developmentCode\":null,\"brand\":\"CAPLYTA\",\"aliases\":[],\"indication\":\"Schizophrenia and bipolar depression\",\"controlledIndication\":null,\"indicationAliases\":[],\"treatmentSettingLine\":[],\"biomarkerPatientSegment\":null,\"portfolioStatus\":null,\"phase\":\"Approved\"},{\"recordId\":\"recbEh2joCl72p9ay\",\"company\":\"Johnson & Johnson\",\"asset\":\"TREMFYA\",\"molecule\":\"guselkumab\",\"developmentCode\":null,\"brand\":\"TREMFYA\",\"aliases\":[],\"indication\":\"Ulcerative colitis\",\"controlledIndication\":null,\"indicationAliases\":[],\"treatmentSettingLine\":[],\"biomarkerPatientSegment\":null,\"portfolioStatus\":null,\"phase\":\"Approved\"},{\"recordId\":\"reccRSOvThVyHmbjf\",\"company\":\"Johnson & Johnson\",\"asset\":\"STELARA\",\"molecule\":\"ustekinumab\",\"developmentCode\":null,\"brand\":\"STELARA\",\"aliases\":[],\"indication\":\"Psoriasis, psoriatic arthritis, Crohn's disease and ulcerative colitis\",\"controlledIndication\":null,\"indicationAliases\":[],\"treatmentSettingLine\":[],\"biomarkerPatientSegment\":null,\"portfolioStatus\":null,\"phase\":\"Approved\"},{\"recordId\":\"receuMqC7RVLZ7jOJ\",\"company\":\"Johnson & Johnson\",\"asset\":\"TALVEY\",\"molecule\":\"talquetamab\",\"developmentCode\":null,\"brand\":\"TALVEY\",\"aliases\":[],\"indication\":\"Relapsed/refractory multiple myeloma\",\"controlledIndication\":null,\"indicationAliases\":[],\"treatmentSettingLine\":[],\"biomarkerPatientSegment\":null,\"portfolioStatus\":null,\"phase\":\"Approved\"},{\"recordId\":\"recfz2TBf3l215nnO\",\"company\":\"Johnson & Johnson\",\"asset\":\"STELARA\",\"molecule\":\"ustekinumab\",\"developmentCode\":null,\"brand\":\"STELARA\",\"aliases\":[],\"indication\":\"Plaque psoriasis\",\"controlledIndication\":null,\"indicationAliases\":[],\"treatmentSettingLine\":[],\"biomarkerPatientSegment\":null,\"portfolioStatus\":null,\"phase\":\"Approved\"},{\"recordId\":\"rechLGWBETpve95DF\",\"company\":\"Johnson & Johnson\",\"asset\":\"CAPLYTA\",\"molecule\":\"lumateperone\",\"developmentCode\":null,\"brand\":\"CAPLYTA\",\"aliases\":[],\"indication\":\"Major depressive disorder, adjunctive therapy\",\"controlledIndication\":null,\"indicationAliases\":[],\"treatmentSettingLine\":[],\"biomarkerPatientSegment\":null,\"portfolioStatus\":null,\"phase\":\"Approved\"},{\"recordId\":\"reckO9FfdSYJjCKGW\",\"company\":\"Johnson & Johnson\",\"asset\":\"JNJ-0683 (ARX788)\",\"molecule\":null,\"developmentCode\":\"JNJ-0683\",\"brand\":\"JNJ-0683 (ARX788)\",\"aliases\":[],\"indication\":\"Breast Cancer\",\"controlledIndication\":null,\"indicationAliases\":[],\"treatmentSettingLine\":[],\"biomarkerPatientSegment\":null,\"portfolioStatus\":null,\"phase\":\"Phase 2\"},{\"recordId\":\"recmkhxG14V1mlrQT\",\"company\":\"Johnson & Johnson\",\"asset\":\"pasritamig\",\"molecule\":null,\"developmentCode\":null,\"brand\":\"pasritamig\",\"aliases\":[],\"indication\":\"Prostate Cancer\",\"controlledIndication\":null,\"indicationAliases\":[],\"treatmentSettingLine\":[],\"biomarkerPatientSegment\":null,\"portfolioStatus\":null,\"phase\":\"Phase 3\"},{\"recordId\":\"recp1LXOBsLTmTK6o\",\"company\":\"Johnson & Johnson\",\"asset\":\"JNJ-7528\",\"molecule\":null,\"developmentCode\":\"JNJ-7528\",\"brand\":\"JNJ-7528\",\"aliases\":[],\"indication\":\"Atopic Dermatitis\",\"controlledIndication\":null,\"indicationAliases\":[],\"treatmentSettingLine\":[],\"biomarkerPatientSegment\":null,\"portfolioStatus\":null,\"phase\":\"Phase 2\"},{\"recordId\":\"recp5I1tLzOR9WC8s\",\"company\":\"Johnson & Johnson\",\"asset\":\"seltorexant\",\"molecule\":null,\"developmentCode\":null,\"brand\":\"seltorexant\",\"aliases\":[],\"indication\":\"Major Depressive Disorder\",\"controlledIndication\":null,\"indicationAliases\":[],\"treatmentSettingLine\":[],\"biomarkerPatientSegment\":null,\"portfolioStatus\":null,\"phase\":\"Phase 3\"},{\"recordId\":\"recpSssRnjBh7FLqi\",\"company\":\"Johnson & Johnson\",\"asset\":\"ERLEADA\",\"molecule\":\"apalutamide\",\"developmentCode\":null,\"brand\":\"ERLEADA\",\"aliases\":[],\"indication\":\"Metastatic castration-sensitive prostate cancer\",\"controlledIndication\":null,\"indicationAliases\":[],\"treatmentSettingLine\":[],\"biomarkerPatientSegment\":null,\"portfolioStatus\":null,\"phase\":\"Approved\"},{\"recordId\":\"recpjhrD2KGAmUuCN\",\"company\":\"Johnson & Johnson\",\"asset\":\"STELARA\",\"molecule\":\"ustekinumab\",\"developmentCode\":null,\"brand\":\"STELARA\",\"aliases\":[],\"indication\":\"Moderately to severely active Crohn's disease\",\"controlledIndication\":null,\"indicationAliases\":[],\"treatmentSettingLine\":[],\"biomarkerPatientSegment\":null,\"portfolioStatus\":null,\"phase\":\"Approved\"},{\"recordId\":\"recq0pcIoHOFsZnod\",\"company\":\"Johnson & Johnson\",\"asset\":\"Milvexian\",\"molecule\":\"milvexian\",\"developmentCode\":null,\"brand\":\"Milvexian\",\"aliases\":[],\"indication\":\"Acute coronary syndrome\",\"controlledIndication\":null,\"indicationAliases\":[],\"treatmentSettingLine\":[],\"biomarkerPatientSegment\":null,\"portfolioStatus\":null,\"phase\":\"Phase 3\"},{\"recordId\":\"recr25BrRVoEjwemB\",\"company\":\"Johnson & Johnson\",\"asset\":\"STELARA\",\"molecule\":\"ustekinumab\",\"developmentCode\":null,\"brand\":\"STELARA\",\"aliases\":[],\"indication\":\"Moderately to severely active ulcerative colitis\",\"controlledIndication\":null,\"indicationAliases\":[],\"treatmentSettingLine\":[],\"biomarkerPatientSegment\":null,\"portfolioStatus\":null,\"phase\":\"Approved\"},{\"recordId\":\"recsCvgEs5L4IibXW\",\"company\":\"Johnson & Johnson\",\"asset\":\"RYBREVANT FASPRO\",\"molecule\":\"amivantamab + hyaluronidase\",\"developmentCode\":null,\"brand\":\"RYBREVANT FASPRO\",\"aliases\":[],\"indication\":\"Recurrent/metastatic head and neck squamous cell carcinoma after immunotherapy and chemotherapy\",\"controlledIndication\":null,\"indicationAliases\":[],\"treatmentSettingLine\":[],\"biomarkerPatientSegment\":null,\"portfolioStatus\":null,\"phase\":\"Filed / Registration\"},{\"recordId\":\"recvMD777TpUDnGwe\",\"company\":\"Johnson & Johnson\",\"asset\":\"JNJ-5939\",\"molecule\":null,\"developmentCode\":\"JNJ-5939\",\"brand\":\"JNJ-5939\",\"aliases\":[],\"indication\":\"Atopic Dermatitis\",\"controlledIndication\":null,\"indicationAliases\":[],\"treatmentSettingLine\":[],\"biomarkerPatientSegment\":null,\"portfolioStatus\":null,\"phase\":\"Phase 2\"},{\"recordId\":\"recx1bGXmvJj88TWX\",\"company\":\"Johnson & Johnson\",\"asset\":\"JNJ-4804\",\"molecule\":\"JNJ-78934804\",\"developmentCode\":null,\"brand\":\"JNJ-4804\",\"aliases\":[],\"indication\":\"Crohn's disease\",\"controlledIndication\":null,\"indicationAliases\":[],\"treatmentSettingLine\":[],\"biomarkerPatientSegment\":null,\"portfolioStatus\":null,\"phase\":\"Phase 2\"},{\"recordId\":\"reczmHhoSBgSJpAcR\",\"company\":\"Johnson & Johnson\",\"asset\":\"JNJ-1900 (NBTXR3)\",\"molecule\":null,\"developmentCode\":\"JNJ-1900\",\"brand\":\"JNJ-1900 (NBTXR3)\",\"aliases\":[],\"indication\":\"Head and Neck Squamous Cell Carcinoma / Non-Small Cell Lung Cancer\",\"controlledIndication\":null,\"indicationAliases\":[],\"treatmentSettingLine\":[],\"biomarkerPatientSegment\":null,\"portfolioStatus\":null,\"phase\":\"Phase 3\"}]")


def _source_identity(row: Dict[str, Any]) -> Dict[str, str]:
    """Add deterministic identity hints without rewriting source evidence.

    Several public pipeline grids use the generic display pattern
    BRAND (molecule). Treat the prefix as a brand/asset identity hint and the
    parenthetical text as a molecule/alias hint for reconciliation only.
    """
    asset = str(row.get("asset") or "").strip()
    brand = str(row.get("brand") or "").strip()
    molecule = str(row.get("molecule") or "").strip()
    m = re.fullmatch(r"\s*(.+?)\s*\(([^()]*)\)\s*", asset)
    if m:
        prefix = m.group(1).strip()
        inner = m.group(2).strip()
        if prefix and not brand:
            brand = prefix
        if inner and not molecule:
            molecule = inner
    return {"asset": asset, "brand": brand, "molecule": molecule}


def _to_source_row(row: Dict[str, Any]) -> comparator.DiscoverySourceRow:
    identity = _source_identity(row)
    phase = str(row.get("phase") or "")
    return comparator.DiscoverySourceRow(
        company="Johnson & Johnson",
        sourceFamily=row.get("sourceFamily") or "Company Pipeline",
        sourceRecordId=row.get("sourceRecordId"),
        sourceUrl=row.get("sourceUrl"),
        sourceWatchRecordId=SOURCE_WATCH_RECORD_ID,
        asset=identity["asset"],
        molecule=identity["molecule"],
        developmentCode=row.get("developmentCode"),
        brand=identity["brand"],
        indication=row.get("indication"),
        phase=phase,
        programStatus=row.get("programStatus") or "Active",
        sponsorOwner="Johnson & Johnson",
        partners=row.get("partners") or [],
        ownershipResolved=True,
        strategicPhase1=False,
        importantLabelExpansion=False,
        marketedStrategicRx=False,
        genericCommodity=False,
    )


async def run_canary() -> Dict[str, Any]:
    source = await gp._extract_generic_pipeline(
        company="Johnson & Johnson",
        source_url=SOURCE_URL,
        timeout_seconds=35.0,
    )
    request = comparator.DiscoveryCompareRequest(
        company="Johnson & Johnson",
        sourceRows=[_to_source_row(row) for row in source.rows],
        portfolioRows=[comparator.PortfolioSnapshotRow(**row) for row in PORTFOLIO_SNAPSHOT],
        companyAliases=["Johnson & Johnson Innovative Medicine", "Janssen"],
        batchRunId=f"JNJ-CANARY-{SNAPSHOT_AS_OF}",
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
    unresolved = [
        c for c in in_scope
        if c.get("classification") not in {"MATCHED", "EXCLUDED BY RULE"}
    ]

    ready = bool(
        source.readyForDiscovery
        and source.rowCount == 97
        and int(source.diagnostics.get("declaredRowCount") or 0) == 97
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
        "version": "JNJ_RECONCILIATION_CANARY_V1",
        "readyForBindingValidation": ready,
        "sourceReadyForDiscovery": source.readyForDiscovery,
        "sourceRows": source.rowCount,
        "sourceDeclaredRows": source.diagnostics.get("declaredRowCount"),
        "sourceSelectedMethod": source.diagnostics.get("selectedMethod"),
        "retrievalMode": source.diagnostics.get("retrievalMode"),
        "portfolioSnapshotRows": len(PORTFOLIO_SNAPSHOT),
        "classifications": dict(classifications),
        "commercialDecisions": dict(decisions),
        "matchMethods": dict(methods),
        "matchConfidence": dict(confidence),
        "fieldDeltaCounts": dict(field_deltas),
        "inScopeRows": len(in_scope),
        "unresolvedInScopeCount": len(unresolved),
        "unresolvedInScopeSample": [compact(c) for c in unresolved[:30]],
        "sourceIssues": source.issues,
        "masterWrites": 0,
    }


if __name__ == "__main__":
    print("JNJ_RECONCILIATION_CANARY " + json.dumps(asyncio.run(run_canary()), ensure_ascii=False), flush=True)
