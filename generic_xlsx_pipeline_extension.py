"""Read-only generic XLSX pipeline adapter.

Purpose
-------
Parse official company pipeline spreadsheets with semantic column headers into
the shared Portfolio Discovery row contract.

Guardrails
----------
- public HTTP(S) only;
- XLSX only;
- semantic header mapping, no company-specific branches;
- no Airtable or master-data writes;
- fail closed when the workbook cannot produce structurally complete rows.
"""

from __future__ import annotations

import io
import re
import zipfile
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import httpx
from fastapi import Header, HTTPException, Query
from pydantic import BaseModel

from main import _auth, app
from html_fetch_extension import _assert_public_http_url


ADAPTER_PROFILE = "PIPELINE_GENERIC_XLSX_V1"
ROUTE_VERSION = "GENERIC_XLSX_PIPELINE_V1.0_READ_ONLY"
MAX_BYTES = 8_000_000
MIN_ROWS = 4

HEADER_ALIASES = {
    "developmentCode": {
        "compound number", "compound no", "compound", "development code",
        "project code", "code",
    },
    "molecule": {
        "inn generic name", "inn", "generic name", "molecule",
    },
    "brand": {
        "brand name", "brand",
    },
    "therapeuticArea": {
        "therapeutic area", "therapy area", "disease area",
    },
    "indication": {
        "indication", "potential indication", "disease",
    },
    "phase": {
        "current phase", "phase", "clinical phase", "stage",
    },
    "mechanismOfAction": {
        "mode of action vaccine type", "mode of action", "mechanism of action",
        "moa", "vaccine type",
    },
    "partner": {
        "in license or other alliance relationship with third party",
        "partner", "partners", "alliance",
    },
    "notes": {
        "footnotes", "notes", "note",
    },
}


class GenericXlsxPipelineResponse(BaseModel):
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
    validation: Dict[str, Any]
    diagnostics: Dict[str, Any]
    guardrails: Dict[str, Any]


def clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", clean(value).lower()).strip()


def phase_canonical(value: Any) -> str:
    n = norm(value)
    if not n:
        return ""
    if any(x in n for x in ("registration", "regulatory", "filed")):
        return "Filed / Registration"
    if "preclinical" in n or "pre clinical" in n:
        return "Preclinical"

    # Roman and Arabic ranges collapse to the highest explicit phase.
    roman = {"i": 1, "ii": 2, "iii": 3, "iv": 4}
    hits: List[int] = []
    for token in re.findall(r"\b(?:phase\s*)?(i{1,3}|iv|[1-4])\b", n):
        if token.isdigit():
            hits.append(int(token))
        elif token in roman:
            hits.append(roman[token])
    if hits:
        return f"Phase {max(hits)}"
    return ""


def col_index(ref: str) -> int:
    letters = re.match(r"([A-Z]+)", str(ref or "").upper())
    if not letters:
        return -1
    value = 0
    for ch in letters.group(1):
        value = value * 26 + (ord(ch) - 64)
    return value - 1


def header_field(value: str) -> Optional[str]:
    n = norm(value)
    for field, aliases in HEADER_ALIASES.items():
        if n in aliases:
            return field
    return None


def read_xlsx_rows(data: bytes) -> List[Dict[str, Any]]:
    ns = {
        "m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
        "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    }
    rel_ns = {"p": "http://schemas.openxmlformats.org/package/2006/relationships"}

    sheets: List[Dict[str, Any]] = []
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        shared: List[str] = []
        if "xl/sharedStrings.xml" in z.namelist():
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in root.findall("m:si", ns):
                shared.append(clean(" ".join(t.text or "" for t in si.findall(".//m:t", ns))))

        workbook = ET.fromstring(z.read("xl/workbook.xml"))
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        relmap = {
            node.attrib["Id"]: node.attrib["Target"]
            for node in rels.findall("p:Relationship", rel_ns)
        }

        for sheet in workbook.findall("m:sheets/m:sheet", ns):
            name = sheet.attrib.get("name", "")
            rid = sheet.attrib.get(
                "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
            )
            target = relmap.get(rid, "")
            path = target if target.startswith("xl/") else "xl/" + target.lstrip("/")
            if path not in z.namelist():
                path = "xl/worksheets/" + target.split("/")[-1]
            if path not in z.namelist():
                continue

            root = ET.fromstring(z.read(path))
            matrix: List[Dict[int, str]] = []
            for row in root.findall(".//m:sheetData/m:row", ns):
                values: Dict[int, str] = {}
                for cell in row.findall("m:c", ns):
                    idx = col_index(cell.attrib.get("r", ""))
                    if idx < 0:
                        continue
                    typ = cell.attrib.get("t")
                    val = ""
                    if typ == "inlineStr":
                        val = clean(" ".join(
                            t.text or "" for t in cell.findall(".//m:t", ns)
                        ))
                    else:
                        node = cell.find("m:v", ns)
                        raw = node.text if node is not None and node.text is not None else ""
                        if typ == "s" and raw.isdigit() and int(raw) < len(shared):
                            val = shared[int(raw)]
                        else:
                            val = clean(raw)
                    values[idx] = val
                if values:
                    matrix.append(values)

            sheets.append({"name": name, "rows": matrix})

    return sheets


def parse_semantic_workbook(
    company: str,
    source_url: str,
    data: bytes,
) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    sheets = read_xlsx_rows(data)
    candidates: List[Dict[str, Any]] = []
    sheet_diagnostics: List[Dict[str, Any]] = []

    for sheet in sheets:
        rows = sheet["rows"]
        header_idx: Optional[int] = None
        mapping: Dict[str, int] = {}

        for idx, row in enumerate(rows[:12]):
            candidate: Dict[str, int] = {}
            for col, value in row.items():
                field = header_field(value)
                if field and field not in candidate:
                    candidate[field] = col
            if "indication" in candidate and "phase" in candidate and any(
                key in candidate for key in ("developmentCode", "molecule", "brand")
            ):
                header_idx = idx
                mapping = candidate
                break

        if header_idx is None:
            sheet_diagnostics.append({
                "sheet": sheet["name"],
                "status": "NO_SEMANTIC_HEADER",
                "rowCount": len(rows),
            })
            continue

        parsed_here = 0
        rejected_here = 0

        def get(row: Dict[int, str], field: str) -> str:
            col = mapping.get(field)
            return clean(row.get(col, "")) if col is not None else ""

        for source_row_no, row in enumerate(rows[header_idx + 1:], start=header_idx + 2):
            development_code = get(row, "developmentCode")
            molecule = get(row, "molecule")
            brand = get(row, "brand")
            indication = get(row, "indication")
            phase_raw = get(row, "phase")
            phase = phase_canonical(phase_raw)
            ta = get(row, "therapeuticArea")
            moa = get(row, "mechanismOfAction")
            partner = get(row, "partner")
            notes = get(row, "notes")

            asset = molecule or brand or development_code
            if not (asset and indication and phase):
                if any((development_code, molecule, brand, indication, phase_raw)):
                    rejected_here += 1
                continue

            candidates.append({
                "company": company,
                "sourceFamily": "Company Pipeline",
                "sourceRecordId": f"{sheet['name']}:{source_row_no}",
                "sourceUrl": source_url,
                "asset": asset,
                "molecule": molecule,
                "developmentCode": development_code,
                "brand": brand,
                "indication": indication,
                "phase": phase,
                "phaseEvidence": "SOURCE_SPREADSHEET",
                "programStatus": "",
                "sponsorOwner": company,
                "partners": [partner] if norm(partner) not in {"", "no"} else [],
                "study": "",
                "trialIds": [],
                "therapeuticArea": ta,
                "mechanismOfAction": moa,
                "sourceNotes": notes,
                "sourceOrdinal": len(candidates) + 1,
                "parserMethod": "SEMANTIC_XLSX_TABLE",
                "sourceAdapter": ADAPTER_PROFILE,
            })
            parsed_here += 1

        sheet_diagnostics.append({
            "sheet": sheet["name"],
            "status": "PARSED",
            "rowCount": len(rows),
            "headerRow": header_idx + 1,
            "mapping": mapping,
            "parsedRows": parsed_here,
            "rejectedRows": rejected_here,
        })

    # Exact source-grain de-duplication only.
    deduped: List[Dict[str, Any]] = []
    seen = set()
    for row in candidates:
        key = (
            norm(row["developmentCode"]),
            norm(row["molecule"]),
            norm(row["brand"]),
            norm(row["indication"]),
            norm(row["phase"]),
        )
        if key in seen:
            continue
        seen.add(key)
        row["sourceOrdinal"] = len(deduped) + 1
        deduped.append(row)

    diagnostics = {
        "sheetCount": len(sheets),
        "sheets": sheet_diagnostics,
        "candidateRows": len(candidates),
        "dedupedRows": len(deduped),
        "duplicateRowsRemoved": len(candidates) - len(deduped),
        "companySpecificParserBranch": False,
        "portfolioDependentValidation": False,
        "writes": 0,
    }
    return deduped, diagnostics


async def download_xlsx(url: str, timeout_seconds: float) -> tuple[bytes, str]:
    await _assert_public_http_url(url)
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise HTTPException(status_code=400, detail="Only public http/https URLs are allowed")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) PipelineXlsxAdapter/1.0",
        "Accept": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,*/*;q=0.8",
    }
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds, connect=12.0),
            follow_redirects=True,
            headers=headers,
        ) as client:
            response = await client.get(url)
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="Pipeline XLSX fetch timed out") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Pipeline XLSX fetch failed: {exc}") from exc

    if response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"Pipeline XLSX source returned HTTP {response.status_code}",
        )
    if len(response.content) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="Pipeline XLSX exceeds size limit")
    if not response.content.startswith(b"PK"):
        raise HTTPException(status_code=502, detail="Pipeline source did not return an XLSX/ZIP document")

    final_url = str(response.url)
    await _assert_public_http_url(final_url)
    return response.content, final_url


async def extract_generic_xlsx(
    company: str,
    source_url: str,
    timeout_seconds: float = 35.0,
) -> GenericXlsxPipelineResponse:
    data, final_url = await download_xlsx(source_url, timeout_seconds)
    rows, diagnostics = parse_semantic_workbook(company, final_url, data)

    incomplete = [
        r["sourceRecordId"]
        for r in rows
        if not (r.get("asset") and r.get("indication") and r.get("phase"))
    ]
    issues: List[str] = []
    if len(rows) < MIN_ROWS:
        issues.append(f"too few structured rows: {len(rows)} < {MIN_ROWS}")
    if incomplete:
        issues.append(f"{len(incomplete)} parsed rows missing core fields")

    validation = {
        "pass": not issues,
        "rowCount": len(rows),
        "issues": issues,
        "allCoreRowsComplete": not incomplete,
        "semanticHeaderFound": any(
            x.get("status") == "PARSED" for x in diagnostics.get("sheets", [])
        ),
    }

    return GenericXlsxPipelineResponse(
        version=ADAPTER_PROFILE,
        routeVersion=ROUTE_VERSION,
        company=company,
        sourceUrl=source_url,
        finalUrl=final_url,
        retrievalMode="STATIC_DOCUMENT",
        readOnly=True,
        readyForDiscovery=not issues,
        rowCount=len(rows),
        rows=rows,
        validation=validation,
        diagnostics={
            **diagnostics,
            "documentBytes": len(data),
        },
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


@app.get("/extract/generic/xlsx-pipeline/health")
async def generic_xlsx_health() -> Dict[str, Any]:
    return {
        "ok": True,
        "version": ADAPTER_PROFILE,
        "routeVersion": ROUTE_VERSION,
        "retrievalMode": "STATIC_DOCUMENT",
        "readOnly": True,
    }


@app.get("/extract/generic/xlsx-pipeline", response_model=GenericXlsxPipelineResponse)
async def generic_xlsx_pipeline(
    company: str = Query(..., min_length=1, max_length=160),
    source_url: str = Query(..., min_length=8),
    timeout_seconds: float = Query(default=35.0, ge=5.0, le=35.0),
    x_adapter_key: Optional[str] = Header(default=None),
) -> GenericXlsxPipelineResponse:
    _auth(x_adapter_key)
    return await extract_generic_xlsx(company, source_url, timeout_seconds)
