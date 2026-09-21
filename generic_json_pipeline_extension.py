"""Reusable read-only semantic JSON pipeline-table adapter.

Accepts a public JSON source that exposes a list of pipeline records either at
the root or under a semantic container such as records/items/results/data.
Field mapping is inferred from source keys and optional column metadata. The
adapter does not use company-specific parser branches or existing Portfolio
state and performs no Airtable/master-data writes.
"""
from __future__ import annotations

import html as html_lib
import json
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import httpx
from fastapi import Header, HTTPException, Query
from pydantic import BaseModel

from main import _auth, app
from html_fetch_extension import _assert_public_http_url


ADAPTER_PROFILE = "PIPELINE_GENERIC_JSON_TABLE_V1"
ROUTE_VERSION = "GENERIC_JSON_PIPELINE_TABLE_V1.0_READ_ONLY"
MAX_BYTES = 8_000_000
MIN_ROWS = 4

ASSET_KEYS = (
    "asset", "name", "drug_name", "drugname", "compound", "molecule",
    "program", "programme", "product", "candidate", "medicine",
)
INDICATION_KEYS = (
    "indication", "investigational_indication", "investigational indication",
    "desc", "disease", "disease_indication", "condition",
)
PHASE_KEYS = (
    "phase", "stage", "development_stage", "developmentstage",
    "development stage", "clinical_phase", "clinicalphase",
)
TA_KEYS = (
    "therapeutic_area", "therapeuticarea", "therapeutic area",
    "therapy_area", "disease-areas", "disease_area", "diseasearea",
)
PARTNER_KEYS = ("partner", "partners", "collaboration", "collaborator", "licensee")
TARGET_KEYS = ("target", "generic", "mechanism", "mechanism_of_action", "mechanismofaction")
CODE_KEYS = (
    "development_code", "developmentcode", "code", "project_code",
    "program_code", "programme_code",
)
BRAND_KEYS = ("brand", "brand_name", "brandname")


class GenericJsonPipelineResponse(BaseModel):
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
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return re.sub(r"\s+", " ", json.dumps(value, ensure_ascii=False)).strip()
    text = html_lib.unescape(str(value))
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def norm_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").lower()).strip("_")


def canonical_phase(value: Any) -> str:
    raw = clean(value)
    n = raw.lower()
    if not n:
        return ""
    if "approved" in n or "marketed" in n:
        return "Approved"
    if any(x in n for x in ("filed", "registration", "regulatory review", "under review")):
        return "Filed / Registration"
    if "preclinical" in n or "pre-clinical" in n:
        return "Preclinical"

    # Prefer the highest explicit phase in combination labels such as Phase 1/2.
    matches = re.findall(r"\b(?:phase\s*)?(i{1,3}|iv|[1-4])\b", n, flags=re.I)
    if matches:
        values = []
        roman = {"i": 1, "ii": 2, "iii": 3, "iv": 4}
        for token in matches:
            token = token.lower()
            values.append(int(token) if token.isdigit() else roman.get(token, 0))
        values = [v for v in values if v]
        if values:
            return f"Phase {max(values)}"

    class_match = re.search(r"phase[-_ ]?(one|two|three|four)", n)
    if class_match:
        mapping = {"one": 1, "two": 2, "three": 3, "four": 4}
        return f"Phase {mapping[class_match.group(1)]}"
    return ""


def _find_key(record: Dict[str, Any], candidates: Tuple[str, ...]) -> Optional[str]:
    keyed = {norm_key(k): k for k in record.keys()}
    for candidate in candidates:
        n = norm_key(candidate)
        if n in keyed:
            return keyed[n]
    return None


def _column_aliases(payload: Any) -> Dict[str, str]:
    aliases: Dict[str, str] = {}
    if not isinstance(payload, dict):
        return aliases
    cols = payload.get("columns")
    if not isinstance(cols, list):
        return aliases
    for col in cols:
        if not isinstance(col, dict):
            continue
        source_key = clean(col.get("values") or col.get("value") or col.get("key"))
        label = clean(col.get("label") or col.get("name") or col.get("title"))
        if source_key and label:
            aliases[norm_key(label)] = source_key
    return aliases


def _records_container(payload: Any) -> Tuple[List[Dict[str, Any]], str]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)], "ROOT_LIST"
    if not isinstance(payload, dict):
        return [], "UNSUPPORTED_ROOT"

    for key in ("records", "items", "results", "data", "pipeline", "programmes", "programs"):
        value = payload.get(key)
        if isinstance(value, list) and value and all(isinstance(x, dict) for x in value):
            return value, key
        if isinstance(value, dict):
            for nested_key in ("records", "items", "results", "data"):
                nested = value.get(nested_key)
                if isinstance(nested, list) and nested and all(isinstance(x, dict) for x in nested):
                    return nested, f"{key}.{nested_key}"
    return [], "NOT_FOUND"


def _field_value(record: Dict[str, Any], candidates: Tuple[str, ...], aliases: Dict[str, str]) -> Tuple[str, Optional[str]]:
    # First use exact semantic record keys.
    key = _find_key(record, candidates)
    if key is not None:
        return clean(record.get(key)), key

    # Then use source-declared column labels mapped to record keys.
    for candidate in candidates:
        alias_key = aliases.get(norm_key(candidate))
        if alias_key:
            actual = _find_key(record, (alias_key,))
            if actual is not None:
                return clean(record.get(actual)), actual
    return "", None


def _partners(value: Any) -> List[str]:
    if value is None or value is False:
        return []
    if isinstance(value, list):
        return [clean(x) for x in value if clean(x)]
    if isinstance(value, dict):
        return [clean(x) for x in value.values() if clean(x)]
    text = clean(value)
    if not text or text.lower() in {"false", "none", "no"}:
        return []
    return [text]


def parse_semantic_json(company: str, source_url: str, payload: Any) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    records, container = _records_container(payload)
    aliases = _column_aliases(payload)
    parsed: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []
    mappings: Dict[str, Dict[str, int]] = {
        "asset": {}, "indication": {}, "phase": {}, "therapeuticArea": {},
    }

    for idx, record in enumerate(records, start=1):
        asset, asset_key = _field_value(record, ASSET_KEYS, aliases)
        indication, indication_key = _field_value(record, INDICATION_KEYS, aliases)
        phase_raw, phase_key = _field_value(record, PHASE_KEYS, aliases)
        ta, ta_key = _field_value(record, TA_KEYS, aliases)
        target, _ = _field_value(record, TARGET_KEYS, aliases)
        development_code, _ = _field_value(record, CODE_KEYS, aliases)
        brand, _ = _field_value(record, BRAND_KEYS, aliases)
        partner_key = _find_key(record, PARTNER_KEYS)
        ph = canonical_phase(phase_raw)

        for label, key in (
            ("asset", asset_key), ("indication", indication_key),
            ("phase", phase_key), ("therapeuticArea", ta_key),
        ):
            if key:
                mappings[label][key] = mappings[label].get(key, 0) + 1

        if not asset or not indication or not ph:
            rejected.append({
                "ordinal": idx,
                "asset": asset,
                "indication": indication,
                "phaseRaw": phase_raw,
                "missing": [
                    label for label, value in (
                        ("asset", asset), ("indication", indication), ("phase", ph)
                    ) if not value
                ],
            })
            continue

        parsed.append({
            "company": company,
            "sourceFamily": "Company Pipeline",
            "sourceRecordId": f"json:{idx}",
            "sourceUrl": source_url,
            "asset": asset,
            "molecule": asset if not development_code else "",
            "developmentCode": development_code,
            "brand": brand,
            "indication": indication,
            "phase": ph,
            "phaseEvidence": "SOURCE_JSON",
            "programStatus": "Active",
            "sponsorOwner": company,
            "partners": _partners(record.get(partner_key)) if partner_key else [],
            "study": "",
            "trialIds": [],
            "therapeuticArea": ta,
            "target": target,
            "sourceOrdinal": len(parsed) + 1,
            "parserMethod": "GENERIC_SEMANTIC_JSON_TABLE",
            "sourceAdapter": ADAPTER_PROFILE,
        })

    # Exact source-grain dedupe only.
    deduped: List[Dict[str, Any]] = []
    seen = set()
    duplicate_count = 0
    for row in parsed:
        key = (
            row["asset"].lower(),
            row["indication"].lower(),
            row["phase"].lower(),
            row["therapeuticArea"].lower(),
        )
        if key in seen:
            duplicate_count += 1
            continue
        seen.add(key)
        row["sourceOrdinal"] = len(deduped) + 1
        deduped.append(row)

    diagnostics = {
        "container": container,
        "sourceRecordCount": len(records),
        "parsedRows": len(deduped),
        "rejectedRows": len(rejected),
        "rejectedSamples": rejected[:12],
        "exactDuplicatesRemoved": duplicate_count,
        "fieldMappings": mappings,
        "columnAliases": aliases,
        "companySpecificParserBranch": False,
        "portfolioDependentValidation": False,
        "writes": 0,
    }
    return deduped, diagnostics


async def _download_json(url: str, timeout_seconds: float) -> Tuple[Any, str, int, str]:
    await _assert_public_http_url(url)
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise HTTPException(status_code=400, detail="Only public http/https URLs are allowed")

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds, connect=min(12.0, timeout_seconds)),
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 GenericPipelineJson/1.0",
                "Accept": "application/json,*/*;q=0.8",
            },
        ) as client:
            response = await client.get(url)
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="JSON pipeline source timed out") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"JSON pipeline source fetch failed: {exc}") from exc

    if response.status_code != 200:
        raise HTTPException(status_code=502, detail=f"JSON pipeline source returned HTTP {response.status_code}")
    if len(response.content) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="JSON pipeline source exceeds size limit")

    final_url = str(response.url)
    await _assert_public_http_url(final_url)
    try:
        payload = response.json()
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Pipeline source did not return valid JSON") from exc
    return payload, final_url, len(response.content), response.headers.get("content-type", "")


async def extract_generic_json(
    company: str,
    source_url: str,
    timeout_seconds: float = 35.0,
) -> GenericJsonPipelineResponse:
    payload, final_url, byte_count, content_type = await _download_json(source_url, timeout_seconds)
    rows, diagnostics = parse_semantic_json(company, final_url, payload)

    issues: List[str] = []
    if len(rows) < MIN_ROWS:
        issues.append(f"too few structured rows: {len(rows)} < {MIN_ROWS}")
    source_count = int(diagnostics.get("sourceRecordCount") or 0)
    rejected = int(diagnostics.get("rejectedRows") or 0)
    if source_count and rejected > max(3, int(source_count * 0.20)):
        issues.append(f"too many source rows rejected structurally: {rejected}/{source_count}")

    ready = not issues
    diagnostics = {
        **diagnostics,
        "documentBytes": byte_count,
        "contentType": content_type,
    }
    return GenericJsonPipelineResponse(
        version=ADAPTER_PROFILE,
        routeVersion=ROUTE_VERSION,
        company=company,
        sourceUrl=source_url,
        finalUrl=final_url,
        retrievalMode="EXTERNAL_HTTP",
        readOnly=True,
        readyForDiscovery=ready,
        rowCount=len(rows),
        rows=rows,
        summary={
            "structuralValidationPass": ready,
            "actual": {"Total": len(rows)},
            "productionStatus": (
                "READY FOR AIRTABLE DELTA COMPARISON"
                if ready else "FAIL CLOSED - PARSER/STRUCTURE REVIEW REQUIRED"
            ),
            "selectedMethod": "GENERIC_SEMANTIC_JSON_TABLE",
            "portfolioDependentValidation": False,
            "companySpecificParserBranch": False,
            "writeMode": "READ_ONLY",
        },
        issues=[{"issue": x} for x in issues],
        diagnostics=diagnostics,
        guardrails={
            "airtableWrites": False,
            "portfolioWrites": False,
            "masterDataWrites": False,
            "companySpecificParserBranch": False,
            "portfolioDependentValidation": False,
            "fuzzyIdentityResolution": False,
            "publicHttpOnly": True,
        },
    )


@app.get("/extract/generic/json-pipeline-table/health")
async def generic_json_health() -> Dict[str, Any]:
    return {
        "ok": True,
        "version": ADAPTER_PROFILE,
        "routeVersion": ROUTE_VERSION,
        "retrievalMode": "EXTERNAL_HTTP",
        "readOnly": True,
    }


@app.get("/extract/generic/json-pipeline-table", response_model=GenericJsonPipelineResponse)
async def generic_json_pipeline(
    company: str = Query(..., min_length=1, max_length=160),
    source_url: str = Query(..., min_length=8),
    timeout_seconds: float = Query(default=35.0, ge=5.0, le=35.0),
    x_adapter_key: Optional[str] = Header(default=None),
) -> GenericJsonPipelineResponse:
    _auth(x_adapter_key)
    return await extract_generic_json(company, source_url, timeout_seconds)
