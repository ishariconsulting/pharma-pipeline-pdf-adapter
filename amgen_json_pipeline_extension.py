"""Read-only Amgen public pipeline JSON adapter.

Uses the machine-readable JSON endpoint used by the official Amgen pipeline
site. Produces one canonical row per structured molecule / indication / phase
combination. No Airtable or master-data writes.
"""
from __future__ import annotations

import html as html_lib
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import httpx
from fastapi import Header, HTTPException, Query
from pydantic import BaseModel

from main import _auth, app
from html_fetch_extension import _assert_public_http_url


ADAPTER_PROFILE = "PIPELINE_AMGEN_JSON_V1"
ROUTE_VERSION = "AMGEN_PIPELINE_JSON_V1.0_READ_ONLY"
MIN_ROWS = 4
MAX_BYTES = 5_000_000


class AmgenPipelineResponse(BaseModel):
    version: str
    routeVersion: str
    company: str
    sourceUrl: str
    finalUrl: str
    retrievalMode: str
    readOnly: bool
    readyForDiscovery: bool
    rowCount: int
    rows: List[Dict[str, Any]]
    summary: Dict[str, Any]
    issues: List[Dict[str, Any]]
    diagnostics: Dict[str, Any]
    guardrails: Dict[str, Any]


def clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def text_only(raw: Any) -> str:
    s = html_lib.unescape(str(raw or ""))
    s = re.sub(r"<br\s*/?>", " ", s, flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    return clean(s)


def canonical_phase(value: Any) -> str:
    n = clean(value).lower()
    if n in {"1", "phase 1", "phase i"}:
        return "Phase 1"
    if n in {"2", "phase 2", "phase ii"}:
        return "Phase 2"
    if n in {"3", "phase 3", "phase iii"}:
        return "Phase 3"
    if n in {"4", "phase 4", "phase iv"}:
        return "Phase 4"
    if "approved" in n:
        return "Approved"
    if "filed" in n or "registration" in n:
        return "Filed / Registration"
    return ""


def identity_parts(molecule_name_raw: Any, molecule_code_raw: Any) -> Dict[str, str]:
    molecule_name = text_only(molecule_name_raw)
    molecule_code = text_only(molecule_code_raw).strip("() ").strip()

    brand = ""
    if any(marker in str(molecule_name_raw or "") for marker in ("®", "&reg;", "™", "&trade;")):
        brand = clean(re.split(r"\(|\bformerly\b", molecule_name, maxsplit=1, flags=re.I)[0])

    development_code = ""
    combined = clean(molecule_name + " " + molecule_code)
    code_match = re.search(r"\b(?:AMG|ABP)[ -]?\d{2,4}\b", combined, flags=re.I)
    if code_match:
        development_code = clean(code_match.group(0).upper().replace("-", " "))

    molecule = molecule_code
    if molecule and re.fullmatch(r"(?:AMG|ABP)[ -]?\d{2,4}", molecule, flags=re.I):
        molecule = ""

    asset = brand or molecule_name or molecule or development_code
    return {
        "asset": asset,
        "brand": brand,
        "molecule": molecule,
        "developmentCode": development_code,
    }


async def extract_amgen_pipeline(
    company: str,
    source_url: str,
    timeout_seconds: float = 35.0,
) -> AmgenPipelineResponse:
    await _assert_public_http_url(source_url)
    parsed = urlparse(source_url)
    hostname = (parsed.hostname or "").lower()
    if not (hostname == "amgenpipeline.com" or hostname.endswith(".amgenpipeline.com")):
        raise HTTPException(status_code=400, detail="Amgen pipeline adapter requires an amgenpipeline.com source")

    if parsed.path.rstrip("/").lower().endswith("/pipeline/molecule/getjsondata"):
        endpoint = source_url
    else:
        endpoint = f"{parsed.scheme}://{parsed.netloc}/pipeline/molecule/getjsondata"

    await _assert_public_http_url(endpoint)
    headers = {
        "User-Agent": "Mozilla/5.0 AmgenPipelineAdapter/1.0",
        "Accept": "application/json,text/plain,*/*;q=0.8",
        "Referer": f"{parsed.scheme}://{parsed.netloc}/",
        "X-Requested-With": "XMLHttpRequest",
    }

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds, connect=12.0),
            follow_redirects=True,
            headers=headers,
        ) as client:
            response = await client.get(endpoint)
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="Amgen pipeline JSON timed out") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Amgen pipeline JSON fetch failed: {exc}") from exc

    if response.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Amgen pipeline endpoint returned HTTP {response.status_code}")
    if len(response.content) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="Amgen pipeline JSON exceeds size limit")

    final_url = str(response.url)
    await _assert_public_http_url(final_url)
    try:
        data = response.json()
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Amgen pipeline endpoint returned invalid JSON") from exc

    molecules = data.get("AmgenPiplines") if isinstance(data, dict) else None
    if not isinstance(molecules, list):
        raise HTTPException(status_code=422, detail="Amgen JSON does not contain AmgenPiplines[]")

    rows: List[Dict[str, Any]] = []
    rejected_pages = 0
    source_pages = 0
    source_indications = 0

    for molecule_index, item in enumerate(molecules, start=1):
        if not isinstance(item, dict):
            continue
        identity = identity_parts(item.get("MoleculeName"), item.get("MoleculeCode"))
        pages = item.get("Pages")
        if not isinstance(pages, list):
            continue

        for page_index, page in enumerate(pages, start=1):
            source_pages += 1
            if not isinstance(page, dict):
                rejected_pages += 1
                continue

            phase_obj = page.get("Phase") if isinstance(page.get("Phase"), dict) else {}
            phase = canonical_phase(phase_obj.get("HtmlString"))
            ta_obj = page.get("TherapeuticAreas") if isinstance(page.get("TherapeuticAreas"), dict) else {}
            therapeutic_area = text_only(ta_obj.get("HtmlString"))
            modality = text_only(page.get("Modality"))
            description = text_only(page.get("Description"))
            additional_info = text_only(page.get("AdditionalInformation"))

            indications = page.get("Indications")
            if not isinstance(indications, list) or not indications:
                indications = [{}]

            page_had_row = False
            for indication_index, indication_obj in enumerate(indications, start=1):
                indication = text_only(
                    indication_obj.get("HtmlString")
                    if isinstance(indication_obj, dict)
                    else indication_obj
                )
                if indication:
                    source_indications += 1

                if not identity["asset"] or not indication or not phase:
                    continue

                row = {
                    "company": company,
                    "sourceFamily": "Company Pipeline",
                    "sourceRecordId": f"amgen:{molecule_index}:{page_index}:{indication_index}",
                    "sourceUrl": final_url,
                    **identity,
                    "indication": indication,
                    "phase": phase,
                    "phaseEvidence": "SOURCE_JSON",
                    "programStatus": "Active",
                    "sponsorOwner": company,
                    "partners": [],
                    "study": "",
                    "trialIds": [],
                    "therapeuticArea": therapeutic_area,
                    "modality": modality,
                    "description": description,
                    "additionalInformation": additional_info,
                    "sourceOrdinal": len(rows) + 1,
                    "parserMethod": "AMGEN_PUBLIC_PIPELINE_JSON",
                    "sourceAdapter": ADAPTER_PROFILE,
                }
                rows.append(row)
                page_had_row = True

            if not page_had_row:
                rejected_pages += 1

    seen = set()
    deduped: List[Dict[str, Any]] = []
    exact_duplicates_removed = 0
    for row in rows:
        key = (
            clean(row["asset"]).lower(),
            clean(row["indication"]).lower(),
            clean(row["phase"]).lower(),
            clean(row["therapeuticArea"]).lower(),
        )
        if key in seen:
            exact_duplicates_removed += 1
            continue
        seen.add(key)
        row["sourceOrdinal"] = len(deduped) + 1
        deduped.append(row)

    issues: List[str] = []
    if len(deduped) < MIN_ROWS:
        issues.append(f"too few structured rows: {len(deduped)} < {MIN_ROWS}")
    if rejected_pages > max(3, int(max(1, source_pages) * 0.10)):
        issues.append(f"too many source pages missing core asset/indication/phase: {rejected_pages}")

    ready = not issues
    diagnostics = {
        "moleculeCount": len(molecules),
        "sourcePages": source_pages,
        "sourceIndications": source_indications,
        "parsedRows": len(deduped),
        "rejectedPages": rejected_pages,
        "exactDuplicatesRemoved": exact_duplicates_removed,
        "exactDuplicates": 0,
        "rowFailures": 0,
        "phaseUnresolved": 0,
        "boundaryWarnings": 0,
        "coverageWarnings": 0,
        "documentBytes": len(response.content),
        "companySpecificParserBranch": True,
        "portfolioDependentValidation": False,
        "writes": 0,
    }

    return AmgenPipelineResponse(
        version=ADAPTER_PROFILE,
        routeVersion=ROUTE_VERSION,
        company=company,
        sourceUrl=source_url,
        finalUrl=final_url,
        retrievalMode="EXTERNAL_HTTP",
        readOnly=True,
        readyForDiscovery=ready,
        rowCount=len(deduped),
        rows=deduped,
        summary={
            "structuralValidationPass": ready,
            "actual": {"Total": len(deduped)},
            "productionStatus": (
                "READY FOR AIRTABLE DELTA COMPARISON"
                if ready
                else "FAIL CLOSED - PARSER/STRUCTURE REVIEW REQUIRED"
            ),
            "selectedMethod": "AMGEN_PUBLIC_PIPELINE_JSON",
            "portfolioDependentValidation": False,
            "writeMode": "READ_ONLY",
        },
        issues=[{"issue": issue} for issue in issues],
        diagnostics=diagnostics,
        guardrails={
            "airtableWrites": False,
            "portfolioWrites": False,
            "masterDataWrites": False,
            "portfolioDependentValidation": False,
            "publicHttpOnly": True,
            "fuzzyIdentityResolution": False,
        },
    )


@app.get("/extract/amgen/json-pipeline/health")
async def amgen_health() -> Dict[str, Any]:
    return {
        "ok": True,
        "version": ADAPTER_PROFILE,
        "routeVersion": ROUTE_VERSION,
        "readOnly": True,
    }


@app.get("/extract/amgen/json-pipeline", response_model=AmgenPipelineResponse)
async def amgen_route(
    company: str = Query(default="Amgen", min_length=1, max_length=160),
    source_url: str = Query(default="https://www.amgenpipeline.com/", min_length=8),
    timeout_seconds: float = Query(default=35.0, ge=5.0, le=35.0),
    x_adapter_key: Optional[str] = Header(default=None),
) -> AmgenPipelineResponse:
    _auth(x_adapter_key)
    return await extract_amgen_pipeline(company, source_url, timeout_seconds)
