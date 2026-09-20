"""Read-only GSK XLSX -> Portfolio Discovery baseline canary.

The Portfolio snapshot is embedded from Airtable at canary build time. This
script performs no Airtable or master-data writes.
"""

import asyncio
import json

from generic_xlsx_pipeline_extension import extract_generic_xlsx
from portfolio_discovery_extension import (
    DiscoveryCompareRequest,
    DiscoverySourceRow,
    PortfolioSnapshotRow,
    compare_discovery,
)

URL = "https://www.gsk.com/media/2qfbw2yv/2q2026-pipeline-list.xlsx"
PORTFOLIO_SNAPSHOT = json.loads(r'''[
  {
    "recordId": "rec1BgtBSnOLaCeJ8",
    "company": "GSK",
    "asset": "Jemperli",
    "molecule": "dostarlimab",
    "developmentCode": "",
    "brand": "Jemperli",
    "aliases": [
      "Tesaro asset"
    ],
    "indication": "Previously untreated stage II/III dMMR/MSI-H locally advanced rectal cancer",
    "controlledIndication": "Colorectal Cancer",
    "indicationAliases": [],
    "portfolioStatus": "",
    "phase": "Phase 3"
  },
  {
    "recordId": "rec1aAFVrNb8JxcZu",
    "company": "GSK",
    "asset": "Trelegy Ellipta",
    "molecule": "fluticasone furoate + umeclidinium + vilanterol",
    "developmentCode": "",
    "brand": "Trelegy Ellipta",
    "aliases": [],
    "indication": "Maintenance treatment of chronic obstructive pulmonary disease",
    "controlledIndication": "Chronic Obstructive Pulmonary Disease",
    "indicationAliases": [],
    "portfolioStatus": "",
    "phase": "Approved"
  },
  {
    "recordId": "rec5XhdiZyNCBXK7b",
    "company": "GSK",
    "asset": "Triumeq",
    "molecule": "dolutegravir + abacavir + lamivudine",
    "developmentCode": "",
    "brand": "Triumeq",
    "aliases": [],
    "indication": "Once-daily single-tablet three-drug regimen for HIV-1 infection",
    "controlledIndication": "HIV-1 Infection",
    "indicationAliases": [],
    "portfolioStatus": "",
    "phase": "Approved"
  },
  {
    "recordId": "rec6XyuIWvQakZBmn",
    "company": "GSK",
    "asset": "Exdensur",
    "molecule": "depemokimab",
    "developmentCode": "",
    "brand": "Exdensur",
    "aliases": [],
    "indication": "Chronic obstructive pulmonary disease",
    "controlledIndication": "Chronic Obstructive Pulmonary Disease",
    "indicationAliases": [],
    "portfolioStatus": "",
    "phase": "Phase 3"
  },
  {
    "recordId": "rec7MQhXUHrENZfHv",
    "company": "GSK",
    "asset": "Penmenvy",
    "molecule": "meningococcal ABCWY vaccine (MenABCWY)",
    "developmentCode": "",
    "brand": "Penmenvy",
    "aliases": [],
    "indication": "Prevention of invasive meningococcal disease caused by serogroups A, B, C, W and Y",
    "controlledIndication": "Meningococcal Disease",
    "indicationAliases": [],
    "portfolioStatus": "",
    "phase": "Approved"
  },
  {
    "recordId": "rec8ujh9kS5dDWaj1",
    "company": "GSK",
    "asset": "Fluarix / FluLaval",
    "molecule": "inactivated influenza vaccine",
    "developmentCode": "",
    "brand": "Fluarix / FluLaval",
    "aliases": [],
    "indication": "Prevention of seasonal influenza",
    "controlledIndication": "Influenza",
    "indicationAliases": [],
    "portfolioStatus": "",
    "phase": "Approved"
  },
  {
    "recordId": "rec8zyeAOCXtPtoHD",
    "company": "GSK",
    "asset": "Tivicay",
    "molecule": "dolutegravir",
    "developmentCode": "",
    "brand": "Tivicay",
    "aliases": [],
    "indication": "Integrase inhibitor backbone for HIV-1 infection in combination regimens (adults, adolescents and paediatrics)",
    "controlledIndication": "HIV-1 Infection",
    "indicationAliases": [],
    "portfolioStatus": "",
    "phase": "Approved"
  },
  {
    "recordId": "rec9a94hoR15cE7Ap",
    "company": "GSK",
    "asset": "Benlysta",
    "molecule": "belimumab",
    "developmentCode": "",
    "brand": "Benlysta",
    "aliases": [],
    "indication": "Active lupus nephritis",
    "controlledIndication": "Lupus Nephritis",
    "indicationAliases": [],
    "portfolioStatus": "",
    "phase": "Approved"
  },
  {
    "recordId": "recAFY9VNbgSLAkza",
    "company": "GSK",
    "asset": "Nucala",
    "molecule": "mepolizumab",
    "developmentCode": "",
    "brand": "Nucala",
    "aliases": [],
    "indication": "Eosinophilic granulomatosis with polyangiitis",
    "controlledIndication": "Eosinophilic Granulomatosis with Polyangiitis",
    "indicationAliases": [],
    "portfolioStatus": "",
    "phase": "Approved"
  },
  {
    "recordId": "recASvRVnWrWJvawm",
    "company": "GSK",
    "asset": "neladalkib",
    "molecule": "neladalkib",
    "developmentCode": "GSK6739060",
    "brand": "neladalkib",
    "aliases": [
      "NVL-655"
    ],
    "indication": "TKI-pretreated ALK-positive NSCLC",
    "controlledIndication": "Non-Small Cell Lung Cancer",
    "indicationAliases": [],
    "portfolioStatus": "",
    "phase": "Filed / Registration"
  },
  {
    "recordId": "recBD37lZyZyNV535",
    "company": "GSK",
    "asset": "Anoro Ellipta",
    "molecule": "umeclidinium + vilanterol",
    "developmentCode": "",
    "brand": "Anoro Ellipta",
    "aliases": [],
    "indication": "Maintenance treatment of COPD (dual bronchodilator)",
    "controlledIndication": "Chronic Obstructive Pulmonary Disease",
    "indicationAliases": [],
    "portfolioStatus": "",
    "phase": "Approved"
  },
  {
    "recordId": "recDotm4mC4yP2brQ",
    "company": "GSK",
    "asset": "GSK4532990",
    "molecule": "",
    "developmentCode": "GSK4532990 / ARO-HSD",
    "brand": "GSK4532990",
    "aliases": [],
    "indication": "Metabolic Dysfunction-Associated Steatohepatitis / Alcohol-Related Liver Disease",
    "controlledIndication": "Metabolic Dysfunction-Associated Steatohepatitis; Alcohol-Related Liver Disease",
    "indicationAliases": [],
    "portfolioStatus": "",
    "phase": "Phase 2"
  },
  {
    "recordId": "recEg7JXSwpPH7jBb",
    "company": "GSK",
    "asset": "GSK5784283",
    "molecule": "",
    "developmentCode": "GSK5784283",
    "brand": "GSK5784283",
    "aliases": [],
    "indication": "Asthma",
    "controlledIndication": "Asthma",
    "indicationAliases": [],
    "portfolioStatus": "",
    "phase": "Phase 2"
  },
  {
    "recordId": "recErNxET8zrkSizV",
    "company": "GSK",
    "asset": "Nucala",
    "molecule": "mepolizumab",
    "developmentCode": "",
    "brand": "Nucala",
    "aliases": [],
    "indication": "Hypereosinophilic syndrome",
    "controlledIndication": "Hypereosinophilic Syndrome",
    "indicationAliases": [],
    "portfolioStatus": "",
    "phase": "Approved"
  },
  {
    "recordId": "recFxkS2Iu7ciqur5",
    "company": "GSK",
    "asset": "Boostrix",
    "molecule": "diphtheria, tetanus, acellular pertussis (Tdap) booster",
    "developmentCode": "",
    "brand": "Boostrix",
    "aliases": [],
    "indication": "Active booster immunisation against tetanus, diphtheria and pertussis in individuals aged 10 years and older; immunisation during the third trimester of pregnancy to prevent pertussis in infants younger than 2 months",
    "controlledIndication": "Tetanus, Diphtheria and Pertussis",
    "indicationAliases": [],
    "portfolioStatus": "",
    "phase": "Approved"
  },
  {
    "recordId": "recGLvyZQxZVdA2Bd",
    "company": "GSK",
    "asset": "Blujepa",
    "molecule": "gepotidacin",
    "developmentCode": "",
    "brand": "Blujepa",
    "aliases": [],
    "indication": "Uncomplicated urinary tract infections in female adults and paediatric patients aged 12 years and older meeting label weight criteria",
    "controlledIndication": "Uncomplicated Urinary Tract Infection",
    "indicationAliases": [],
    "portfolioStatus": "",
    "phase": "Approved"
  },
  {
    "recordId": "recGaOstcAfk6Nh4n",
    "company": "GSK",
    "asset": "GSK4382276",
    "molecule": "GSK4382276",
    "developmentCode": "GSK4382276",
    "brand": "GSK4382276",
    "aliases": [],
    "indication": "Seasonal influenza",
    "controlledIndication": "Influenza",
    "indicationAliases": [],
    "portfolioStatus": "",
    "phase": "Phase 2"
  },
  {
    "recordId": "recIe0tp13zUJmlz2",
    "company": "GSK",
    "asset": "Arexvy",
    "molecule": "RSVPreF3 OA vaccine",
    "developmentCode": "",
    "brand": "Arexvy",
    "aliases": [],
    "indication": "Prevention of RSV lower respiratory tract disease in adults 60+ and adults 18-59 at increased risk",
    "controlledIndication": "Respiratory Syncytial Virus Disease",
    "indicationAliases": [],
    "portfolioStatus": "",
    "phase": "Approved"
  },
  {
    "recordId": "recIkBN5wQby6EUsZ",
    "company": "GSK",
    "asset": "Dovato",
    "molecule": "dolutegravir + lamivudine",
    "developmentCode": "",
    "brand": "Dovato",
    "aliases": [
      "DTG/3TC"
    ],
    "indication": "Complete once-daily two-drug regimen (2DR) for HIV-1 infection in treatment-naive and virally suppressed adults and adolescents",
    "controlledIndication": "HIV-1 Infection",
    "indicationAliases": [],
    "portfolioStatus": "",
    "phase": "Approved"
  },
  {
    "recordId": "recIzgzVyTLCkNluQ",
    "company": "GSK",
    "asset": "Relvar / Breo Ellipta",
    "molecule": "fluticasone furoate + vilanterol",
    "developmentCode": "",
    "brand": "Relvar / Breo Ellipta",
    "aliases": [],
    "indication": "Maintenance treatment of chronic obstructive pulmonary disease",
    "controlledIndication": "Chronic Obstructive Pulmonary Disease",
    "indicationAliases": [],
    "portfolioStatus": "",
    "phase": "Approved"
  },
  {
    "recordId": "recK8MdSgdkbWDh2f",
    "company": "GSK",
    "asset": "Trelegy Ellipta",
    "molecule": "fluticasone furoate + umeclidinium + vilanterol",
    "developmentCode": "",
    "brand": "Trelegy Ellipta",
    "aliases": [],
    "indication": "Maintenance treatment of asthma in adults aged 18 years and older",
    "controlledIndication": "Asthma",
    "indicationAliases": [],
    "portfolioStatus": "",
    "phase": "Approved"
  },
  {
    "recordId": "recNBzcZoU5GzV3JN",
    "company": "GSK",
    "asset": "velzatinib",
    "molecule": "velzatinib",
    "developmentCode": "GSK6042981",
    "brand": "velzatinib",
    "aliases": [
      "IDRX-42"
    ],
    "indication": "Gastrointestinal stromal tumour",
    "controlledIndication": "Gastrointestinal Stromal Tumor",
    "indicationAliases": [],
    "portfolioStatus": "",
    "phase": "Phase 3"
  },
  {
    "recordId": "recPUwFj41bZpSZ1F",
    "company": "GSK",
    "asset": "risvutatug rezetecan",
    "molecule": "risvutatug rezetecan",
    "developmentCode": "GSK5764227",
    "brand": "risvutatug rezetecan",
    "aliases": [
      "Ris-Rez",
      "GSK'227"
    ],
    "indication": "Relapsed or refractory extensive-stage small-cell lung cancer",
    "controlledIndication": "Small Cell Lung Cancer",
    "indicationAliases": [],
    "portfolioStatus": "",
    "phase": "Phase 3"
  },
  {
    "recordId": "recQABfD5MaNqa1t0",
    "company": "GSK",
    "asset": "Juluca",
    "molecule": "dolutegravir + rilpivirine",
    "developmentCode": "",
    "brand": "Juluca",
    "aliases": [],
    "indication": "Once-daily two-drug regimen (2DR) for HIV-1 in virally suppressed adults",
    "controlledIndication": "HIV-1 Infection",
    "indicationAliases": [],
    "portfolioStatus": "",
    "phase": "Approved"
  },
  {
    "recordId": "recSSgoCRwz3N2wmu",
    "company": "GSK",
    "asset": "efimosfermin alfa",
    "molecule": "efimosfermin alfa",
    "developmentCode": "GSK6519754",
    "brand": "efimosfermin alfa",
    "aliases": [],
    "indication": "Metabolic dysfunction-associated steatohepatitis",
    "controlledIndication": "Metabolic Dysfunction-Associated Steatohepatitis",
    "indicationAliases": [],
    "portfolioStatus": "",
    "phase": "Phase 3"
  },
  {
    "recordId": "recSk8Iaj5Tqd88K0",
    "company": "GSK",
    "asset": "Bexsero",
    "molecule": "Meningococcal Group B Vaccine",
    "developmentCode": "",
    "brand": "Bexsero",
    "aliases": [],
    "indication": "Prevention of invasive meningococcal group B disease",
    "controlledIndication": "Meningococcal Disease",
    "indicationAliases": [],
    "portfolioStatus": "",
    "phase": "Approved"
  },
  {
    "recordId": "recSoikZRYW2VQcAh",
    "company": "GSK",
    "asset": "GSK5733584",
    "molecule": "",
    "developmentCode": "GSK5733584",
    "brand": "GSK5733584",
    "aliases": [],
    "indication": "Endometrial Cancer",
    "controlledIndication": "Endometrial Cancer",
    "indicationAliases": [],
    "portfolioStatus": "",
    "phase": "Phase 3"
  },
  {
    "recordId": "recWNMCk5On9yadOC",
    "company": "GSK",
    "asset": "cabotegravir",
    "molecule": "cabotegravir",
    "developmentCode": "GSK1265744",
    "brand": "cabotegravir",
    "aliases": [],
    "indication": "HIV",
    "controlledIndication": "HIV-1 Infection",
    "indicationAliases": [],
    "portfolioStatus": "",
    "phase": "Phase 3"
  },
  {
    "recordId": "recYKoyBJzRUvDyej",
    "company": "GSK",
    "asset": "Nucala",
    "molecule": "mepolizumab",
    "developmentCode": "",
    "brand": "Nucala",
    "aliases": [],
    "indication": "Severe eosinophilic asthma",
    "controlledIndication": "Asthma",
    "indicationAliases": [],
    "portfolioStatus": "",
    "phase": "Approved"
  },
  {
    "recordId": "recZ01ve3lAVXQApp",
    "company": "GSK",
    "asset": "Nucala",
    "molecule": "mepolizumab",
    "developmentCode": "",
    "brand": "Nucala",
    "aliases": [],
    "indication": "Chronic obstructive pulmonary disease with an eosinophilic phenotype",
    "controlledIndication": "Chronic Obstructive Pulmonary Disease",
    "indicationAliases": [],
    "portfolioStatus": "",
    "phase": "Approved"
  },
  {
    "recordId": "reca6jwA2MLbgj7CK",
    "company": "GSK",
    "asset": "Jemperli",
    "molecule": "dostarlimab",
    "developmentCode": "",
    "brand": "Jemperli",
    "aliases": [],
    "indication": "Primary advanced or recurrent endometrial cancer in adults, in combination with carboplatin and paclitaxel",
    "controlledIndication": "Endometrial Cancer",
    "indicationAliases": [],
    "portfolioStatus": "",
    "phase": "Approved"
  },
  {
    "recordId": "recaZJuFUsMBhSGwD",
    "company": "GSK",
    "asset": "bepirovirsen",
    "molecule": "bepirovirsen",
    "developmentCode": "GSK3228836",
    "brand": "bepirovirsen",
    "aliases": [],
    "indication": "Chronic hepatitis B infection",
    "controlledIndication": "Chronic Hepatitis B",
    "indicationAliases": [],
    "portfolioStatus": "",
    "phase": "Filed / Registration"
  },
  {
    "recordId": "recdf4BiR5ntgpmAW",
    "company": "GSK",
    "asset": "GSK5637608",
    "molecule": "GSK5637608",
    "developmentCode": "GSK5637608",
    "brand": "GSK5637608",
    "aliases": [],
    "indication": "Chronic hepatitis B infection",
    "controlledIndication": "Chronic Hepatitis B",
    "indicationAliases": [],
    "portfolioStatus": "",
    "phase": "Phase 2"
  },
  {
    "recordId": "receXkdtQRLVatWOp",
    "company": "GSK",
    "asset": "Shingrix",
    "molecule": "recombinant zoster vaccine (RZV)",
    "developmentCode": "",
    "brand": "Shingrix",
    "aliases": [],
    "indication": "Prevention of herpes zoster (shingles) and post-herpetic neuralgia in adults 50+ and immunocompromised adults 18+",
    "controlledIndication": "Herpes Zoster",
    "indicationAliases": [],
    "portfolioStatus": "",
    "phase": "Approved"
  },
  {
    "recordId": "recg7G9OdPmQd8E4c",
    "company": "GSK",
    "asset": "Blujepa",
    "molecule": "gepotidacin",
    "developmentCode": "",
    "brand": "Blujepa",
    "aliases": [],
    "indication": "Uncomplicated urogenital gonorrhea caused by susceptible Neisseria gonorrhoeae in patients aged 12 years and older with limited or no alternative treatment options",
    "controlledIndication": "Gonorrhea",
    "indicationAliases": [],
    "portfolioStatus": "",
    "phase": "Approved"
  },
  {
    "recordId": "recgxlTZZ016mRVsK",
    "company": "GSK",
    "asset": "Nucala",
    "molecule": "mepolizumab",
    "developmentCode": "",
    "brand": "Nucala",
    "aliases": [],
    "indication": "Chronic rhinosinusitis with nasal polyps",
    "controlledIndication": "Chronic Rhinosinusitis with Nasal Polyps",
    "indicationAliases": [],
    "portfolioStatus": "",
    "phase": "Approved"
  },
  {
    "recordId": "rechIWhlqMzsTnGJL",
    "company": "GSK",
    "asset": "GSK5733584",
    "molecule": "",
    "developmentCode": "GSK5733584",
    "brand": "GSK5733584",
    "aliases": [],
    "indication": "Ovarian Cancer",
    "controlledIndication": "Ovarian Cancer",
    "indicationAliases": [],
    "portfolioStatus": "",
    "phase": "Phase 3"
  },
  {
    "recordId": "rechye3x9CTcQBqUV",
    "company": "GSK",
    "asset": "GSK1265744ULA + GSK1329758ULA",
    "molecule": "",
    "developmentCode": "CAB ULA + RPV ULA",
    "brand": "GSK1265744ULA + GSK1329758ULA",
    "aliases": [],
    "indication": "HIV-1 Infection",
    "controlledIndication": "HIV-1 Infection",
    "indicationAliases": [],
    "portfolioStatus": "",
    "phase": "Phase 3"
  },
  {
    "recordId": "reciSqoY9WypKK9Vo",
    "company": "GSK",
    "asset": "Benlysta",
    "molecule": "belimumab",
    "developmentCode": "",
    "brand": "Benlysta",
    "aliases": [],
    "indication": "Systemic lupus erythematosus",
    "controlledIndication": "Systemic Lupus Erythematosus",
    "indicationAliases": [],
    "portfolioStatus": "",
    "phase": "Approved"
  },
  {
    "recordId": "recietUhjjp0Kaljd",
    "company": "GSK",
    "asset": "Ojjaara / Omjjara",
    "molecule": "momelotinib",
    "developmentCode": "",
    "brand": "Ojjaara / Omjjara",
    "aliases": [],
    "indication": "Myelofibrosis with anaemia (intermediate/high-risk)",
    "controlledIndication": "Myelofibrosis",
    "indicationAliases": [],
    "portfolioStatus": "",
    "phase": "Approved"
  },
  {
    "recordId": "recimddiwPX0JK6Vx",
    "company": "GSK",
    "asset": "Cabenuva",
    "molecule": "cabotegravir + rilpivirine",
    "developmentCode": "",
    "brand": "Cabenuva",
    "aliases": [
      "CAB/RPV LA"
    ],
    "indication": "First complete long-acting injectable regimen for HIV-1 treatment in virally suppressed adults (monthly or every-two-months dosing)",
    "controlledIndication": "HIV-1 Infection",
    "indicationAliases": [],
    "portfolioStatus": "",
    "phase": "Approved"
  },
  {
    "recordId": "recqfe0uaVYp4ROUn",
    "company": "GSK",
    "asset": "Apretude",
    "molecule": "cabotegravir",
    "developmentCode": "",
    "brand": "Apretude",
    "aliases": [],
    "indication": "First long-acting injectable for HIV pre-exposure prophylaxis (PrEP) in at-risk adults and adolescents",
    "controlledIndication": "HIV-1 Pre-Exposure Prophylaxis (PrEP)",
    "indicationAliases": [],
    "portfolioStatus": "",
    "phase": "Approved"
  },
  {
    "recordId": "recrCUsgnJ0yiYDUx",
    "company": "GSK",
    "asset": "Blenrep",
    "molecule": "belantamab mafodotin",
    "developmentCode": "",
    "brand": "Blenrep",
    "aliases": [],
    "indication": "Relapsed or refractory multiple myeloma; US label requires at least two prior lines including a proteasome inhibitor and an immunomodulatory agent",
    "controlledIndication": "Multiple Myeloma",
    "indicationAliases": [],
    "portfolioStatus": "",
    "phase": "Approved"
  },
  {
    "recordId": "recrGa9LmBzy3RB6X",
    "company": "GSK",
    "asset": "VH4524184",
    "molecule": "",
    "developmentCode": "VH4524184",
    "brand": "VH4524184",
    "aliases": [],
    "indication": "HIV-1 Infection",
    "controlledIndication": "HIV-1 Infection",
    "indicationAliases": [],
    "portfolioStatus": "",
    "phase": "Phase 2"
  },
  {
    "recordId": "rectasye4uiEC6LDL",
    "company": "GSK",
    "asset": "GSK3862995",
    "molecule": "",
    "developmentCode": "GSK3862995",
    "brand": "GSK3862995",
    "aliases": [],
    "indication": "Bronchiectasis",
    "controlledIndication": "Bronchiectasis",
    "indicationAliases": [],
    "portfolioStatus": "",
    "phase": "Phase 2"
  },
  {
    "recordId": "recvDSR2Cekfv3hCl",
    "company": "GSK",
    "asset": "Zejula",
    "molecule": "niraparib",
    "developmentCode": "",
    "brand": "Zejula",
    "aliases": [],
    "indication": "Maintenance treatment of advanced ovarian cancer",
    "controlledIndication": "Ovarian Cancer",
    "indicationAliases": [],
    "portfolioStatus": "",
    "phase": "Approved"
  },
  {
    "recordId": "recvywvCzyU31Acen",
    "company": "GSK",
    "asset": "Relvar / Breo Ellipta",
    "molecule": "fluticasone furoate + vilanterol",
    "developmentCode": "",
    "brand": "Relvar / Breo Ellipta",
    "aliases": [],
    "indication": "Maintenance treatment of asthma",
    "controlledIndication": "Asthma",
    "indicationAliases": [],
    "portfolioStatus": "",
    "phase": "Approved"
  }
]''')


async def main():
    source = await extract_generic_xlsx("GSK", URL, 35.0)

    source_rows = []
    for row in source.rows:
        phase = row.get("phase") or ""
        source_rows.append(
            DiscoverySourceRow(
                company="GSK",
                sourceFamily="Company Pipeline",
                sourceRecordId=row.get("sourceRecordId"),
                sourceUrl=row.get("sourceUrl"),
                asset=row.get("asset"),
                molecule=row.get("molecule"),
                developmentCode=row.get("developmentCode"),
                brand=row.get("brand"),
                indication=row.get("indication"),
                phase=phase,
                programStatus="Active",
                sponsorOwner="GSK",
                partners=row.get("partners") or [],
                strategicPhase1=False,
            )
        )

    request = DiscoveryCompareRequest(
        company="GSK",
        companyAliases=["GlaxoSmithKline"],
        sourceRows=source_rows,
        portfolioRows=[PortfolioSnapshotRow(**row) for row in PORTFOLIO_SNAPSHOT],
        batchRunId="GSK-XLSX-Q2-2026-CANARY",
    )
    compared = compare_discovery(request)

    by_class = {}
    for c in compared.candidates:
        by_class.setdefault(c["classification"], []).append(c)

    compact_samples = {}
    for name, vals in by_class.items():
        compact_samples[name] = [
            {
                "asset": x.get("asset"),
                "developmentCode": x.get("developmentCode"),
                "indication": x.get("indication"),
                "phase": x.get("phase"),
                "matchMethod": x.get("matchMethod"),
                "existingPortfolioRecordIds": x.get("existingPortfolioRecordIds"),
                "decision": x.get("commercialInclusionDecision"),
                "reason": x.get("reviewReason"),
            }
            for x in vals[:8]
        ]

    print("GSK_XLSX_RECON_CANARY " + json.dumps({
        "adapterReady": source.readyForDiscovery,
        "sourceRows": source.rowCount,
        "portfolioRows": len(PORTFOLIO_SNAPSHOT),
        "summary": compared.summary,
        "samples": compact_samples,
        "masterWrites": 0,
        "portfolioDependentAdapterValidation": False,
    }, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
