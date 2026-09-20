"""Read-only GSK XLSX + controlled-indication resolver baseline canary.

Embeds current Airtable indication taxonomy and GSK Portfolio snapshot only for
validation. Performs no Airtable/master-data writes.
"""

import asyncio
import json
import re
import unicodedata
from collections import Counter

from generic_xlsx_pipeline_extension import extract_generic_xlsx
from portfolio_discovery_extension import (
    DiscoveryCompareRequest,
    DiscoverySourceRow,
    PortfolioSnapshotRow,
    compare_discovery,
)

URL = "https://www.gsk.com/media/2qfbw2yv/2q2026-pipeline-list.xlsx"
INDICATIONS = json.loads(r'''[
  {
    "id": "rec06P7QcKJR9Yzzi",
    "canonical": "Chronic Lung Allograft Dysfunction",
    "short": "CLAD",
    "aliases": [
      "Chronic lung allograft dysfunction",
      "CLAD"
    ]
  },
  {
    "id": "rec0Pg87LtJPfJzhJ",
    "canonical": "Migraine",
    "short": "Migraine",
    "aliases": []
  },
  {
    "id": "rec0QuCXC2Ny388uI",
    "canonical": "Multiple Myeloma",
    "short": "MM",
    "aliases": []
  },
  {
    "id": "rec0xeJ0SnsC2UhaR",
    "canonical": "Pelizaeus-Merzbacher Disease",
    "short": "PMD",
    "aliases": [
      "Pelizaeus-Merzbacher disease"
    ]
  },
  {
    "id": "rec1PiHISwwRlZuEr",
    "canonical": "Primary Membranous Nephropathy",
    "short": "PMN",
    "aliases": []
  },
  {
    "id": "rec1RC35m1HXHzoWp",
    "canonical": "Mantle Cell Lymphoma",
    "short": "MCL",
    "aliases": []
  },
  {
    "id": "rec1VEStvPEmo25aH",
    "canonical": "Myelofibrosis",
    "short": "MF",
    "aliases": []
  },
  {
    "id": "rec1YjV437P73ZBvY",
    "canonical": "Transthyretin Amyloid Cardiomyopathy (ATTR-CM)",
    "short": "ATTR-CM",
    "aliases": [
      "ATTR Amyloidosis with Cardiomyopathy",
      "Transthyretin amyloidosis with cardiomyopathy"
    ]
  },
  {
    "id": "rec1e2SN9RufUFfon",
    "canonical": "Facioscapulohumeral Muscular Dystrophy",
    "short": "FSHD",
    "aliases": []
  },
  {
    "id": "rec1jO7FivMv1aWps",
    "canonical": "MOG Antibody-Associated Disease",
    "short": "MOGAD",
    "aliases": []
  },
  {
    "id": "rec2Y9u3uX41wqUnT",
    "canonical": "Pulmonary Hypertension Associated with COPD",
    "short": "PH-COPD",
    "aliases": [
      "Pulmonary hypertension associated with chronic obstructive pulmonary disease",
      "Pulmonary hypertension-chronic obstructive pulmonary disease"
    ]
  },
  {
    "id": "rec2ebCjjz6rOcjLq",
    "canonical": "Geographic Atrophy",
    "short": "GA",
    "aliases": []
  },
  {
    "id": "rec2jhIMx3kUtAIaw",
    "canonical": "Biliary Tract Cancer",
    "short": "BTC",
    "aliases": []
  },
  {
    "id": "rec2mXac9gnEZc6Er",
    "canonical": "Endometrial Hyperplasia",
    "short": "EH",
    "aliases": []
  },
  {
    "id": "rec36HgBOI9o3A9KY",
    "canonical": "B-Cell Non-Hodgkin Lymphoma",
    "short": "B-NHL",
    "aliases": [
      "B-cell NHL",
      "B-NHL",
      "B-cell non-Hodgkin lymphoma"
    ]
  },
  {
    "id": "rec3JuHrmPQdLfAV0",
    "canonical": "Esophageal Adenocarcinoma",
    "short": "EAC",
    "aliases": [
      "Oesophageal adenocarcinoma"
    ]
  },
  {
    "id": "rec3SP5TNphzOjT3y",
    "canonical": "Hepatocellular Carcinoma",
    "short": "HCC",
    "aliases": []
  },
  {
    "id": "rec3fktXW278yQQjC",
    "canonical": "Chronic Rhinosinusitis with Nasal Polyps",
    "short": "CRSwNP",
    "aliases": []
  },
  {
    "id": "rec3hNvFTScD1pYWq",
    "canonical": "Axial Spondyloarthritis",
    "short": "axSpA",
    "aliases": []
  },
  {
    "id": "rec3xmsexXOLvYZV7",
    "canonical": "Anaphylaxis",
    "short": "Anaphylaxis",
    "aliases": []
  },
  {
    "id": "rec48LHmZdHfYz5HV",
    "canonical": "NTRK Fusion-Positive Solid Tumors",
    "short": "NTRK+ Tumors",
    "aliases": [
      "solid tumors that have a neurotrophic tyrosine receptor kinase (NTRK) gene fusion",
      "NTRK gene fusion-positive solid tumors"
    ]
  },
  {
    "id": "rec4UvjUm02XcQHeX",
    "canonical": "Exocrine Pancreatic Insufficiency",
    "short": "EPI",
    "aliases": []
  },
  {
    "id": "rec4mbamT1PpRGDNN",
    "canonical": "Acute Coronary Syndrome",
    "short": "ACS",
    "aliases": []
  },
  {
    "id": "rec4nSOQ5WV9u2PUY",
    "canonical": "Diabetic Macular Edema",
    "short": "DME",
    "aliases": []
  },
  {
    "id": "rec54qpQf7uE8kw0K",
    "canonical": "Follicular Lymphoma",
    "short": "FL",
    "aliases": []
  },
  {
    "id": "rec59vtakhrojHfvH",
    "canonical": "Giant Cell Arteritis",
    "short": "GCA",
    "aliases": []
  },
  {
    "id": "rec5INNcUJJ4PpFL5",
    "canonical": "Psoriasis",
    "short": "PsO",
    "aliases": []
  },
  {
    "id": "rec5N0CsTwgoCj8uv",
    "canonical": "Diffuse Large B-Cell Lymphoma",
    "short": "DLBCL",
    "aliases": []
  },
  {
    "id": "rec5gKBGZcdpy8vKA",
    "canonical": "Attention-Deficit/Hyperactivity Disorder",
    "short": "ADHD",
    "aliases": []
  },
  {
    "id": "rec5m1HyeNtj57lM8",
    "canonical": "Parkinson's Disease",
    "short": "PD",
    "aliases": []
  },
  {
    "id": "rec5vffQe6ZhKCem1",
    "canonical": "Neurofibromatosis Type 1",
    "short": "NF1",
    "aliases": []
  },
  {
    "id": "rec600lmmMd3g2dhn",
    "canonical": "Glaucoma",
    "short": "Glaucoma",
    "aliases": []
  },
  {
    "id": "rec657gwY1lFdRfKH",
    "canonical": "OTOF-Related Genetic Hearing Loss",
    "short": "OTOF Hearing Loss",
    "aliases": [
      "hearing loss due to mutations of the OTOF gene",
      "severe-to-profound and profound sensorineural hearing loss associated with molecularly confirmed biallelic variants in the OTOF gene",
      "OTOF-related hearing loss",
      "severe-to-profound and profound sensorineural hearing loss (any frequency >90 dB HL) associated with molecularly confirmed biallelic variants in the OTOF gene"
    ]
  },
  {
    "id": "rec67CjP11okLdTyZ",
    "canonical": "Marginal Zone Lymphoma",
    "short": "MZL",
    "aliases": []
  },
  {
    "id": "rec6RVNroywalli1I",
    "canonical": "HSCT-Associated Thrombotic Microangiopathy",
    "short": "HSCT-TMA",
    "aliases": [
      "HSCT-associated thrombotic microangiopathy",
      "HSCT-TMA",
      "haematopoietic stem cell transplant-associated thrombotic microangiopathy",
      "hematopoietic stem cell transplant-associated thrombotic microangiopathy"
    ]
  },
  {
    "id": "rec6iHiSim6taAN4y",
    "canonical": "Hemophilia A",
    "short": "HA",
    "aliases": [
      "Hemophilia A or B"
    ]
  },
  {
    "id": "rec7EAxL949kTU5Dp",
    "canonical": "Hypothyroidism",
    "short": "Hypothyroidism",
    "aliases": []
  },
  {
    "id": "rec7VWGT0zL3Pt5xr",
    "canonical": "Amyotrophic Lateral Sclerosis",
    "short": "ALS",
    "aliases": [
      "SOD1 Amyotrophic Lateral Sclerosis",
      "SOD1 ALS"
    ]
  },
  {
    "id": "rec7hOqNTTJPPr1YT",
    "canonical": "Tobacco Use Disorder",
    "short": "TUD",
    "aliases": []
  },
  {
    "id": "rec7kSLLu8uEOq4J2",
    "canonical": "Presbyopia",
    "short": "Presbyopia",
    "aliases": []
  },
  {
    "id": "rec7kz4J1myI08Ccl",
    "canonical": "Clostridioides difficile Infection",
    "short": "CDI",
    "aliases": [
      "C. difficile infection",
      "Clostridium difficile infection"
    ]
  },
  {
    "id": "rec7nhaxvAApleVQX",
    "canonical": "Chronic Kidney Disease",
    "short": "CKD",
    "aliases": []
  },
  {
    "id": "rec84SBIm3Y2Z7WAb",
    "canonical": "Pompe Disease",
    "short": "Pompe",
    "aliases": []
  },
  {
    "id": "rec8Fa8LaNqHSXjKK",
    "canonical": "Cold Agglutinin Disease",
    "short": "CAD",
    "aliases": []
  },
  {
    "id": "rec8jJLH3mpieSYOI",
    "canonical": "Hypertriglyceridemia",
    "short": "HTG",
    "aliases": [
      "Hypertriglyceridaemia",
      "Elevated triglycerides",
      "High triglycerides"
    ]
  },
  {
    "id": "rec94PLEYL2UbVNgE",
    "canonical": "Familial Chylomicronemia Syndrome",
    "short": "FCS",
    "aliases": [
      "Familial Chylomicronemia",
      "Familial Chylomicronaemia Syndrome",
      "Familial Chylomicronaemia",
      "Familial hyperchylomicronemia syndrome",
      "Familial lipoprotein lipase deficiency",
      "Hyperlipoproteinemia Type I",
      "Hyperlipoproteinaemia Type I"
    ]
  },
  {
    "id": "rec9Edsf05fcZvQwM",
    "canonical": "Von Willebrand Disease",
    "short": "VWD",
    "aliases": [
      "Von Willebrand Disease"
    ]
  },
  {
    "id": "rec9JPpvGayVJTRy4",
    "canonical": "Cancer Cachexia",
    "short": "",
    "aliases": [
      "Cachexia in Cancer",
      "Cancer-associated cachexia"
    ]
  },
  {
    "id": "rec9aZTfRreK8Mq8A",
    "canonical": "Human Parainfluenza Virus Type 3 Infection",
    "short": "HPIV3",
    "aliases": [
      "Human parainfluenza virus type 3 infection",
      "Parainfluenza virus type 3 infection",
      "PIV3 infection",
      "HPIV3 infection",
      "PIV3"
    ]
  },
  {
    "id": "rec9oYmoh7jvpgljT",
    "canonical": "Cutaneous Lupus Erythematosus",
    "short": "CLE",
    "aliases": []
  },
  {
    "id": "recACP15cXLhUzCfZ",
    "canonical": "Tetanus, Diphtheria and Pertussis",
    "short": "Tdap",
    "aliases": []
  },
  {
    "id": "recALZRv8cZ5b5X93",
    "canonical": "Gaucher Disease",
    "short": "Gaucher",
    "aliases": []
  },
  {
    "id": "recAOHNcIcqQEDYY7",
    "canonical": "Staphylococcus aureus Bloodstream Infection",
    "short": "S. aureus BSI",
    "aliases": [
      "Staphylococcus aureus bloodstream infection",
      "S. aureus BSI",
      "Staph aureus infection"
    ]
  },
  {
    "id": "recAPSuaKVViWG8l8",
    "canonical": "Hypertrophic Cardiomyopathy",
    "short": "HCM",
    "aliases": []
  },
  {
    "id": "recAYFF6dMDU7IP2w",
    "canonical": "Malaria",
    "short": "Malaria",
    "aliases": []
  },
  {
    "id": "recAZ2g5jwOrZHq78",
    "canonical": "Paroxysmal Nocturnal Hemoglobinuria",
    "short": "PNH",
    "aliases": []
  },
  {
    "id": "recAaCEyzO9klCBhY",
    "canonical": "Organ Transplant Rejection",
    "short": "Transplant Rejection",
    "aliases": [
      "Prophylaxis of organ rejection",
      "Prevention of organ rejection"
    ]
  },
  {
    "id": "recB2pwWoa0g73Ywz",
    "canonical": "Bullous Pemphigoid",
    "short": "BP",
    "aliases": []
  },
  {
    "id": "recBLudMjZUo0lEvo",
    "canonical": "Alpha-1 Antitrypsin Deficiency",
    "short": "AATD",
    "aliases": []
  },
  {
    "id": "recBZwJimSLR5zu7j",
    "canonical": "Lyme Disease",
    "short": "Lyme",
    "aliases": []
  },
  {
    "id": "recBdlGk8kHNSmqkH",
    "canonical": "Cat Allergy",
    "short": "Cat Allergy",
    "aliases": [
      "Cat allergy",
      "Cat dander allergy"
    ]
  },
  {
    "id": "recBjTywmg4ynwz1x",
    "canonical": "Osteoporosis",
    "short": "Osteoporosis",
    "aliases": []
  },
  {
    "id": "recBvKpztLCbEo7Ph",
    "canonical": "Angelman Syndrome",
    "short": "Angelman Syndrome",
    "aliases": [
      "Angelman syndrome"
    ]
  },
  {
    "id": "recC9XXx0m7y4rgpk",
    "canonical": "Huntington's Disease",
    "short": "HD",
    "aliases": []
  },
  {
    "id": "recCCYMuFhIAFPYGw",
    "canonical": "Invasive Group B Streptococcus Disease",
    "short": "GBS",
    "aliases": [
      "Invasive Group B Streptococcus Infection",
      "Group B Streptococcus Infection"
    ]
  },
  {
    "id": "recCMyKvjKOmlNdoS",
    "canonical": "B-Cell Acute Lymphoblastic Leukemia",
    "short": "B-ALL",
    "aliases": [
      "B-cell precursor acute lymphoblastic leukemia",
      "B-cell precursor ALL",
      "Philadelphia chromosome-positive acute lymphoblastic leukemia",
      "Ph+ ALL"
    ]
  },
  {
    "id": "recCajMSH0x41KcuY",
    "canonical": "Schizophrenia",
    "short": "SCZ",
    "aliases": []
  },
  {
    "id": "recCb9YUHjaS9rfHI",
    "canonical": "Birch Allergy",
    "short": "Birch Allergy",
    "aliases": [
      "Birch allergy",
      "Birch pollen allergy"
    ]
  },
  {
    "id": "recCd45SjhhfjNigx",
    "canonical": "Acute Pain",
    "short": "Acute Pain",
    "aliases": []
  },
  {
    "id": "recCmkznPpDFu78Vz",
    "canonical": "Hepatitis C",
    "short": "HCV",
    "aliases": []
  },
  {
    "id": "recCxhzffCYScYWYT",
    "canonical": "Acute Kidney Injury",
    "short": "AKI",
    "aliases": [
      "acute kidney injury",
      "AKI"
    ]
  },
  {
    "id": "recD9AKQeZlCUFvX4",
    "canonical": "Alexander Disease",
    "short": "AxD",
    "aliases": []
  },
  {
    "id": "recDFb05Ysbv8zPsm",
    "canonical": "Bronchiectasis",
    "short": "Bronchiectasis",
    "aliases": []
  },
  {
    "id": "recDQC4lgECqybfI3",
    "canonical": "Acute Myocardial Infarction",
    "short": "AMI",
    "aliases": []
  },
  {
    "id": "recDZpnLWKIQDWdLQ",
    "canonical": "Status Epilepticus",
    "short": "SE",
    "aliases": []
  },
  {
    "id": "recDpMYrKtZ5yp0kD",
    "canonical": "Neurotrophic Keratopathy",
    "short": "NK",
    "aliases": []
  },
  {
    "id": "recDqN9qY3FIhjjDc",
    "canonical": "Mood and Anxiety Disorders (Basket)",
    "short": "",
    "aliases": [
      "Mood and Anxiety Disorders"
    ]
  },
  {
    "id": "recE9Zrsgx86PJkcv",
    "canonical": "Hypercholesterolemia",
    "short": "Hypercholesterolemia",
    "aliases": []
  },
  {
    "id": "recEDoePswaKh11Jh",
    "canonical": "Thyroid Eye Disease",
    "short": "TED",
    "aliases": []
  },
  {
    "id": "recES2xRL5WCsuFTV",
    "canonical": "Contraception",
    "short": "Contraception",
    "aliases": [
      "Prevention of pregnancy"
    ]
  },
  {
    "id": "recEgaQvbtBfmbUSe",
    "canonical": "Hyperkalemia",
    "short": "HyperK",
    "aliases": []
  },
  {
    "id": "recEwp54wLI1cOEHk",
    "canonical": "Acinetobacter baumannii Infection",
    "short": "A. baumannii",
    "aliases": []
  },
  {
    "id": "recF5ouBBNRfXUu4y",
    "canonical": "Chronic Hepatitis D",
    "short": "CHD",
    "aliases": [
      "Chronic hepatitis delta virus infection",
      "Chronic hepatitis D virus infection",
      "Chronic HDV infection"
    ]
  },
  {
    "id": "recFG4oP99OFWhyM5",
    "canonical": "Minimal Change Disease",
    "short": "MCD",
    "aliases": [
      "Minimal change disease",
      "Minimal change nephropathy",
      "MCD"
    ]
  },
  {
    "id": "recFIVoY2jjqZtNgP",
    "canonical": "Eosinophilic Esophagitis",
    "short": "EoE",
    "aliases": []
  },
  {
    "id": "recFQEnwVexqz0xiA",
    "canonical": "Dyslipidemia",
    "short": "Dyslipidemia",
    "aliases": [
      "Dyslipidemia"
    ]
  },
  {
    "id": "recFjvEntwXN3UNvW",
    "canonical": "Painful Distal Sensory Polyneuropathy",
    "short": "Painful DSP",
    "aliases": []
  },
  {
    "id": "recFkbw8jEO2RZJph",
    "canonical": "Progressive Supranuclear Palsy",
    "short": "PSP",
    "aliases": [
      "Progressive supranuclear palsy"
    ]
  },
  {
    "id": "recG2looERNPbYTPQ",
    "canonical": "Chronic Lymphocytic Leukemia",
    "short": "CLL",
    "aliases": []
  },
  {
    "id": "recGlqtxXp5FWhrxl",
    "canonical": "Myasthenia Gravis",
    "short": "MG",
    "aliases": [
      "Myasthenia gravis"
    ]
  },
  {
    "id": "recGqHO6GAc931CIA",
    "canonical": "Neurogenic Detrusor Overactivity",
    "short": "NDO",
    "aliases": []
  },
  {
    "id": "recH0qrRvjmWdpEAk",
    "canonical": "Skeletal-Related Event Prevention",
    "short": "SRE Prevention",
    "aliases": []
  },
  {
    "id": "recHhGZLDgoSqekYJ",
    "canonical": "Pharmacologically Induced Mydriasis",
    "short": "Mydriasis",
    "aliases": []
  },
  {
    "id": "recHvC210ENjrhGB5",
    "canonical": "Inflammatory Diseases (Basket)",
    "short": "",
    "aliases": [
      "Inflammatory Diseases"
    ]
  },
  {
    "id": "recI426RE1CYbVwnW",
    "canonical": "Prion Disease",
    "short": "PrD",
    "aliases": [
      "Prion disease"
    ]
  },
  {
    "id": "recIELX7F8MvEkYu3",
    "canonical": "IgE-Mediated Food Allergy",
    "short": "Food Allergy",
    "aliases": []
  },
  {
    "id": "recIVA1pnWtuf4Wvk",
    "canonical": "Post-Refractive Surgery Visual Disturbances",
    "short": "Post-RS Visual Disturbance",
    "aliases": []
  },
  {
    "id": "recIe15woWDBbrNBl",
    "canonical": "Peripheral Artery Disease",
    "short": "PAD",
    "aliases": []
  },
  {
    "id": "recJ5JsvyXM5bwUtx",
    "canonical": "Systemic Autoimmune Rheumatic Disease-Associated Interstitial Lung Disease",
    "short": "SARD-ILD",
    "aliases": [
      "Systemic autoimmune rheumatic disease-associated interstitial lung disease",
      "SARD-ILD"
    ]
  },
  {
    "id": "recJ6HNmt8cvAkYL2",
    "canonical": "Heart Failure",
    "short": "HF",
    "aliases": []
  },
  {
    "id": "recJEOKMd1uPQINlB",
    "canonical": "Alopecia Areata",
    "short": "AA",
    "aliases": []
  },
  {
    "id": "recJFxMYVjdEFQxCe",
    "canonical": "Pneumococcal Disease",
    "short": "Pneumococcal",
    "aliases": [
      "invasive disease caused by Streptococcus pneumoniae",
      "pneumonia caused by Streptococcus pneumoniae"
    ]
  },
  {
    "id": "recJMsisYmtjr8tGo",
    "canonical": "Neuromyelitis Optica Spectrum Disorder",
    "short": "NMOSD",
    "aliases": []
  },
  {
    "id": "recJUXxRBzGh4NWUw",
    "canonical": "Growth Hormone Deficiency",
    "short": "GHD",
    "aliases": []
  },
  {
    "id": "recK5CuZ6EbAY5hEZ",
    "canonical": "Classical Hodgkin Lymphoma",
    "short": "cHL",
    "aliases": []
  },
  {
    "id": "recK7mRbEh48R90ht",
    "canonical": "Atopic Dermatitis",
    "short": "AD",
    "aliases": []
  },
  {
    "id": "recKdQBZftG6zmrYj",
    "canonical": "Kidney Transplant Antibody-Mediated Rejection",
    "short": "Kidney AMR",
    "aliases": []
  },
  {
    "id": "recKee2DvCLgLq6iW",
    "canonical": "Malignant Pleural Mesothelioma",
    "short": "MPM",
    "aliases": []
  },
  {
    "id": "recKf6IM8jo7WifQ3",
    "canonical": "Merkel Cell Carcinoma",
    "short": "MCC",
    "aliases": []
  },
  {
    "id": "recL4CnhAkwwOAeUJ",
    "canonical": "Hematologic Malignancies (Basket)",
    "short": "Heme Malignancies (Basket)",
    "aliases": []
  },
  {
    "id": "recLEQgCjJ5Fmefl8",
    "canonical": "Atrial Fibrillation",
    "short": "AF",
    "aliases": []
  },
  {
    "id": "recLLUUH8BdibV9oM",
    "canonical": "Congenital Adrenal Hyperplasia",
    "short": "CAH",
    "aliases": []
  },
  {
    "id": "recLW21syxYDfgznV",
    "canonical": "Hidradenitis Suppurativa",
    "short": "HS",
    "aliases": []
  },
  {
    "id": "recLlYgm5UUYIqRCm",
    "canonical": "Tenosynovial Giant Cell Tumor",
    "short": "TGCT",
    "aliases": []
  },
  {
    "id": "recLrzb0qao9LzT4E",
    "canonical": "Delayed Graft Function after Kidney Transplantation",
    "short": "DGF",
    "aliases": [
      "delayed graft function",
      "DGF",
      "delayed graft function after kidney transplantation"
    ]
  },
  {
    "id": "recLvQHjelSbVfSTX",
    "canonical": "Neuroblastoma",
    "short": "Neuroblastoma",
    "aliases": []
  },
  {
    "id": "recMOmy7JRCyX0QvU",
    "canonical": "Endometrial Cancer",
    "short": "EC",
    "aliases": []
  },
  {
    "id": "recMrofO1Y36RgJtX",
    "canonical": "Recurrent Calcium Oxalate Kidney Stone Disease",
    "short": "CaOx Kidney Stones",
    "aliases": [
      "Recurrent calcium oxalate kidney stone disease",
      "Calcium oxalate kidney stones",
      "Calcium oxalate nephrolithiasis",
      "Recurrent nephrolithiasis with elevated urinary oxalate"
    ]
  },
  {
    "id": "recMtPk9A392CxgrZ",
    "canonical": "Coronary Artery Disease",
    "short": "CAD",
    "aliases": [
      "Coronary artery disease"
    ]
  },
  {
    "id": "recN4Q8WBtlCoEE3j",
    "canonical": "Rheumatoid Arthritis",
    "short": "RA",
    "aliases": []
  },
  {
    "id": "recNHmEwp6AmbzxQ9",
    "canonical": "Allergic Fungal Rhinosinusitis",
    "short": "AFRS",
    "aliases": []
  },
  {
    "id": "recNrDsAI3sR76Wht",
    "canonical": "Irritable Bowel Syndrome",
    "short": "IBS",
    "aliases": []
  },
  {
    "id": "recO0O13r3P3P3SSZ",
    "canonical": "HLH/MAS in Still's Disease",
    "short": "HLH/MAS in Still's",
    "aliases": [
      "HLH/MAS in Still's disease",
      "Hemophagocytic lymphohistiocytosis/macrophage activation syndrome in Still's disease",
      "Macrophage activation syndrome in Still's disease",
      "HLH in Still's disease",
      "HLH/MAS in systemic juvenile idiopathic arthritis"
    ]
  },
  {
    "id": "recO4pFyeQ2NfpSBq",
    "canonical": "Chronic Gout",
    "short": "Gout",
    "aliases": []
  },
  {
    "id": "recO9bevLUJRY9p8U",
    "canonical": "Post-Bariatric Hypoglycemia",
    "short": "PBH",
    "aliases": []
  },
  {
    "id": "recOF9LMw9TO9ekGk",
    "canonical": "IgG4-Related Disease",
    "short": "IgG4-RD",
    "aliases": []
  },
  {
    "id": "recOh0smYfbRo0Cno",
    "canonical": "Generalized Myasthenia Gravis",
    "short": "gMG",
    "aliases": []
  },
  {
    "id": "recOtZfzTpJ0yIaqu",
    "canonical": "ANCA-Associated Vasculitis",
    "short": "AAV",
    "aliases": [
      "anti-neutrophil cytoplasmic autoantibody (ANCA)-associated vasculitis",
      "anti-neutrophil cytoplasmic autoantibodies associated vasculitides"
    ]
  },
  {
    "id": "recPxbZjs30UKx7qA",
    "canonical": "Fibrodysplasia Ossificans Progressiva",
    "short": "FOP",
    "aliases": []
  },
  {
    "id": "recQEpGFepI96XxJk",
    "canonical": "Renal Cell Carcinoma",
    "short": "RCC",
    "aliases": []
  },
  {
    "id": "recQTqeeeQMyMKnOY",
    "canonical": "Ovarian Cancer",
    "short": "OC",
    "aliases": [
      "epithelial ovarian, fallopian tube, or primary peritoneal cancer"
    ]
  },
  {
    "id": "recQbBti1a1dt50af",
    "canonical": "Allergic Rhinitis",
    "short": "AR",
    "aliases": []
  },
  {
    "id": "recQvzI9ZJFjPZREJ",
    "canonical": "Desmoid Tumor",
    "short": "Desmoid",
    "aliases": []
  },
  {
    "id": "recR4T8RPwLpozbhi",
    "canonical": "VEXAS Syndrome",
    "short": "VEXAS",
    "aliases": [
      "VEXAS",
      "VEXAS syndrome",
      "Vacuoles E1 enzyme X-linked autoinflammatory somatic syndrome"
    ]
  },
  {
    "id": "recRNPPKTHnNRTETp",
    "canonical": "Autoimmune Hemolytic Anemia",
    "short": "AIHA",
    "aliases": []
  },
  {
    "id": "recRNPVIxnRHjmIv6",
    "canonical": "Transthyretin Amyloidosis",
    "short": "ATTR",
    "aliases": []
  },
  {
    "id": "recRd5F7PDudKBmfh",
    "canonical": "Chemotherapy-Induced Nausea and Vomiting",
    "short": "CINV",
    "aliases": []
  },
  {
    "id": "recRgduhzxkSdfyu0",
    "canonical": "Colorectal Cancer",
    "short": "CRC",
    "aliases": []
  },
  {
    "id": "recS4It34OQCXW0cJ",
    "canonical": "Immune Thrombocytopenia",
    "short": "ITP",
    "aliases": []
  },
  {
    "id": "recS4uv0LmzMo9rxJ",
    "canonical": "Graves' Disease",
    "short": "Graves",
    "aliases": [
      "Graves disease",
      "Graves' disease"
    ]
  },
  {
    "id": "recS71s9u7gh91N2N",
    "canonical": "C3 Glomerulopathy",
    "short": "C3G",
    "aliases": [
      "Complement 3 glomerulopathy",
      "Complement 3 glomerulopathy (C3G)"
    ]
  },
  {
    "id": "recSDlinTwHgkC1hD",
    "canonical": "Chronic Graft-Versus-Host Disease",
    "short": "cGVHD",
    "aliases": []
  },
  {
    "id": "recSJQbM7fYJAtdjR",
    "canonical": "Uncomplicated Urinary Tract Infection",
    "short": "uUTI",
    "aliases": []
  },
  {
    "id": "recSli44UuFuvFALs",
    "canonical": "Primary Biliary Cholangitis",
    "short": "PBC",
    "aliases": []
  },
  {
    "id": "recSo4jvRDPsuKbCW",
    "canonical": "Primary Aldosteronism",
    "short": "PA",
    "aliases": [
      "primary aldosteronism",
      "PA",
      "primary hyperaldosteronism"
    ]
  },
  {
    "id": "recTEYfrNPRUUA1E2",
    "canonical": "Behçet's Disease",
    "short": "Behçet's",
    "aliases": []
  },
  {
    "id": "recTQGyAfsoRYFBIH",
    "canonical": "Spinocerebellar Ataxia Type 2",
    "short": "SCA2",
    "aliases": [
      "Spinocerebellar ataxia 2",
      "Spinocerebellar ataxia type 2"
    ]
  },
  {
    "id": "recTQI1sSQhcqa3Dt",
    "canonical": "Thymidine Kinase 2 Deficiency",
    "short": "TK2d",
    "aliases": []
  },
  {
    "id": "recTzfao19U4cCx2j",
    "canonical": "Hypertension",
    "short": "HTN",
    "aliases": []
  },
  {
    "id": "recUBeLORgwHD9wAA",
    "canonical": "Wet Age-Related Macular Degeneration",
    "short": "wAMD",
    "aliases": []
  },
  {
    "id": "recUGiD7yLFspEpRE",
    "canonical": "Polymyalgia Rheumatica",
    "short": "PMR",
    "aliases": []
  },
  {
    "id": "recUPtAPIalfu2JzL",
    "canonical": "Recurrent Pericarditis",
    "short": "Recurrent Pericarditis",
    "aliases": []
  },
  {
    "id": "recUUd6o7BrUC4aVN",
    "canonical": "Beta Thalassemia",
    "short": "β-thal",
    "aliases": [
      "Beta-thalassemia",
      "Transfusion-dependent beta-thalassemia",
      "Transfusion dependent beta thalassemia",
      "β-thalassemia",
      "Transfusion-dependent β-thalassemia",
      "TDT"
    ]
  },
  {
    "id": "recUm0OIP3vQZFV4P",
    "canonical": "COVID-19",
    "short": "COVID-19",
    "aliases": []
  },
  {
    "id": "recUn3w5X2ia0ORuq",
    "canonical": "Myotonic Dystrophy",
    "short": "DM",
    "aliases": []
  },
  {
    "id": "recUxY4VyFAA7gd36",
    "canonical": "Systemic Sclerosis",
    "short": "SSc",
    "aliases": []
  },
  {
    "id": "recV7xMCeHeiITTHH",
    "canonical": "Celiac Disease",
    "short": "Celiac",
    "aliases": []
  },
  {
    "id": "recV9AnsteLYHQjEm",
    "canonical": "Neurodegenerative Diseases (Basket)",
    "short": "",
    "aliases": [
      "Neurodegenerative Diseases"
    ]
  },
  {
    "id": "recVH7OKSiIIDZgtE",
    "canonical": "Stargardt Disease",
    "short": "Stargardt",
    "aliases": []
  },
  {
    "id": "recVLUaqRfLhYwKPW",
    "canonical": "Bipolar Disorder",
    "short": "BD",
    "aliases": [
      "Bipolar I Disorder",
      "Bipolar I or II Disorder"
    ]
  },
  {
    "id": "recVdfouLC4LIf8Rc",
    "canonical": "Acute Myeloid Leukemia",
    "short": "AML",
    "aliases": []
  },
  {
    "id": "recW2IiXDJSvOim3V",
    "canonical": "Respiratory Syncytial Virus Disease",
    "short": "RSV",
    "aliases": []
  },
  {
    "id": "recW4BFSrtHIRGhor",
    "canonical": "Blastic Plasmacytoid Dendritic Cell Neoplasm",
    "short": "BPDCN",
    "aliases": []
  },
  {
    "id": "recWe3PW9RKybb8PA",
    "canonical": "Psoriatic Arthritis",
    "short": "PsA",
    "aliases": []
  },
  {
    "id": "recWxHdvzrVw4NRZq",
    "canonical": "Central Disorders of Hypersomnolence (Basket)",
    "short": "CDH",
    "aliases": [
      "Central Hypersomnias"
    ]
  },
  {
    "id": "recX8szVoPFR4Y7CL",
    "canonical": "Hereditary Transthyretin Amyloidosis with Polyneuropathy (hATTR-PN)",
    "short": "hATTR-PN",
    "aliases": [
      "hATTR Amyloidosis with Polyneuropathy",
      "Hereditary ATTR amyloidosis with polyneuropathy",
      "Familial amyloidotic polyneuropathy",
      "Familial amyloid polyneuropathy",
      "ATTRv-PN",
      "vATTR-PN",
      "polyneuropathy of hereditary transthyretin-mediated amyloidosis"
    ]
  },
  {
    "id": "recXNA8UahVahAn3o",
    "canonical": "Neuropsychiatric Disorders (Basket)",
    "short": "",
    "aliases": [
      "Neuropsychiatric Disorders"
    ]
  },
  {
    "id": "recXWz8rO9rgicPvK",
    "canonical": "Invasive Aspergillosis",
    "short": "IA",
    "aliases": []
  },
  {
    "id": "recXkUozEiLsH9uLX",
    "canonical": "Metabolic Dysfunction-Associated Steatohepatitis",
    "short": "MASH",
    "aliases": [
      "noncirrhotic metabolic dysfunction-associated steatohepatitis",
      "nonalcoholic steatohepatitis",
      "NASH"
    ]
  },
  {
    "id": "recXoQKCAIrMOVzRt",
    "canonical": "Acute Hepatic Porphyria",
    "short": "AHP",
    "aliases": [
      "Acute Hepatic Porphyria (AHP)"
    ]
  },
  {
    "id": "recXq9kfuEPLSzZWD",
    "canonical": "Cytomegalovirus Infection",
    "short": "CMV",
    "aliases": []
  },
  {
    "id": "recXvFIVrwdTXCENY",
    "canonical": "Microscopic Colitis",
    "short": "Microscopic Colitis",
    "aliases": [
      "Microscopic colitis"
    ]
  },
  {
    "id": "recYCBJAid3iRheu9",
    "canonical": "Autism Spectrum Disorder",
    "short": "ASD",
    "aliases": [
      "Autism"
    ]
  },
  {
    "id": "recYSUDGYgZh0Tlky",
    "canonical": "HIV-1 Pre-Exposure Prophylaxis (PrEP)",
    "short": "HIV PrEP",
    "aliases": [
      "Pre-exposure prophylaxis of HIV-1 infection",
      "Pre-exposure prophylaxis for HIV-1 infection",
      "HIV-1 pre-exposure prophylaxis",
      "PrEP of HIV-1 infection",
      "pre-exposure prophylaxis (PrEP) to reduce the risk of sexually acquired HIV-1 infection",
      "pre-exposure prophylaxis (PrEP) to reduce the risk of sexually acquired HIV-1"
    ]
  },
  {
    "id": "recYaILZ8YegzISsP",
    "canonical": "Spinal Muscular Atrophy",
    "short": "SMA",
    "aliases": []
  },
  {
    "id": "recYbhClxBZN3cT9A",
    "canonical": "Vitiligo",
    "short": "Vitiligo",
    "aliases": []
  },
  {
    "id": "recYgUBU0acO59pSc",
    "canonical": "HIV-1 Infection",
    "short": "HIV-1",
    "aliases": []
  },
  {
    "id": "recYh0ZlCvMe0rNM1",
    "canonical": "Cytokine Release Syndrome",
    "short": "CRS",
    "aliases": [
      "Cytokine release syndrome",
      "CRS"
    ]
  },
  {
    "id": "recYnC6OpdhRIgvhY",
    "canonical": "Atherosclerotic Cardiovascular Disease",
    "short": "ASCVD",
    "aliases": []
  },
  {
    "id": "recYrQZRxES8BF5Xi",
    "canonical": "Chronic Myelomonocytic Leukemia",
    "short": "CMML",
    "aliases": [
      "Chronic myelomonocytic leukemia",
      "CMML"
    ]
  },
  {
    "id": "recZ7Y1MbKApmWcql",
    "canonical": "Multiple System Atrophy",
    "short": "MSA",
    "aliases": []
  },
  {
    "id": "recZDthC4XRo3TttS",
    "canonical": "Systemic Lupus Erythematosus",
    "short": "SLE",
    "aliases": []
  },
  {
    "id": "recZubkJQO0MyHAl3",
    "canonical": "Membranoproliferative Glomerulonephritis",
    "short": "MPGN",
    "aliases": []
  },
  {
    "id": "recZzgbXmq3DyUzDw",
    "canonical": "Dilated Cardiomyopathy",
    "short": "DCM",
    "aliases": [
      "dilated cardiomyopathy",
      "DCM",
      "R14del dilated cardiomyopathy",
      "BAG3-associated dilated cardiomyopathy"
    ]
  },
  {
    "id": "reca2XrzjuZmB35EU",
    "canonical": "Chronic Myeloid Leukemia",
    "short": "CML",
    "aliases": []
  },
  {
    "id": "recaJcoU9FedG6C9w",
    "canonical": "Alcohol Use Disorder",
    "short": "AUD",
    "aliases": []
  },
  {
    "id": "recaVLkz3HANhDeZZ",
    "canonical": "Chronic Inflammatory Demyelinating Polyneuropathy",
    "short": "CIDP",
    "aliases": []
  },
  {
    "id": "recahakfVQ1QSw32m",
    "canonical": "COVID-19 and Influenza (Basket)",
    "short": "",
    "aliases": [
      "Combination COVID-19 & Influenza",
      "COVID-19 & Influenza"
    ]
  },
  {
    "id": "recalPK8gzmTqOHpU",
    "canonical": "Hyperammonemia",
    "short": "Hyperammonemia",
    "aliases": []
  },
  {
    "id": "recamUUAra6WANxSd",
    "canonical": "APOL1-Mediated Kidney Disease",
    "short": "AMKD",
    "aliases": []
  },
  {
    "id": "recbdYP7GZpXYkPF1",
    "canonical": "Vasomotor Symptoms Associated with Menopause",
    "short": "VMS",
    "aliases": [
      "Vasomotor symptoms due to menopause",
      "Moderate to severe vasomotor symptoms due to menopause"
    ]
  },
  {
    "id": "recbumFIq1FqH6HUt",
    "canonical": "Cerebral Amyloid Angiopathy",
    "short": "CAA",
    "aliases": [
      "Cerebral Amyloid Angiopathy (CAA)"
    ]
  },
  {
    "id": "recbvDwaA5h7hU8Lx",
    "canonical": "Chronic Obstructive Pulmonary Disease",
    "short": "COPD",
    "aliases": []
  },
  {
    "id": "recbyi5SyGbTfG2UX",
    "canonical": "Diabetic Peripheral Neuropathic Pain",
    "short": "DPN Pain",
    "aliases": []
  },
  {
    "id": "recc9GTDn40mXsaDd",
    "canonical": "Ankylosing Spondylitis",
    "short": "AS",
    "aliases": []
  },
  {
    "id": "reccYgnm6gcnRAZVS",
    "canonical": "Acromegaly",
    "short": "Acromegaly",
    "aliases": []
  },
  {
    "id": "reccezBURUE0f9gGt",
    "canonical": "Prostate Cancer",
    "short": "PC",
    "aliases": []
  },
  {
    "id": "recciMu4KyWnYYPqt",
    "canonical": "Advanced Solid Tumours (Basket)",
    "short": "Solid Tumours (Basket)",
    "aliases": []
  },
  {
    "id": "reccm73wDy1Ek5yh7",
    "canonical": "Heart Failure with Reduced Ejection Fraction",
    "short": "HFrEF",
    "aliases": [
      "Chronic heart failure with reduced ejection fraction",
      "Heart failure with reduced ejection fraction",
      "HFrEF",
      "Chronic HFrEF"
    ]
  },
  {
    "id": "reccsbMFUaAIKjMWS",
    "canonical": "Hypoparathyroidism",
    "short": "HypoPT",
    "aliases": []
  },
  {
    "id": "reccvqThk3jotXHdE",
    "canonical": "Knee Osteoarthritis",
    "short": "Knee OA",
    "aliases": []
  },
  {
    "id": "recd1PtzXC2CjzWMK",
    "canonical": "Alzheimer's Disease",
    "short": "AD",
    "aliases": []
  },
  {
    "id": "recdNg7bZThwNNndS",
    "canonical": "Asthma",
    "short": "Asthma",
    "aliases": []
  },
  {
    "id": "recdXG57qOyYBjLkj",
    "canonical": "Esophageal Squamous Cell Carcinoma",
    "short": "ESCC",
    "aliases": []
  },
  {
    "id": "recejPT4FDDiVHfi2",
    "canonical": "Mesial Temporal Lobe Epilepsy",
    "short": "MTLE",
    "aliases": [
      "Mesial temporal lobe epilepsy",
      "Drug-resistant mesial temporal lobe epilepsy"
    ]
  },
  {
    "id": "receomlEXOryG5SmV",
    "canonical": "X-Linked Myotubular Myopathy",
    "short": "XLMTM",
    "aliases": []
  },
  {
    "id": "recerQfFplhTauqAJ",
    "canonical": "Pulmonary Arterial Hypertension",
    "short": "PAH",
    "aliases": []
  },
  {
    "id": "receuwTlFXK3QAzF7",
    "canonical": "Acne Vulgaris",
    "short": "Acne",
    "aliases": [
      "Acne",
      "Acne vulgaris"
    ]
  },
  {
    "id": "recevH2ETJJsnjM2P",
    "canonical": "Hypereosinophilic Syndrome",
    "short": "HES",
    "aliases": []
  },
  {
    "id": "recevvA9U1TTIs5nC",
    "canonical": "Extrapulmonary Neuroendocrine Carcinoma",
    "short": "EP-NEC",
    "aliases": []
  },
  {
    "id": "recf92DX7PfMsuuZI",
    "canonical": "Idiopathic Multicentric Castleman Disease",
    "short": "iMCD",
    "aliases": [
      "multicentric Castleman's disease",
      "multicentric Castleman disease"
    ]
  },
  {
    "id": "recfJcayOkW3QHoWD",
    "canonical": "Early Stage Breast Cancer",
    "short": "Early BC",
    "aliases": [
      "Early breast cancer",
      "Early-stage breast cancer",
      "high-risk early-stage triple-negative breast cancer"
    ]
  },
  {
    "id": "recfV3Go52R8qoRh8",
    "canonical": "Chronic Hepatitis B",
    "short": "CHB",
    "aliases": []
  },
  {
    "id": "recfWpmWGg9ejwubV",
    "canonical": "Chronic Urticaria",
    "short": "Chronic Urticaria",
    "aliases": [
      "Chronic urticaria"
    ]
  },
  {
    "id": "recg2BvUyyPF5jcBF",
    "canonical": "Gastrointestinal Stromal Tumor",
    "short": "GIST",
    "aliases": []
  },
  {
    "id": "recg3WiwTMCaRDrel",
    "canonical": "Autoimmune Hepatitis",
    "short": "AIH",
    "aliases": []
  },
  {
    "id": "recgBKToXRSNQh2pO",
    "canonical": "Cushing Syndrome",
    "short": "Cushing",
    "aliases": []
  },
  {
    "id": "recgfa6ZKoHPPyr5I",
    "canonical": "Human Papillomavirus-Related Disease",
    "short": "HPV",
    "aliases": []
  },
  {
    "id": "recgsLeLT73CaX1G1",
    "canonical": "Autosomal Dominant Polycystic Kidney Disease",
    "short": "ADPKD",
    "aliases": [
      "ADPKD",
      "autosomal dominant polycystic kidney disease"
    ]
  },
  {
    "id": "recgzwK6Mpp98zwgS",
    "canonical": "Cystinosis",
    "short": "Cystinosis",
    "aliases": []
  },
  {
    "id": "rechG8V0WfKVrld6T",
    "canonical": "Cystic Fibrosis",
    "short": "CF",
    "aliases": []
  },
  {
    "id": "rechKUfoSGIWeamFq",
    "canonical": "Infertility",
    "short": "Infertility",
    "aliases": []
  },
  {
    "id": "rechTJcIJGPlgBjHP",
    "canonical": "Glioblastoma",
    "short": "GBM",
    "aliases": [
      "Glioblastoma multiforme",
      "Glioblastoma",
      "GBM",
      "Recurrent glioblastoma"
    ]
  },
  {
    "id": "rechVG4oeT7IoqPSI",
    "canonical": "Metabolic Dysfunction-Associated Steatotic Liver Disease",
    "short": "MASLD",
    "aliases": [
      "Non-Alcoholic Fatty Liver Disease",
      "Nonalcoholic Fatty Liver Disease",
      "NAFLD"
    ]
  },
  {
    "id": "rechfSkThqypFT2ob",
    "canonical": "Urothelial Carcinoma",
    "short": "UCa",
    "aliases": [
      "Urothelial cancer",
      "BCG-naive high-risk non-muscle-invasive bladder cancer",
      "BCG-naïve high-risk non-muscle-invasive bladder cancer",
      "muscle invasive bladder cancer",
      "BCG-unresponsive non-muscle invasive bladder cancer"
    ]
  },
  {
    "id": "rechkxHT04uC2Lt0W",
    "canonical": "Serious Gram-Negative Infections",
    "short": "Gram-Negative Infection",
    "aliases": []
  },
  {
    "id": "rechqwnwSeFd71yo4",
    "canonical": "Invasive Mucormycosis",
    "short": "Mucormycosis",
    "aliases": []
  },
  {
    "id": "rechw5VfuHl726EeH",
    "canonical": "Alport Syndrome",
    "short": "Alport",
    "aliases": []
  },
  {
    "id": "reciAO9HLDFtpqsjg",
    "canonical": "Diabetic Retinopathy",
    "short": "DR",
    "aliases": []
  },
  {
    "id": "reciYSvjXagRYEPUA",
    "canonical": "Type 1 Diabetes",
    "short": "T1D",
    "aliases": []
  },
  {
    "id": "reciZSoJAL7XVm10d",
    "canonical": "PNPLA3 I148M Liver Disease",
    "short": "PNPLA3 I148M Liver Disease",
    "aliases": [
      "PNPLA3-associated liver disease",
      "PNPLA3 I148M liver disease"
    ]
  },
  {
    "id": "recixdSfo5zSSeSBq",
    "canonical": "Cutaneous Squamous Cell Carcinoma",
    "short": "cSCC",
    "aliases": []
  },
  {
    "id": "recj46ScMVcGpXOi0",
    "canonical": "Hereditary Hemorrhagic Telangiectasia",
    "short": "HHT",
    "aliases": [
      "Hereditary Hemorrhagic Telangiectasia"
    ]
  },
  {
    "id": "recjJS5cafsEbD8NI",
    "canonical": "Chronic Spontaneous Urticaria",
    "short": "CSU",
    "aliases": []
  },
  {
    "id": "recjKCMQ4tVpK4Q0Y",
    "canonical": "Meningococcal Disease",
    "short": "Meningococcal",
    "aliases": [
      "invasive disease caused by Neisseria meningitidis",
      "invasive meningococcal disease"
    ]
  },
  {
    "id": "recjKYpuKZoHTmuL3",
    "canonical": "Focal Segmental Glomerulosclerosis",
    "short": "FSGS",
    "aliases": []
  },
  {
    "id": "recjloFxdwlSC0cxu",
    "canonical": "Idiopathic Pulmonary Fibrosis",
    "short": "IPF",
    "aliases": []
  },
  {
    "id": "recjts9yZ2OCsU13T",
    "canonical": "Large B-Cell Lymphoma",
    "short": "LBCL",
    "aliases": []
  },
  {
    "id": "reckG76wv2Nc6MiUA",
    "canonical": "Multiple Sclerosis",
    "short": "MS",
    "aliases": []
  },
  {
    "id": "reckG9xqwOSuX9jxv",
    "canonical": "Postpartum Depression",
    "short": "PPD",
    "aliases": []
  },
  {
    "id": "reckuknVb4avAA2FX",
    "canonical": "Influenza",
    "short": "Flu",
    "aliases": []
  },
  {
    "id": "reclFSKtC8mHmMMJh",
    "canonical": "Congenital Myasthenic Syndromes",
    "short": "CMS",
    "aliases": [
      "Congenital myasthenic syndrome",
      "Congenital myasthenic syndromes"
    ]
  },
  {
    "id": "reclKGbIEBs1Ztfc7",
    "canonical": "Chemotherapy-Induced Thrombocytopenia",
    "short": "CIT",
    "aliases": []
  },
  {
    "id": "reclOV8MICwOPryFr",
    "canonical": "Retinal Vein Occlusion",
    "short": "RVO",
    "aliases": []
  },
  {
    "id": "reclRntw6S5eUZe6P",
    "canonical": "Liver Cirrhosis",
    "short": "Cirrhosis",
    "aliases": [
      "liver cirrhosis",
      "cirrhosis",
      "hepatic cirrhosis"
    ]
  },
  {
    "id": "reclSR4J5b2qhpAGJ",
    "canonical": "Ischemic Stroke and Transient Ischemic Attack",
    "short": "Stroke/TIA",
    "aliases": []
  },
  {
    "id": "reclVvuTvpWS8LwD4",
    "canonical": "Narcolepsy",
    "short": "Narcolepsy",
    "aliases": []
  },
  {
    "id": "recllbXJlbDKsqIwI",
    "canonical": "Duchenne Muscular Dystrophy",
    "short": "DMD",
    "aliases": []
  },
  {
    "id": "reclrdcNr9OpkQBnP",
    "canonical": "Mixed Hyperlipidemia",
    "short": "Mixed Hyperlipidemia",
    "aliases": [
      "Mixed hyperlipidaemia",
      "Mixed dyslipidemia",
      "Mixed dyslipidaemia"
    ]
  },
  {
    "id": "recmAJiXvfYL8tInZ",
    "canonical": "Primary Hyperoxaluria Type 1",
    "short": "PH1",
    "aliases": [
      "Primary Hyperoxaluria Type 1 (PH1)"
    ]
  },
  {
    "id": "recmHw7Oj7MBAbjX1",
    "canonical": "Warm Autoimmune Hemolytic Anemia",
    "short": "wAIHA",
    "aliases": []
  },
  {
    "id": "recmIpOcGCoBVZ14x",
    "canonical": "Hemophilia A and B (Basket)",
    "short": "",
    "aliases": [
      "Hemophilia A or B",
      "Hemophilia A or B with or without inhibitors"
    ]
  },
  {
    "id": "recmYcu1a5u1f7npJ",
    "canonical": "IgA Nephropathy",
    "short": "IgAN",
    "aliases": []
  },
  {
    "id": "recnBMY1L8Rp0yBAM",
    "canonical": "MDS and AML (Basket)",
    "short": "",
    "aliases": [
      "Myelodysplastic Syndrome and Acute Myeloid Leukemia",
      "Myelodysplastic Syndromes and Acute Myeloid Leukemia"
    ]
  },
  {
    "id": "recnK9rVBrjfshg91",
    "canonical": "Tourette Syndrome",
    "short": "TS",
    "aliases": []
  },
  {
    "id": "recnUUUgo5AqotQ83",
    "canonical": "Obstructive Sleep Apnea",
    "short": "OSA",
    "aliases": []
  },
  {
    "id": "recnVq40m8d9Bhv9T",
    "canonical": "Breast Cancer",
    "short": "BC",
    "aliases": []
  },
  {
    "id": "recnXX1eEGbyPLnW1",
    "canonical": "Generalized Anxiety Disorder",
    "short": "GAD",
    "aliases": []
  },
  {
    "id": "recndoeczH4t9VDDW",
    "canonical": "HER2-Positive Gastrointestinal Cancers (Basket)",
    "short": "",
    "aliases": [
      "HER2+ Gastrointestinal Cancers"
    ]
  },
  {
    "id": "recnf2FFoo2OaQfSL",
    "canonical": "Bone Metastases",
    "short": "Bone metastases",
    "aliases": []
  },
  {
    "id": "recnvHO5UOVZWRWuT",
    "canonical": "Cervical Cancer",
    "short": "Cervical Cancer",
    "aliases": [
      "cervical cancer",
      "locally advanced cervical cancer",
      "high-risk locally advanced cervical cancer"
    ]
  },
  {
    "id": "reco1Sof1Fzu24yhY",
    "canonical": "Alcohol-Related Liver Disease",
    "short": "ALD",
    "aliases": [
      "Alcohol-related liver disease",
      "Alcohol-associated liver disease",
      "Alcoholic liver disease"
    ]
  },
  {
    "id": "reco8V52mFzQkVUEG",
    "canonical": "Yellow Fever",
    "short": "YF",
    "aliases": []
  },
  {
    "id": "reco9JXIwAKt0YuMd",
    "canonical": "Hypophosphatasia",
    "short": "HPP",
    "aliases": []
  },
  {
    "id": "recoE89Tw0wCElUb9",
    "canonical": "Pancreatic Ductal Adenocarcinoma",
    "short": "PDAC",
    "aliases": [
      "adenocarcinoma of the pancreas",
      "pancreatic adenocarcinoma",
      "metastatic adenocarcinoma of the pancreas"
    ]
  },
  {
    "id": "recoW7mRopH8aAL6I",
    "canonical": "CDKL5 Deficiency Disorder",
    "short": "CDD",
    "aliases": []
  },
  {
    "id": "recoWfEdsivKTr6Y1",
    "canonical": "Primary Immunodeficiency",
    "short": "PID",
    "aliases": [
      "primary humoral immunodeficiency",
      "primary immunodeficiency (PI)"
    ]
  },
  {
    "id": "recobJdDjglDRLov9",
    "canonical": "Cardiovascular Risk Reduction",
    "short": "CV Risk Reduction",
    "aliases": []
  },
  {
    "id": "recoc6cItAirqtOXQ",
    "canonical": "Overactive Bladder",
    "short": "OAB",
    "aliases": []
  },
  {
    "id": "recp9SRKBCOpZ8Zku",
    "canonical": "Atrial Fibrillation and Venous Thromboembolism (Basket)",
    "short": "",
    "aliases": [
      "Atrial fibrillation and venous thromboembolism",
      "Stroke prevention in atrial fibrillation and treatment/prevention of venous thromboembolism"
    ]
  },
  {
    "id": "recpBrE7LR92Be9Rj",
    "canonical": "Tardive Dyskinesia",
    "short": "TD",
    "aliases": []
  },
  {
    "id": "recpD3CMKCKBNjcM7",
    "canonical": "Gonorrhea",
    "short": "GC",
    "aliases": []
  },
  {
    "id": "recpUwtKfXIomuIcX",
    "canonical": "Dravet Syndrome",
    "short": "DS",
    "aliases": []
  },
  {
    "id": "recphz4obhIOFXsbY",
    "canonical": "Interferon-gamma-driven Sepsis",
    "short": "IDS",
    "aliases": [
      "Interferon-gamma-driven sepsis",
      "IFN-gamma-driven sepsis",
      "IFNγ-driven sepsis",
      "IDS"
    ]
  },
  {
    "id": "recpmkMQaAVGLpe4z",
    "canonical": "Thrombotic Thrombocytopenic Purpura",
    "short": "TTP",
    "aliases": []
  },
  {
    "id": "recq6e8TGpuOMimJN",
    "canonical": "AL Amyloidosis",
    "short": "AL Amyloidosis",
    "aliases": []
  },
  {
    "id": "recq8w2wmfgjsS3hy",
    "canonical": "Ulcerative Colitis",
    "short": "UC",
    "aliases": []
  },
  {
    "id": "recqTQTf5vXD7yKrn",
    "canonical": "Non-Small Cell Lung Cancer",
    "short": "NSCLC",
    "aliases": []
  },
  {
    "id": "recqq3yK9uAzWxYYp",
    "canonical": "Atypical Hemolytic Uremic Syndrome",
    "short": "aHUS",
    "aliases": []
  },
  {
    "id": "recqxC8XO90SjpUVu",
    "canonical": "Myelodysplastic Syndromes",
    "short": "MDS",
    "aliases": []
  },
  {
    "id": "recs3Bl7qfRLO2Yoz",
    "canonical": "CHAPLE Disease",
    "short": "CHAPLE",
    "aliases": []
  },
  {
    "id": "recsI9hk6A1lwSncv",
    "canonical": "Gastroenteropancreatic Neuroendocrine Tumors",
    "short": "GEP-NET",
    "aliases": []
  },
  {
    "id": "recsd6lIZbUFd8bQi",
    "canonical": "Herpes Zoster",
    "short": "Shingles",
    "aliases": []
  },
  {
    "id": "recsjrKPlIBHEL7g1",
    "canonical": "Chronic Inducible Urticaria",
    "short": "CIndU",
    "aliases": []
  },
  {
    "id": "recslhRD7XfexxmVu",
    "canonical": "Systemic Mastocytosis",
    "short": "SM",
    "aliases": []
  },
  {
    "id": "recsqJsClxROXtz9s",
    "canonical": "Lennox-Gastaut Syndrome",
    "short": "LGS",
    "aliases": []
  },
  {
    "id": "recsxeyLaqv7oE6Px",
    "canonical": "Complicated Urinary Tract Infection",
    "short": "cUTI",
    "aliases": []
  },
  {
    "id": "rect2IEJt8V8La4R0",
    "canonical": "Sjögren's Disease",
    "short": "SjD",
    "aliases": []
  },
  {
    "id": "rect3wE2XMm7g59db",
    "canonical": "Rabies",
    "short": "Rabies",
    "aliases": []
  },
  {
    "id": "rect7EgAhitFCIPz1",
    "canonical": "Chlamydia Infection",
    "short": "Chlamydia",
    "aliases": [
      "Chlamydia",
      "Chlamydial infection"
    ]
  },
  {
    "id": "rectaQWBuRMZrdhCi",
    "canonical": "Chronic Pruritus",
    "short": "Chronic Pruritus",
    "aliases": []
  },
  {
    "id": "rectqIKrmxp5Jsibx",
    "canonical": "Human Metapneumovirus Infection",
    "short": "hMPV",
    "aliases": [
      "Human metapneumovirus infection",
      "hMPV infection",
      "hMPV"
    ]
  },
  {
    "id": "rectsoZ8Boqsdt0hm",
    "canonical": "MECP2 Duplication Syndrome",
    "short": "MECP2 Duplication Syndrome",
    "aliases": [
      "MECP2 duplication syndrome"
    ]
  },
  {
    "id": "recuA7HRlOEG52gCp",
    "canonical": "Cardiac Amyloidosis",
    "short": "Cardiac Amyloidosis",
    "aliases": []
  },
  {
    "id": "recuJGXgS9B6U9BPK",
    "canonical": "Severe Viral Lower Respiratory Tract Infection",
    "short": "Viral LRTI",
    "aliases": [
      "severe viral lower respiratory tract infection",
      "severe viral LRTI",
      "severe viral lower respiratory tract disease"
    ]
  },
  {
    "id": "recuLhrIMnnMHgBfT",
    "canonical": "Idiopathic Inflammatory Myopathies",
    "short": "IIM",
    "aliases": [
      "idiopathic inflammatory myopathies",
      "IIM",
      "myositis",
      "polymyositis",
      "dermatomyositis"
    ]
  },
  {
    "id": "recuMlLEFYT4rtG3u",
    "canonical": "Dermatomyositis and Polymyositis",
    "short": "DM/PM",
    "aliases": []
  },
  {
    "id": "recuPKR4sGXD3PLqt",
    "canonical": "Chronic Low Back Pain",
    "short": "CLBP",
    "aliases": []
  },
  {
    "id": "recv28Sjr2VFGofDN",
    "canonical": "Melanoma",
    "short": "Melanoma",
    "aliases": []
  },
  {
    "id": "recv3pvpAPgRT6MoE",
    "canonical": "Polycythemia Vera",
    "short": "PV",
    "aliases": []
  },
  {
    "id": "recvDf9YGugNtrnkf",
    "canonical": "Prolonged Seizures",
    "short": "SPS",
    "aliases": []
  },
  {
    "id": "recvKS8rKn0vFs1uE",
    "canonical": "Lupus Nephritis",
    "short": "LN",
    "aliases": []
  },
  {
    "id": "recvTteFdk80zrowJ",
    "canonical": "Stress Urinary Incontinence",
    "short": "SUI",
    "aliases": []
  },
  {
    "id": "recwKYLPWkI6OgtsP",
    "canonical": "Sickle Cell Disease",
    "short": "SCD",
    "aliases": []
  },
  {
    "id": "recwKlnsnHo0qhNgf",
    "canonical": "Type 2 Diabetes",
    "short": "T2D",
    "aliases": [
      "Type 2 Diabetes Mellitus"
    ]
  },
  {
    "id": "recwO9SExWolBy2AA",
    "canonical": "Gastric and Gastroesophageal Junction Adenocarcinoma",
    "short": "Gastric/GEJ",
    "aliases": [
      "Gastric or gastroesophageal junction adenocarcinoma",
      "Gastric adenocarcinoma",
      "Gastroesophageal junction adenocarcinoma",
      "gastric cancer, gastroesophageal junction cancer, and esophageal adenocarcinoma"
    ]
  },
  {
    "id": "recwVDSSuxRU2PX61",
    "canonical": "Diabetic Kidney Disease",
    "short": "DKD",
    "aliases": [
      "Diabetic Kidney Disease"
    ]
  },
  {
    "id": "recwXjfRf4wHkMHQi",
    "canonical": "Dengue",
    "short": "Dengue",
    "aliases": []
  },
  {
    "id": "recwYd8ELUyF5AIXn",
    "canonical": "Maple Syrup Urine Disease",
    "short": "MSUD",
    "aliases": []
  },
  {
    "id": "recwZzK30alpzEgZZ",
    "canonical": "Progressive Pulmonary Fibrosis",
    "short": "PPF",
    "aliases": [
      "Chronic fibrosing interstitial lung diseases with a progressive phenotype",
      "Chronic fibrosing ILD with a progressive phenotype",
      "Progressive fibrosing interstitial lung disease"
    ]
  },
  {
    "id": "recwuU1rPUgXPJ9Mu",
    "canonical": "Eosinophilic Granulomatosis with Polyangiitis",
    "short": "EGPA",
    "aliases": []
  },
  {
    "id": "recww06D3PDJ7X67L",
    "canonical": "Severe Hypertriglyceridemia",
    "short": "sHTG",
    "aliases": [
      "Severe hypertriglyceridaemia",
      "SHTG",
      "Severe HTG"
    ]
  },
  {
    "id": "recxHsoK1cGAO081B",
    "canonical": "Uveitic Macular Edema",
    "short": "UME",
    "aliases": []
  },
  {
    "id": "recxbb6lZoPHrkRmu",
    "canonical": "Propionic Acidemia",
    "short": "PA",
    "aliases": []
  },
  {
    "id": "recxpXRl47NiW1xsy",
    "canonical": "Head and Neck Squamous Cell Carcinoma",
    "short": "HNSCC",
    "aliases": [
      "Squamous cell carcinoma of the head and neck",
      "Head and neck squamous cell cancer"
    ]
  },
  {
    "id": "recxv5NFE2e99mLAo",
    "canonical": "Essential Thrombocythemia",
    "short": "ET",
    "aliases": []
  },
  {
    "id": "recxxslg9QL1iMa1v",
    "canonical": "Crohn's Disease",
    "short": "CD",
    "aliases": []
  },
  {
    "id": "recy52C4DhuxZ5VPi",
    "canonical": "Major Depressive Disorder",
    "short": "MDD",
    "aliases": []
  },
  {
    "id": "recyCbcwgJqqlHGts",
    "canonical": "Small Cell Lung Cancer",
    "short": "SCLC",
    "aliases": []
  },
  {
    "id": "recyL1kBw44ckYKaI",
    "canonical": "Hemophilia B",
    "short": "HB",
    "aliases": [
      "Hemophilia A or B"
    ]
  },
  {
    "id": "recyeJFj6mBTlAk0Q",
    "canonical": "Inherited Retinal Disease",
    "short": "IRD",
    "aliases": []
  },
  {
    "id": "recyiqdi7maBlvYPE",
    "canonical": "Contrast-Enhanced Magnetic Resonance Imaging",
    "short": "CE-MRI",
    "aliases": []
  },
  {
    "id": "recykz2eWwpCg8BPr",
    "canonical": "Obesity",
    "short": "Obesity",
    "aliases": [
      "Obesity & Weight Management"
    ]
  },
  {
    "id": "recyuueowAnwXGYVx",
    "canonical": "Hereditary Angioedema",
    "short": "HAE",
    "aliases": []
  },
  {
    "id": "reczLOuWtzbDwcOzN",
    "canonical": "Friedreich Ataxia",
    "short": "FA",
    "aliases": [
      "Friedreich's ataxia",
      "Friedreich’s ataxia"
    ]
  },
  {
    "id": "reczPWV4fg6xHUG5h",
    "canonical": "Venous Thromboembolism",
    "short": "VTE",
    "aliases": []
  },
  {
    "id": "reczPrXGpnRUnyvQI",
    "canonical": "Opioid Use Disorder",
    "short": "OUD",
    "aliases": []
  },
  {
    "id": "reczW6dL1aFq0TRGm",
    "canonical": "Nephrotic Syndrome",
    "short": "NS",
    "aliases": []
  },
  {
    "id": "reczbIEv6Cbee6SQH",
    "canonical": "Gastroesophageal Adenocarcinomas (Basket)",
    "short": "",
    "aliases": [
      "Gastroesophageal adenocarcinomas",
      "1L Gastroesophageal"
    ]
  }
]''')
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


def norm(v):
    text=unicodedata.normalize("NFKD",str(v or "").lower())
    text="".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+"," ",text).strip()


def source_variants(value):
    raw=str(value or "").strip()
    out={norm(raw)}
    # Remove a parenthetical acronym/abbreviation, not arbitrary clinical detail.
    stripped=re.sub(r"\s*\(([A-Za-z0-9+\-/]{2,12})\)\s*"," ",raw)
    out.add(norm(stripped))
    return {x for x in out if x}


def build_index():
    exact={}
    terms=[]
    ambiguous=set()
    for item in INDICATIONS:
        values=[item["canonical"],item.get("short",""),*(item.get("aliases") or [])]
        for raw in values:
            n=norm(raw)
            if not n:
                continue
            if n in exact and exact[n]["id"] != item["id"]:
                ambiguous.add(n)
            else:
                exact[n]=item
    for n in ambiguous:
        exact.pop(n,None)

    # Longer disease names/verified aliases first. Very short acronyms are used
    # only as standalone exact matches to avoid false containment.
    for n,item in exact.items():
        if len(n) >= 5:
            terms.append((len(n),n,item))
    terms.sort(reverse=True)
    return exact,terms


EXACT,TERMS=build_index()


def resolve_indication(raw):
    variants=source_variants(raw)
    hits=[]
    for v in variants:
        if v in EXACT:
            hits.append(("EXACT",EXACT[v]))
    unique={x[1]["id"]:x for x in hits}
    if len(unique)==1:
        return next(iter(unique.values()))

    source_norm=norm(raw)
    contained=[]
    padded=f" {source_norm} "
    for _,term,item in TERMS:
        if f" {term} " in padded:
            contained.append(item)
    by_id={x["id"]:x for x in contained}
    if len(by_id)==1:
        return ("CONTAINED_VERIFIED_TERM",next(iter(by_id.values())))

    # If multiple terms all resolve to the same canonical record, accept it.
    if contained and len({x["id"] for x in contained})==1:
        return ("CONTAINED_VERIFIED_TERM",contained[0])

    return ("UNRESOLVED",None)


async def main():
    source=await extract_generic_xlsx("GSK",URL,35.0)
    source_rows=[]
    resolution_counts=Counter()
    unresolved=[]
    resolved_samples=[]

    for row in source.rows:
        raw=row.get("indication") or ""
        method,item=resolve_indication(raw)
        resolution_counts[method]+=1
        canonical=item["canonical"] if item else raw

        if item:
            resolved_samples.append({
                "raw":raw,"canonical":canonical,"method":method,"recordId":item["id"]
            })
        else:
            unresolved.append({
                "asset":row.get("asset"),
                "developmentCode":row.get("developmentCode"),
                "rawIndication":raw,
                "phase":row.get("phase"),
                "mechanismOfAction":row.get("mechanismOfAction"),
            })

        source_rows.append(DiscoverySourceRow(
            company="GSK",
            sourceFamily="Company Pipeline",
            sourceRecordId=row.get("sourceRecordId"),
            sourceUrl=row.get("sourceUrl"),
            asset=row.get("asset"),
            molecule=row.get("molecule"),
            developmentCode=row.get("developmentCode"),
            brand=row.get("brand"),
            indication=canonical,
            phase=row.get("phase"),
            programStatus="Active",
            sponsorOwner="GSK",
            partners=row.get("partners") or [],
            strategicPhase1=False,
        ))

    compared=compare_discovery(DiscoveryCompareRequest(
        company="GSK",
        companyAliases=["GlaxoSmithKline"],
        sourceRows=source_rows,
        portfolioRows=[PortfolioSnapshotRow(**row) for row in PORTFOLIO_SNAPSHOT],
        batchRunId="GSK-XLSX-Q2-2026-CANONICAL-INDICATION-CANARY",
    ))

    samples={}
    for candidate in compared.candidates:
        samples.setdefault(candidate["classification"],[])
        if len(samples[candidate["classification"]])<6:
            samples[candidate["classification"]].append({
                "asset":candidate.get("asset"),
                "developmentCode":candidate.get("developmentCode"),
                "canonicalIndication":candidate.get("indication"),
                "phase":candidate.get("phase"),
                "matchMethod":candidate.get("matchMethod"),
                "existingPortfolioRecordIds":candidate.get("existingPortfolioRecordIds"),
            })

    print("GSK_CANONICAL_INDICATION_RECON " + json.dumps({
        "adapterReady":source.readyForDiscovery,
        "sourceRows":source.rowCount,
        "portfolioRows":len(PORTFOLIO_SNAPSHOT),
        "indicationCatalogSize":len(INDICATIONS),
        "resolutionCounts":dict(resolution_counts),
        "unresolvedCount":len(unresolved),
        "unresolved":unresolved[:20],
        "reconciliationSummary":compared.summary,
        "samples":samples,
        "resolvedSamples":resolved_samples[:12],
        "masterWrites":0,
    },ensure_ascii=False),flush=True)


if __name__=="__main__":
    asyncio.run(main())
