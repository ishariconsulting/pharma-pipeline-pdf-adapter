"""AstraZeneca source-specific pipeline adapter in the common discovery contract.

This route wraps the already validated AstraZeneca V1.4 parser behind the same
read-only response contract consumed by Portfolio Discovery Worker V1.4.

Why this exists:
- AstraZeneca's official pipeline page is structurally richer than the generic
  HTML pipeline pattern.
- The dedicated parser already understands AstraZeneca therapy-area/phase
  boundaries and study-token formatting.
- Downstream Airtable logic remains company-agnostic because this route emits
  the same common contract as other pipeline adapters.

No Airtable or master-data writes are performed here.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import Header, HTTPException, Query

from main import _auth, app
from generic_pipeline_extension import GenericPipelineExtractionResponse
import astrazeneca_pipeline_adapter as az
import astrazeneca_pipeline_adapter_v13  # noqa: F401 - parser hygiene patches
import astrazeneca_pipeline_adapter_v14  # noqa: F401 - case-safe study repair


ADAPTER_PROFILE = "PIPELINE_ASTRAZENECA_HTML_V1.4"
ROUTE_VERSION = "ASTRAZENECA_COMMON_CONTRACT_V1.0"
OFFICIAL_SOURCE_URL = az.AZ_PIPELINE_URL


def _norm(value: str) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _source_url_ok(source_url: str) -> bool:
    return source_url.rstrip("/") == OFFICIAL_SOURCE_URL.rstrip("/")


@app.get(
    "/extract/astrazeneca/pipeline",
    response_model=GenericPipelineExtractionResponse,
)
async def extract_astrazeneca_pipeline_common_contract(
    company: str = Query(..., min_length=1, max_length=160),
    source_url: str = Query(..., min_length=8),
    timeout_seconds: float = Query(default=35.0, ge=5.0, le=35.0),
    x_adapter_key: Optional[str] = Header(default=None),
) -> GenericPipelineExtractionResponse:
    _auth(x_adapter_key)

    if _norm(company) not in {"astrazeneca", "astrazeneca plc"}:
        raise HTTPException(
            status_code=400,
            detail="This source-specific adapter is restricted to AstraZeneca.",
        )

    if not _source_url_ok(source_url):
        raise HTTPException(
            status_code=400,
            detail="Unexpected AstraZeneca pipeline source URL.",
        )

    # timeout_seconds is accepted to preserve the common worker contract.
    # The validated AZ parser owns its bounded public-source fetch settings.
    _ = timeout_seconds

    raw_html = await az._fetch_source_html()
    all_rows = az.parse_pipeline_html(raw_html)

    selected = [
        row
        for row in all_rows
        if row.commercialInScope and not row.removedSinceLastQuarter
    ]

    row_payloads = []
    row_issues = []

    for row in selected:
        asset = (
            row.asset
            or row.brand
            or row.molecule
            or row.developmentCode
            or ""
        ).strip()
        indication = (row.indication or "").strip()
        phase = (row.phase or "").strip()

        missing = [
            name
            for name, value in (
                ("asset", asset),
                ("indication", indication),
                ("phase", phase),
            )
            if not value
        ]

        if missing:
            row_issues.append(
                {
                    "issue": (
                        f"{row.sourceRecordId}: missing core fields "
                        + ", ".join(missing)
                    )
                }
            )

        row_payloads.append(
            {
                "sourceRecordId": row.sourceRecordId,
                "sourceCardOrdinal": row.sourceRecordId,
                "asset": asset,
                "molecule": row.molecule or "",
                "developmentCode": row.developmentCode or "",
                "brand": row.brand or "",
                "indication": indication,
                "phase": phase,
                "therapeuticArea": row.therapyArea or "",
                "modality": "",
                "description": row.programText or "",
                "additionalInformation": (
                    f"Source as of {row.sourceAsOf}"
                    if row.sourceAsOf
                    else ""
                ),
                "study": "",
                "trialIds": [],
                "programStatus": "Active",
                "sponsorOwner": "AstraZeneca",
                "partners": [],
                "sourceUrl": OFFICIAL_SOURCE_URL,
                "sourceAdapter": ADAPTER_PROFILE,
                "sourceTherapeuticArea": row.therapyArea or "",
            }
        )

    structural_pass = (
        len(row_payloads) >= 4
        and len(row_issues) == 0
    )

    issues = list(row_issues)
    if len(row_payloads) < 4:
        issues.append(
            {
                "issue": (
                    f"too few structured rows: {len(row_payloads)} < 4"
                )
            }
        )

    diagnostics: Dict[str, Any] = {
        "selectedMethod": "ASTRAZENECA_SOURCE_SPECIFIC_V1.4",
        "rowFailures": len(row_issues),
        "boundaryWarnings": 0,
        "coverageWarnings": 0,
        "sourceParsedRows": len(all_rows),
        "commercialInScopeRows": len(row_payloads),
        "retrievalMode": "DIRECT",
        "routingReason": "SOURCE_SPECIFIC_ADAPTER",
        "portfolioDependentValidation": False,
    }

    summary: Dict[str, Any] = {
        "structuralValidationPass": structural_pass,
        "actual": {"Total": len(row_payloads)},
        "productionStatus": (
            "READY FOR AIRTABLE DELTA COMPARISON"
            if structural_pass
            else "FAIL CLOSED - SOURCE-SPECIFIC PARSER REVIEW REQUIRED"
        ),
        "selectedMethod": diagnostics["selectedMethod"],
        "retrievalMode": "DIRECT",
        "routingReason": "SOURCE_SPECIFIC_ADAPTER",
        "portfolioDependentValidation": False,
        "companySpecificParserBranch": True,
        "writeMode": "READ_ONLY",
    }

    validation = {
        "pass": structural_pass,
        "issues": [item["issue"] for item in issues],
    }

    return GenericPipelineExtractionResponse(
        version=ADAPTER_PROFILE,
        routeVersion=ROUTE_VERSION,
        interpreterVersion=az.AZ_PIPELINE_VERSION,
        company="AstraZeneca",
        sourceUrl=OFFICIAL_SOURCE_URL,
        finalUrl=OFFICIAL_SOURCE_URL,
        sourceDate=None,
        readOnly=True,
        readyForDiscovery=structural_pass,
        rowCount=len(row_payloads),
        rows=row_payloads,
        summary=summary,
        issues=issues,
        diagnostics=diagnostics,
        validation=validation,
        guardrails={
            "airtableWrites": False,
            "portfolioWrites": False,
            "masterDataWrites": False,
            "companySpecificParserBranch": True,
            "portfolioDependentValidation": False,
            "publicHttpOnly": True,
            "ssrfGuard": True,
            "fuzzyIdentityResolution": False,
            "sourceRestricted": True,
        },
    )


@app.get("/extract/astrazeneca/pipeline/health")
async def extract_astrazeneca_pipeline_health() -> Dict[str, Any]:
    return {
        "ok": True,
        "version": ADAPTER_PROFILE,
        "routeVersion": ROUTE_VERSION,
        "parserVersion": az.AZ_PIPELINE_VERSION,
        "readOnly": True,
        "sourceUrl": OFFICIAL_SOURCE_URL,
        "writeMode": "READ_ONLY",
    }
