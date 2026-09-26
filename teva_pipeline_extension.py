"""Teva official pipeline adapter in the common discovery contract.

Parses Teva's public Innovative Medicine & Biosimilar Pipeline HTML using the
page's explicit development-stage headings and programme headings. Rows without
an explicit indication are intentionally excluded from Portfolio discovery
rather than inventing disease context.

Read-only. No Airtable or master-data writes.
"""

from __future__ import annotations

import hashlib
import re
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional

import httpx
from fastapi import Header, HTTPException, Query

from main import _auth, app
from html_fetch_extension import _assert_public_http_url
from generic_pipeline_extension import GenericPipelineExtractionResponse


ADAPTER_PROFILE = "PIPELINE_TEVA_HTML_V1"
ROUTE_VERSION = "TEVA_PIPELINE_COMMON_CONTRACT_V1.0"
SOURCE_URL = "https://www.tevapharm.com/science/pipeline/"

PHASES = {
    "pre-clinical": "Preclinical",
    "preclinical": "Preclinical",
    "phase 1": "Phase 1",
    "phase 2": "Phase 2",
    "phase 3": "Phase 3",
    "clinical": "Clinical",
    "under regulatory review": "Filed / Registration",
    "approved": "Approved",
}


def clean(value: Any) -> str:
    s = str(value or "")
    s = (
        s.replace("\u00a0", " ")
        .replace("\u2018", "'")
        .replace("\u2019", "'")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("®", "")
        .replace("™", "")
    )
    return re.sub(r"\s+", " ", s).strip()


def norm(value: Any) -> str:
    return clean(value).lower()


class PipelineParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.capture: Optional[str] = None
        self.buf: List[str] = []
        self.phase = ""
        self.asset = ""
        self.indications: List[str] = []
        self.context: List[str] = []
        self.rows: List[Dict[str, Any]] = []
        self.excluded_no_indication = 0

    def flush_asset(self) -> None:
        asset = clean(self.asset)
        if not asset:
            self.indications = []
            self.context = []
            return

        inds = [clean(x) for x in self.indications if clean(x)]
        if not inds:
            self.excluded_no_indication += 1
        else:
            for indication in inds:
                self.rows.append({
                    "phase": self.phase,
                    "rawAsset": asset,
                    "indication": indication,
                    "context": " | ".join(self.context[:4]),
                })

        self.asset = ""
        self.indications = []
        self.context = []

    def handle_starttag(self, tag: str, attrs) -> None:
        t = tag.lower()
        if t in {"h3", "h4", "li", "p"}:
            self.capture = t
            self.buf = []

    def handle_data(self, data: str) -> None:
        if self.capture:
            self.buf.append(data)

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if self.capture != t:
            return

        text = clean(" ".join(self.buf))
        self.capture = None
        self.buf = []

        if not text:
            return

        if t == "h3":
            phase = PHASES.get(norm(text))
            if phase:
                self.flush_asset()
                self.phase = phase
            return

        if t == "h4" and self.phase:
            if norm(text) in {
                "more information",
                "no drugs found for your filtering criteria",
            }:
                return
            self.flush_asset()
            self.asset = text
            return

        if t == "li" and self.phase and self.asset:
            if not re.search(
                r"^(biosimilars?|small molecules?|novel biologics?)$",
                text,
                re.I,
            ):
                self.indications.append(text)
            return

        if t == "p" and self.phase and self.asset:
            if len(text) <= 400:
                self.context.append(text)


def parse_identity(raw: str) -> Dict[str, str]:
    raw = clean(raw)
    asset = raw
    molecule = ""
    development = ""
    brand = ""

    m = re.match(r"^(.*?)\s*\(([^()]+)\)\s*$", raw)
    if m:
        outer = clean(m.group(1))
        inner = clean(m.group(2))
        asset = outer or inner
        if re.search(r"\b(?:TEV|EBS)[- ']?\d+", inner, re.I):
            development = inner
        else:
            molecule = inner

    if re.fullmatch(r"(?:TEV|EBS)[- ']?\d+", asset, re.I):
        development = asset
    elif asset.lower().startswith("biosimilar to "):
        brand = clean(re.sub(r"^biosimilar to\s+", "", asset, flags=re.I))
    elif asset and not molecule:
        molecule = asset

    return {
        "asset": asset,
        "molecule": molecule,
        "developmentCode": development,
        "brand": brand,
    }


async def fetch_html(timeout_seconds: float) -> str:
    await _assert_public_http_url(SOURCE_URL)
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; PharmaIntelligenceAdapter/1.0)",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-GB,en;q=0.9",
    }
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds, connect=12.0),
            headers=headers,
            follow_redirects=True,
        ) as client:
            response = await client.get(SOURCE_URL)
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="Teva pipeline fetch timed out") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Teva pipeline fetch failed: {exc}") from exc

    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"Teva pipeline returned HTTP {response.status_code}")
    return response.text


@app.get("/extract/teva/pipeline", response_model=GenericPipelineExtractionResponse)
async def extract_teva_pipeline(
    company: str = Query(..., min_length=1, max_length=160),
    source_url: str = Query(..., min_length=8),
    timeout_seconds: float = Query(default=35.0, ge=5.0, le=35.0),
    x_adapter_key: Optional[str] = Header(default=None),
) -> GenericPipelineExtractionResponse:
    _auth(x_adapter_key)

    if "teva" not in norm(company):
        raise HTTPException(status_code=400, detail="This adapter is restricted to Teva.")
    if source_url.rstrip("/") != SOURCE_URL.rstrip("/"):
        raise HTTPException(status_code=400, detail="Unexpected Teva pipeline source URL.")

    raw = await fetch_html(timeout_seconds)
    parser = PipelineParser()
    parser.feed(raw)
    parser.close()
    parser.flush_asset()

    source_date_match = re.search(
        r"Pipeline\s+is\s+current\s+as\s+of\s+([A-Za-z]+\s+20\d{2})",
        re.sub(r"<[^>]+>", " ", raw),
        re.I,
    )
    source_date = clean(source_date_match.group(1)) if source_date_match else None

    rows: List[Dict[str, Any]] = []
    seen = set()
    for i, parsed in enumerate(parser.rows, start=1):
        identity = parse_identity(parsed["rawAsset"])
        indication = clean(parsed["indication"])
        phase = clean(parsed["phase"])
        key = (norm(identity["asset"]), norm(indication), norm(phase))
        if key in seen:
            continue
        seen.add(key)
        rid = "teva:" + hashlib.sha1("|".join(key).encode("utf-8")).hexdigest()[:16]
        rows.append({
            "company": "Teva",
            "sourceFamily": "Teva Official Pipeline",
            "sourceRecordId": rid,
            "sourceUrl": SOURCE_URL,
            "asset": identity["asset"],
            "molecule": identity["molecule"],
            "developmentCode": identity["developmentCode"],
            "brand": identity["brand"],
            "indication": indication,
            "phase": phase,
            "therapeuticArea": "",
            "modality": "",
            "description": clean(parsed.get("context", "")),
            "additionalInformation": clean(parsed.get("context", "")),
            "programStatus": "Active",
            "sponsorOwner": "Teva",
            "partners": [],
            "study": "",
            "trialIds": [],
            "sourceAdapter": ADAPTER_PROFILE,
            "sourceCardOrdinal": len(rows) + 1,
            "sourceTherapeuticArea": "",
        })

    issues: List[Dict[str, Any]] = []
    if len(rows) < 4:
        issues.append({"issue": f"too few structured rows: {len(rows)} < 4"})

    incomplete = [
        r["sourceRecordId"]
        for r in rows
        if not (r.get("asset") and r.get("indication") and r.get("phase"))
    ]
    if incomplete:
        issues.append({"issue": f"{len(incomplete)} rows missing core fields"})

    structural_pass = not issues
    diagnostics = {
        "selectedMethod": "TEVA_PHASE_HEADING_HTML_V1",
        "rowFailures": 0,
        "phaseUnresolved": 0,
        "boundaryWarnings": 0,
        "coverageWarnings": 0,
        "exactDuplicates": 0,
        "excludedNoIndicationRows": parser.excluded_no_indication,
        "portfolioDependentValidation": False,
        "retrievalMode": "DIRECT",
    }
    summary = {
        "structuralValidationPass": structural_pass,
        "actual": {"Total": len(rows)},
        "selectedMethod": diagnostics["selectedMethod"],
        "retrievalMode": "DIRECT",
        "routingReason": "SOURCE_SPECIFIC_ADAPTER",
        "portfolioDependentValidation": False,
        "companySpecificParserBranch": True,
        "writeMode": "READ_ONLY",
        "productionStatus": (
            "READY FOR AIRTABLE DELTA COMPARISON"
            if structural_pass
            else "FAIL CLOSED - SOURCE PARSER REVIEW REQUIRED"
        ),
    }
    validation = {
        "pass": structural_pass,
        "issues": [x["issue"] for x in issues],
    }

    return GenericPipelineExtractionResponse(
        version=ADAPTER_PROFILE,
        routeVersion=ROUTE_VERSION,
        interpreterVersion=ROUTE_VERSION,
        company="Teva",
        sourceUrl=SOURCE_URL,
        finalUrl=SOURCE_URL,
        sourceDate=source_date,
        readOnly=True,
        readyForDiscovery=structural_pass,
        rowCount=len(rows),
        rows=rows,
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


@app.get("/extract/teva/pipeline/health")
async def teva_pipeline_health() -> Dict[str, Any]:
    return {
        "ok": True,
        "version": ADAPTER_PROFILE,
        "routeVersion": ROUTE_VERSION,
        "sourceUrl": SOURCE_URL,
        "readOnly": True,
    }
