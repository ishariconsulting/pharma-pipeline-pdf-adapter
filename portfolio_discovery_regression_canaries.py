"""Import-time READ-ONLY regression canaries for Portfolio Discovery V1.3.

These fixtures are deliberately frozen test snapshots. They validate comparator
behaviour only; they never write Airtable, RPC, MRS, queues, or automations.

Pfizer oracle:
- 58 official Aug-4-2026 Phase 2 / Phase 3 / Registration programme rows.
- Every row must reconcile to an existing Portfolio representation in the
  frozen regression fixture.
- VLA15 / PF-07307405 must remain MATCHED while surfacing a phase delta.

Vertex oracle:
- VX-993 -> NEW ASSET
- VX-407 -> NEW ASSET
- atumelnant / Cushing's syndrome -> NEW INDICATION
- atumelnant / CAH -> MATCHED
"""

from typing import Any, Dict, List, Optional

import portfolio_discovery_extension_v13  # noqa: F401 - installs V1.3 patches
import portfolio_discovery_extension_v11 as base


CANARY_VERSION = "V1.0 PORTFOLIO DISCOVERY REGRESSION CANARIES"


def _source(
    company: str,
    rid: str,
    asset: str,
    indication: str,
    phase: str,
    *,
    development_code: str = "",
    brand: str = "",
    molecule: str = "",
    controlled: str = "",
) -> base.DiscoverySourceRow:
    return base.DiscoverySourceRow(
        company=company,
        sourceFamily="Company Pipeline",
        sourceRecordId=rid,
        asset=asset,
        brand=brand or None,
        molecule=molecule or None,
        developmentCode=development_code or None,
        indication=indication,
        controlledIndicationCandidate=controlled or None,
        phase=phase,
        ownershipResolved=True,
    )


def _portfolio(
    company: str,
    rid: str,
    asset: str,
    indication: str,
    phase: str,
    *,
    development_code: str = "",
    brand: str = "",
    molecule: str = "",
    controlled: str = "",
    aliases: Optional[List[str]] = None,
) -> base.PortfolioSnapshotRow:
    return base.PortfolioSnapshotRow(
        recordId=rid,
        company=company,
        asset=asset,
        brand=brand or None,
        molecule=molecule or None,
        developmentCode=development_code or None,
        aliases=aliases or [],
        indication=indication,
        controlledIndication=controlled or None,
        phase=phase,
    )


# Frozen Pfizer default-commercial-scope source oracle: 58 official rows.
PFIZER_SOURCE: List[base.DiscoverySourceRow] = [
    # Inflammation & Immunology (13)
    _source("Pfizer", "PFZ-001", "LITFULO", "Nonsegmental Vitiligo", "Phase 3", molecule="ritlecitinib"),
    _source("Pfizer", "PFZ-002", "Dazukibart", "Dermatomyositis and Polymyositis", "Phase 3", development_code="PF-06823859", molecule="dazukibart"),
    _source("Pfizer", "PFZ-003", "Osivelotor", "Sickle Cell Disease", "Phase 3", development_code="PF-07940367", molecule="osivelotor"),
    _source("Pfizer", "PFZ-004", "LITFULO", "Chronic Spontaneous Urticaria", "Phase 2", molecule="ritlecitinib"),
    _source("Pfizer", "PFZ-005", "LITFULO", "Hidradenitis Suppurativa", "Phase 2", molecule="ritlecitinib"),
    _source("Pfizer", "PFZ-006", "PF-06835375", "Immune Thrombocytopenic Purpura", "Phase 2", development_code="PF-06835375"),
    _source("Pfizer", "PFZ-007", "Tilrekimig", "Atopic Dermatitis", "Phase 2", development_code="PF-07275315", molecule="tilrekimig"),
    _source("Pfizer", "PFZ-008", "Tilrekimig", "Asthma", "Phase 2", development_code="PF-07275315", molecule="tilrekimig"),
    _source("Pfizer", "PFZ-009", "Tilrekimig", "Chronic Obstructive Pulmonary Disease", "Phase 2", development_code="PF-07275315", molecule="tilrekimig"),
    _source("Pfizer", "PFZ-010", "Ompekimig", "Atopic Dermatitis", "Phase 2", molecule="ompekimig"),
    _source("Pfizer", "PFZ-011", "PF-07868489", "Pulmonary Arterial Hypertension", "Phase 2", development_code="PF-07868489"),
    _source("Pfizer", "PFZ-012", "PF-07261271", "Ulcerative Colitis", "Phase 2", development_code="PF-07261271"),
    _source("Pfizer", "PFZ-013", "PF-08049820", "Atopic Dermatitis", "Phase 2", development_code="PF-08049820"),

    # Internal Medicine (7)
    _source("Pfizer", "PFZ-014", "Ibuzatrelvir", "COVID-19 Infection", "Phase 3", development_code="PF-07817883", molecule="ibuzatrelvir"),
    _source("Pfizer", "PFZ-015", "NURTEC", "Menstrually-Related Migraine", "Phase 3", molecule="rimegepant"),
    _source("Pfizer", "PFZ-016", "Berobenatide", "Chronic Weight Management", "Phase 3", development_code="PF-08653944", molecule="berobenatide"),
    _source("Pfizer", "PFZ-017", "Ponsegromab", "Cachexia in Cancer", "Phase 2", development_code="PF-06946860", molecule="ponsegromab"),
    _source("Pfizer", "PFZ-018", "PF-07328948", "Heart Failure", "Phase 2", development_code="PF-07328948"),
    _source("Pfizer", "PFZ-019", "Berobenatide + MET-233i", "Chronic Weight Management", "Phase 2", development_code="PF-08653944", molecule="MET-097i + MET-233i"),
    _source("Pfizer", "PFZ-020", "MET-233i", "Chronic Weight Management", "Phase 2", development_code="PF-08653945", molecule="MET-233i"),

    # Oncology registration (2)
    _source("Pfizer", "PFZ-021", "TUKYSA", "1L HER2+ Metastatic Breast Cancer Maintenance (HER2CLIMB-05)", "Registration", molecule="tucatinib"),
    _source(
        "Pfizer", "PFZ-022", "TALZENNA (talazoparib)",
        "Combo w/ XTANDI (enzalutamide) for DNA Damage Repair (DDR)-Deficient Metastatic Castration Sensitive Prostate Cancer (TALAPRO-3)",
        "Registration", brand="TALZENNA", molecule="talazoparib",
    ),

    # Oncology Phase 3 (20)
    _source("Pfizer", "PFZ-023", "Sasanlimab", "High-Risk Non-Muscle-Invasive Bladder Cancer (CREST)", "Phase 3", development_code="PF-06801591", molecule="sasanlimab"),
    _source("Pfizer", "PFZ-024", "ELREXFIO", "Relapsed/Refractory Multiple Myeloma, Double-Class Exposed (MM-5)", "Phase 3", molecule="elranatamab"),
    _source("Pfizer", "PFZ-025", "ELREXFIO", "Newly Diagnosed Multiple Myeloma after Autologous Stem-Cell Transplantation - Maintenance (MM-7)", "Phase 3", molecule="elranatamab"),
    _source("Pfizer", "PFZ-026", "ELREXFIO", "Newly Diagnosed Multiple Myeloma, Transplant-Ineligible (MM-6)", "Phase 3", molecule="elranatamab"),
    _source("Pfizer", "PFZ-027", "ELREXFIO", "2L+ post-CD38 Relapsed Refractory Multiple Myeloma (MM-32)", "Phase 3", molecule="elranatamab"),
    _source("Pfizer", "PFZ-028", "Sigvotatug Vedotin", "2L+ Metastatic Non-Small Cell Lung Cancer (mNSCLC) (Be6A LUNG-01)", "Phase 3", development_code="PF-08046047", molecule="sigvotatug vedotin"),
    _source("Pfizer", "PFZ-029", "Sigvotatug Vedotin", "1L Metastatic Non-Small Cell Lung Cancer, TPS-high (Be6A LUNG-02)", "Phase 3", development_code="PF-08046047", molecule="sigvotatug vedotin"),
    _source("Pfizer", "PFZ-030", "TUKYSA", "HER2+ Adjuvant Breast Cancer (CompassHER2 RD)", "Phase 3", molecule="tucatinib"),
    _source("Pfizer", "PFZ-031", "TUKYSA", "1L HER2+ Metastatic Colorectal Cancer (MOUNTAINEER-03)", "Phase 3", molecule="tucatinib"),
    _source("Pfizer", "PFZ-032", "Disitamab Vedotin", "1L HER2-expressing Metastatic Urothelial Cancer (DV-001)", "Phase 3", molecule="disitamab vedotin"),
    _source("Pfizer", "PFZ-033", "Mevrometostat + Enzalutamide", "1/2L Metastatic Castration Resistant Prostate Cancer post-Abiraterone (MEVPRO-1)", "Phase 3", development_code="PF-06821497", molecule="mevrometostat"),
    _source("Pfizer", "PFZ-034", "Mevrometostat + Enzalutamide", "1L Metastatic Castration Resistant Prostate Cancer NHT-naive (MEVPRO-2)", "Phase 3", development_code="PF-06821497", molecule="mevrometostat"),
    _source("Pfizer", "PFZ-035", "Mevrometostat + Enzalutamide", "1L Metastatic Castration-Sensitive Prostate Cancer NHT-naive (MEVPRO-3)", "Phase 3", development_code="PF-06821497", molecule="mevrometostat"),
    _source("Pfizer", "PFZ-036", "Atirmociclib", "1L HR+/HER2- Metastatic Breast Cancer (FourLight-3)", "Phase 3", development_code="PF-07220060", molecule="atirmociclib"),
    _source("Pfizer", "PFZ-037", "Prifetrastat", "2L/3L HR+/HER2- Metastatic Breast Cancer (KATSIS-1)", "Phase 3", development_code="PF-07248144", molecule="prifetrastat"),
    _source("Pfizer", "PFZ-038", "Fetrastobart Vedotin", "2L+ Non-Small Cell Lung Cancer (PADL1NK-005)", "Phase 3", development_code="PF-08046054", molecule="fetrastobart vedotin"),
    _source("Pfizer", "PFZ-039", "PF-08634404", "1L Metastatic Colorectal Cancer (Symbiotic-GI-03)", "Phase 3", development_code="PF-08634404"),
    _source("Pfizer", "PFZ-040", "PF-08634404", "1L Non-Small Cell Lung Cancer (squamous) (Symbiotic-Lung-01)", "Phase 3", development_code="PF-08634404"),
    _source("Pfizer", "PFZ-041", "PF-08634404", "1L Non-Small Cell Lung Cancer (non-squamous) (Symbiotic-Lung-01)", "Phase 3", development_code="PF-08634404"),
    _source("Pfizer", "PFZ-042", "PADCEV", "Bladder-Sparing Muscle-Invasive Bladder Cancer (EV-309)", "Phase 3", molecule="enfortumab vedotin + pembrolizumab"),

    # Oncology Phase 2 (9)
    _source("Pfizer", "PFZ-043", "PADCEV", "Locally Advanced or Metastatic Solid Tumors (EV-202)", "Phase 2", molecule="enfortumab vedotin + pembrolizumab"),
    _source("Pfizer", "PFZ-044", "TIVDAK", "Advanced Solid Tumors (TV-207)", "Phase 2", molecule="tisotumab vedotin"),
    _source("Pfizer", "PFZ-045", "TUKYSA", "Locally Advanced or Metastatic Solid Tumors with HER2 Alterations", "Phase 2", molecule="tucatinib"),
    _source("Pfizer", "PFZ-046", "Disitamab Vedotin", "2L+ Metastatic Urothelial Cancer with HER2 Expression", "Phase 2", development_code="PF-08046051", molecule="disitamab vedotin"),
    _source("Pfizer", "PFZ-047", "Atirmociclib", "2L HR+/HER2- Metastatic Breast Cancer (FourLight-1)", "Phase 2", development_code="PF-07220060", molecule="atirmociclib"),
    _source("Pfizer", "PFZ-048", "Atirmociclib", "Early Breast Cancer", "Phase 2", development_code="PF-07220060", molecule="atirmociclib"),
    _source("Pfizer", "PFZ-049", "PF-08634404", "1L Small Cell Lung Cancer (Symbiotic-Lung-04)", "Phase 2", development_code="PF-08634404"),
    _source("Pfizer", "PFZ-050", "PF-08634404", "1L Gastroesophageal Cancer (Symbiotic-GI-16)", "Phase 2", development_code="PF-08634404"),
    _source("Pfizer", "PFZ-051", "PF-08634404", "Transformed Small Cell Lung Cancer (Symbiotic-Lung-14)", "Phase 2", development_code="PF-08634404"),

    # Vaccines (7)
    _source("Pfizer", "PFZ-052", "VLA15", "Prevention of Lyme Disease", "Phase 3", development_code="PF-07307405"),
    _source("Pfizer", "PFZ-053", "COVID-19 Vaccine", "COVID-19 Infection (in collaboration with BioNTech) (U.S. - 6 months through 11 years of age)", "Phase 3"),
    _source("Pfizer", "PFZ-054", "PF-06760805", "Invasive Group B Streptococcus Infection (maternal)", "Phase 3", development_code="PF-06760805"),
    _source("Pfizer", "PFZ-055", "PF-07831694", "Clostridioides difficile (C. difficile) - updated formulation", "Phase 3", development_code="PF-07831694"),
    _source("Pfizer", "PFZ-056", "PF-07872412", "Pneumococcal Infection - Pediatrics", "Phase 3", development_code="PF-07872412"),
    _source("Pfizer", "PFZ-057", "PF-07252220", "Influenza (adults)", "Phase 2", development_code="PF-07252220"),
    _source("Pfizer", "PFZ-058", "PF-07926307", "Combination COVID-19 & Influenza (in collaboration with BioNTech)", "Phase 2", development_code="PF-07926307"),
]


# Frozen corresponding Portfolio regression fixture. Most rows intentionally keep
# exact programme wording; selected rows preserve the known normalization edges.
PFIZER_PORTFOLIO: List[base.PortfolioSnapshotRow] = []
for idx, src in enumerate(PFIZER_SOURCE, start=1):
    asset = src.asset or ""
    indication = src.indication or ""
    phase = src.phase or ""
    brand = src.brand or ""
    molecule = src.molecule or ""
    development_code = src.developmentCode or ""

    if src.sourceRecordId == "PFZ-022":
        asset = "TALZENNA + XTANDI"
        brand = "TALZENNA + XTANDI"
        molecule = "talazoparib + enzalutamide"
        indication = "DNA Damage Repair (DDR)-Deficient Metastatic Castration Sensitive Prostate Cancer (TALAPRO-3)"
        phase = "Filed / Registration"
    elif src.sourceRecordId == "PFZ-029":
        # Current Portfolio wording is more commercial/readable and omits the study code.
        indication = "First-line metastatic non-small cell lung cancer"
    elif src.sourceRecordId == "PFZ-036":
        # Explicitly exercise 1L / HR+ / HER2- deterministic normalization.
        indication = "First-line HR-positive, HER2-negative metastatic breast cancer"
    elif src.sourceRecordId == "PFZ-050":
        indication = "1L Gastroesophageal (Symbiotic-GI-16)"
    elif src.sourceRecordId == "PFZ-052":
        phase = "Filed / Registration"  # known live Portfolio delta
        indication = "Prevention of Lyme disease"

    PFIZER_PORTFOLIO.append(_portfolio(
        "Pfizer",
        f"pfz_port_{idx:03d}",
        asset,
        indication,
        phase,
        development_code=development_code,
        brand=brand,
        molecule=molecule,
    ))


VERTEX_PORTFOLIO = [
    _portfolio(
        "Vertex Pharmaceuticals",
        "vertex_atumelnant_cah",
        "atumelnant",
        "Adults with classic congenital adrenal hyperplasia due to 21-hydroxylase deficiency; Phase 3 CALM-CAH",
        "Phase 3",
        development_code="CRN04894",
        molecule="atumelnant",
        controlled="Congenital Adrenal Hyperplasia",
    ),
]

VERTEX_SOURCE = [
    _source(
        "Vertex Pharmaceuticals", "VRTX-001", "VX-993",
        "Diabetic Peripheral Neuropathy", "Phase 2",
        development_code="VX-993",
    ),
    _source(
        "Vertex Pharmaceuticals", "VRTX-002", "VX-407",
        "Autosomal Dominant Polycystic Kidney Disease", "Phase 2",
        development_code="VX-407",
    ),
    _source(
        "Vertex Pharmaceuticals", "VRTX-003", "atumelnant",
        "Cushing's Syndrome", "Phase 2",
        development_code="CRN04894", molecule="atumelnant",
        controlled="Cushing's Syndrome",
    ),
    _source(
        "Vertex Pharmaceuticals", "VRTX-004", "atumelnant",
        "Congenital Adrenal Hyperplasia", "Phase 3",
        development_code="CRN04894", molecule="atumelnant",
        controlled="Congenital Adrenal Hyperplasia",
    ),
]


def _run_pfizer() -> Dict[str, Any]:
    result = base.compare_discovery(base.DiscoveryCompareRequest(
        company="Pfizer",
        companyAliases=["Pfizer Inc."],
        sourceRows=PFIZER_SOURCE,
        portfolioRows=PFIZER_PORTFOLIO,
        batchRunId="PFIZER_V13_REGRESSION_58",
    ))
    by_id = {c["sourceRecordId"]: c for c in result.candidates}
    classifications = [c["classification"] for c in result.candidates]
    lyme = by_id["PFZ-052"]

    checks = {
        "source_count_58": result.sourceRowCount == 58,
        "all_58_matched": classifications.count("MATCHED") == 58,
        "no_new_asset": result.summary.get("NEW ASSET", 0) == 0,
        "no_new_indication": result.summary.get("NEW INDICATION", 0) == 0,
        "no_possible_duplicate": result.summary.get("POSSIBLE DUPLICATE", 0) == 0,
        "vla15_matched": lyme["classification"] == "MATCHED",
        "vla15_phase_delta": any(
            d.get("field") == "Development Phase"
            and d.get("sourceValue") == "Phase 3"
            and d.get("portfolioValue") == "Filed / Registration"
            for d in lyme.get("fieldDeltas", [])
        ),
        "read_only": result.readOnly is True,
    }
    return {
        "ok": all(checks.values()),
        "checks": checks,
        "summary": result.summary,
        "sourceRowCount": result.sourceRowCount,
        "portfolioRowCount": result.portfolioRowCount,
        "version": result.version,
    }


def _run_vertex() -> Dict[str, Any]:
    result = base.compare_discovery(base.DiscoveryCompareRequest(
        company="Vertex Pharmaceuticals",
        sourceRows=VERTEX_SOURCE,
        portfolioRows=VERTEX_PORTFOLIO,
        batchRunId="VERTEX_V13_REGRESSION",
    ))
    by_id = {c["sourceRecordId"]: c for c in result.candidates}
    checks = {
        "vx993_new_asset": by_id["VRTX-001"]["classification"] == "NEW ASSET",
        "vx407_new_asset": by_id["VRTX-002"]["classification"] == "NEW ASSET",
        "atumelnant_cushing_new_indication": by_id["VRTX-003"]["classification"] == "NEW INDICATION",
        "atumelnant_cah_matched": by_id["VRTX-004"]["classification"] == "MATCHED",
        "read_only": result.readOnly is True,
    }
    return {
        "ok": all(checks.values()),
        "checks": checks,
        "summary": result.summary,
        "version": result.version,
    }


PFIZER_REGRESSION = _run_pfizer()
VERTEX_REGRESSION = _run_vertex()
REGRESSION_RESULTS = {
    "ok": bool(PFIZER_REGRESSION["ok"] and VERTEX_REGRESSION["ok"]),
    "canaryVersion": CANARY_VERSION,
    "pfizer": PFIZER_REGRESSION,
    "vertex": VERTEX_REGRESSION,
    "guardrails": {
        "masterWrites": False,
        "portfolioMutation": False,
        "rpcMutation": False,
        "mrsMutation": False,
        "queueMutation": False,
        "existingAutomationMutation": False,
    },
}

if not REGRESSION_RESULTS["ok"]:
    raise RuntimeError(f"Portfolio Discovery regression canary failed: {REGRESSION_RESULTS}")


@base.app.get("/compare/portfolio-discovery/regression-health")
async def portfolio_discovery_regression_health() -> Dict[str, Any]:
    """Safe public health summary; exposes no Airtable/master-record payloads."""
    return REGRESSION_RESULTS
