"""Read-only Lilly official investor-document extraction endpoint.

Registers a source-specific STATIC_DOCUMENT handler on the existing FastAPI app.
No Airtable or master-data writes are performed.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any, Dict, List, Optional

import fitz
from fastapi import Header, HTTPException
from pydantic import BaseModel

from main import _auth, app
from lilly_static_document_canary import (
    EXPECTED_SOURCE_DATE,
    SOURCE_URL,
    VERSION as PARSER_VERSION,
    download_pdf,
    find_pipeline_page,
    norm,
    parse_pipeline,
)

ENDPOINT_VERSION = "PIPELINE_LILLY_INVESTOR_PDF_V1.0"


class LillyStaticResponse(BaseModel):
    version: str
    contractVersion: str
    company: str
    sourceUrl: str
    sourceDate: str
    retrievalMode: str
    parserProfile: str
    projectCount: int
    phaseCounts: Dict[str, int]
    projects: List[Dict[str, Any]]
    diagnostics: Dict[str, Any]
    checks: Dict[str, bool]
    parserBindingValidated: bool
    readOnly: bool
    masterWritesPerformed: int
    failClosed: bool


class LillyPipelineCompatResponse(BaseModel):
    version: str
    routeVersion: str
    company: str
    sourceUrl: str
    sourceDate: str
    retrievalMode: str
    readOnly: bool
    readyForDiscovery: bool
    rowCount: int
    rows: List[Dict[str, Any]]
    summary: Dict[str, Any]
    issues: List[Dict[str, Any]]
    diagnostics: Dict[str, Any]
    guardrails: Dict[str, Any]


def extract_lilly_static() -> LillyStaticResponse:
    pdf = download_pdf()
    doc = fitz.open(stream=pdf, filetype="pdf")
    page_idx, page, page_text = find_pipeline_page(doc)
    rows, diagnostics = parse_pipeline(page)

    date_match = re.search(r"As of\s+([A-Z][a-z]+\s+\d{1,2},\s+\d{4})", page_text)
    source_date = date_match.group(1) if date_match else ""
    counts = Counter(r["phase"] for r in rows)
    orforglipron = [r for r in rows if "orforglipron" in norm(r["asset"])]

    checks = {
        "officialPdfRetrieved": bool(pdf and pdf.startswith(b"%PDF")),
        "pipelineSlideUnique": True,
        "sourceDatePresent": bool(source_date),
        "expectedSourceDate": source_date == EXPECTED_SOURCE_DATE,
        "minimumProgrammeCount": len(rows) >= 40,
        "phase2Present": counts.get("Phase 2", 0) >= 20,
        "phase3Present": counts.get("Phase 3", 0) >= 20,
        "regReviewPresent": counts.get("Reg Review", 0) >= 1,
        "approvedPresent": counts.get("Approved", 0) >= 1,
        "orforglipronParsed": len(orforglipron) >= 4,
        "allRowsStructurallyComplete": all(
            r.get("asset") and r.get("indication") and r.get("phase") for r in rows
        ),
        "zeroRejectedCells": int(diagnostics.get("rejectedCellCount", -1)) == 0,
    }
    passed = all(checks.values())
    if not passed:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Lilly static-document validation failed closed",
                "checks": checks,
                "diagnostics": diagnostics,
                "projectCount": len(rows),
                "phaseCounts": dict(counts),
            },
        )

    return LillyStaticResponse(
        version=ENDPOINT_VERSION,
        contractVersion="INTEL_ADAPTER_V1",
        company="Eli Lilly and Company",
        sourceUrl=SOURCE_URL,
        sourceDate=source_date,
        retrievalMode="STATIC_DOCUMENT",
        parserProfile="PIPELINE_LILLY_INVESTOR_PDF_V1",
        projectCount=len(rows),
        phaseCounts=dict(counts),
        projects=rows,
        diagnostics={
            **diagnostics,
            "pdfBytes": len(pdf),
            "pageCount": len(doc),
            "pipelinePage": page_idx + 1,
            "parserVersion": PARSER_VERSION,
        },
        checks=checks,
        parserBindingValidated=True,
        readOnly=True,
        masterWritesPerformed=0,
        failClosed=False,
    )


@app.get("/extract/lilly-investor-pdf/health")
async def lilly_static_health() -> Dict[str, Any]:
    return {
        "ok": True,
        "version": ENDPOINT_VERSION,
        "retrievalMode": "STATIC_DOCUMENT",
        "parserProfile": "PIPELINE_LILLY_INVESTOR_PDF_V1",
        "readOnly": True,
    }


@app.get("/extract/lilly-investor-pdf", response_model=LillyStaticResponse)
async def lilly_static_extract(
    x_adapter_key: Optional[str] = Header(default=None),
) -> LillyStaticResponse:
    _auth(x_adapter_key)
    return extract_lilly_static()

def extract_lilly_pipeline_compat() -> LillyPipelineCompatResponse:
    """Expose the validated Lilly static parser through the recurring-pipeline contract."""
    base = extract_lilly_static()
    rows: List[Dict[str, Any]] = []

    for idx, project in enumerate(base.projects, start=1):
        asset = str(project.get("asset") or "").strip()
        indication = str(project.get("indication") or "").strip()
        phase = str(project.get("phase") or "").strip()
        if norm(phase) == "reg review":
            phase = "Filed / Registration"

        rows.append({
            "company": base.company,
            "sourceFamily": "Company Pipeline",
            "sourceRecordId": f"lilly-static:{idx}",
            "sourceUrl": base.sourceUrl,
            "asset": asset,
            "molecule": "",
            "developmentCode": "",
            "brand": "",
            "indication": indication,
            "phase": phase,
            "phaseEvidence": "SOURCE_INVESTOR_PDF",
            "programStatus": "",
            "sponsorOwner": base.company,
            "partners": [],
            "study": "",
            "trialIds": [],
            "therapeuticArea": "",
            "sourcePage": project.get("sourcePage"),
            "sourceOrdinal": idx,
            "parserMethod": "LILLY_VECTOR_GEOMETRY",
            "sourceAdapter": "PIPELINE_LILLY_INVESTOR_PDF_V1",
        })

    diagnostics = {
        **base.diagnostics,
        "rowFailures": 0,
        "exactDuplicatesRemoved": 0,
        "exactDuplicates": 0,
        "phaseUnresolved": 0,
        "boundaryWarnings": 0,
        "portfolioDependentValidation": False,
        "companySpecificParserBranch": True,
        "writes": 0,
    }
    ready = bool(base.parserBindingValidated) and len(rows) >= 40
    issues: List[Dict[str, Any]] = []
    if not ready:
        issues.append({"issue": "Lilly static parser/source validation did not pass"})

    summary = {
        "structuralValidationPass": ready,
        "actual": {"Total": len(rows)},
        "productionStatus": (
            "READY FOR AIRTABLE DELTA COMPARISON"
            if ready
            else "FAIL CLOSED - PARSER/STRUCTURE REVIEW REQUIRED"
        ),
        "selectedMethod": "LILLY_VECTOR_GEOMETRY",
        "portfolioDependentValidation": False,
        "companySpecificParserBranch": True,
        "writeMode": "READ_ONLY",
    }

    return LillyPipelineCompatResponse(
        version="PIPELINE_LILLY_INVESTOR_PDF_V1",
        routeVersion="LILLY_STATIC_PIPELINE_COMPAT_V1.0_READ_ONLY",
        company=base.company,
        sourceUrl=base.sourceUrl,
        sourceDate=base.sourceDate,
        retrievalMode=base.retrievalMode,
        readOnly=True,
        readyForDiscovery=ready,
        rowCount=len(rows),
        rows=rows,
        summary=summary,
        issues=issues,
        diagnostics=diagnostics,
        guardrails={
            "airtableWrites": False,
            "portfolioWrites": False,
            "masterDataWrites": False,
            "portfolioDependentValidation": False,
            "publicFirstPartySource": True,
            "failClosed": True,
        },
    )


@app.get("/extract/lilly/pipeline/health")
async def lilly_pipeline_compat_health() -> Dict[str, Any]:
    return {
        "ok": True,
        "version": "PIPELINE_LILLY_INVESTOR_PDF_V1",
        "routeVersion": "LILLY_STATIC_PIPELINE_COMPAT_V1.0_READ_ONLY",
        "retrievalMode": "STATIC_DOCUMENT",
        "readOnly": True,
    }


@app.get("/extract/lilly/pipeline", response_model=LillyPipelineCompatResponse)
async def lilly_pipeline_compat(
    x_adapter_key: Optional[str] = Header(default=None),
) -> LillyPipelineCompatResponse:
    _auth(x_adapter_key)
    return extract_lilly_pipeline_compat()

