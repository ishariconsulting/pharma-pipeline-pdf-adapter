"""UCB H1 2026 official pipeline overview adapter.

Parses UCB's first-party Pipeline Overview PDF. The document encodes phase by
the horizontal extent of each programme bar across PHASE 1/2/3 columns; this
adapter derives phase from source geometry and indications from the bold
indication labels on the right.

Read-only. No Airtable or master-data writes.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Dict, List, Optional, Tuple

import fitz
import httpx
from fastapi import Header, HTTPException, Query

from main import _auth, app
from html_fetch_extension import _assert_public_http_url
from generic_pipeline_extension import GenericPipelineExtractionResponse


ADAPTER_PROFILE = "PIPELINE_UCB_H1_PDF_V1"
ROUTE_VERSION = "UCB_H1_PIPELINE_COMMON_CONTRACT_V1.0"
SOURCE_URL = "https://www.ucb.com/sites/default/files/2026-07/H1%20Pipeline%20Overview.pdf"


def clean(value: Any) -> str:
    s = str(value or "")
    s = (
        s.replace("\u00a0", " ")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("®", "")
        .replace("™", "")
    )
    return re.sub(r"\s+", " ", s).strip()


def norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", clean(value).lower()).strip()


def _line_items(page: fitz.Page) -> List[Dict[str, Any]]:
    data = page.get_text("dict")
    out: List[Dict[str, Any]] = []
    for block in data.get("blocks", []):
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            if not spans:
                continue
            text = clean(" ".join(clean(s.get("text", "")) for s in spans))
            if not text:
                continue
            x0 = min(float(s["bbox"][0]) for s in spans)
            y0 = min(float(s["bbox"][1]) for s in spans)
            x1 = max(float(s["bbox"][2]) for s in spans)
            y1 = max(float(s["bbox"][3]) for s in spans)
            bold = any(
                "bold" in str(s.get("font", "")).lower()
                or int(s.get("flags", 0)) & 16
                for s in spans
            )
            size = max(float(s.get("size", 0)) for s in spans)
            out.append({
                "text": text,
                "x0": x0, "y0": y0, "x1": x1, "y1": y1,
                "yc": (y0 + y1) / 2.0,
                "bold": bold,
                "size": size,
            })
    return out


def _phase_headers(lines: List[Dict[str, Any]]) -> Dict[int, float]:
    out: Dict[int, float] = {}
    for line in lines:
        m = re.fullmatch(r"PHASE\s*([123])", line["text"], re.I)
        if m:
            out[int(m.group(1))] = (line["x0"] + line["x1"]) / 2.0
    return out


def _indication_start(lines: List[Dict[str, Any]]) -> Optional[float]:
    candidates = [
        line for line in lines
        if re.search(r"Indication\s*/\s*Planned\s+Timelines", line["text"], re.I)
    ]
    if candidates:
        return min(x["x0"] for x in candidates)
    candidates = [line for line in lines if norm(line["text"]).startswith("indication planned timelines")]
    return min((x["x0"] for x in candidates), default=None)


def _phase_grid_right(headers: Dict[int, float]) -> float:
    """Right edge of the source Phase 3 grid inferred from header spacing."""
    spacing = (headers[3] - headers[1]) / 2.0
    return headers[3] + spacing / 2.0


def _asset_lines(
    lines: List[Dict[str, Any]],
    headers: Dict[int, float],
    header_y: float,
    page_h: float,
) -> List[Dict[str, Any]]:
    """Return left-column programme labels only.

    The long indication heading is centred over the right panel, so its x0 is
    not a safe left/right boundary. Programme names consistently start left of
    the Phase 1 header centre; use that source geometry instead.
    """
    left_cutoff = headers[1] - 8.0
    candidates = []

    for line in lines:
        if not (header_y + 12 < line["yc"] < page_h - 45):
            continue
        if line["x0"] >= left_cutoff:
            continue

        text = line["text"]
        if re.search(r"^PHASE\s*[123]$", text, re.I):
            continue
        if re.search(
            r"UCB.?s Pipeline|Immunology|Neurology|Proprietary|Inspired by|Driven by|Facts & Figures",
            text,
            re.I,
        ):
            continue
        if line["bold"] and len(text) >= 4:
            candidates.append(line)

    # Merge wrapped labels such as glovadalen + mechanism on the following line.
    groups: List[List[Dict[str, Any]]] = []
    for line in sorted(candidates, key=lambda x: x["yc"]):
        if groups and line["yc"] - groups[-1][-1]["yc"] <= 13.0:
            groups[-1].append(line)
        else:
            groups.append([line])

    out: List[Dict[str, Any]] = []
    for group in groups:
        ordered = sorted(group, key=lambda x: (x["yc"], x["x0"]))
        text = clean(" ".join(x["text"] for x in ordered))
        if not text:
            continue
        out.append({
            "text": text,
            "x0": min(x["x0"] for x in ordered),
            "y0": min(x["y0"] for x in ordered),
            "x1": max(x["x1"] for x in ordered),
            "y1": max(x["y1"] for x in ordered),
            "yc": sum(x["yc"] for x in ordered) / len(ordered),
            "bold": True,
            "size": max(x["size"] for x in ordered),
        })
    return out


def _bar_right_edge(page: fitz.Page, y: float, indication_x: float) -> Optional[float]:
    candidates: List[Tuple[float, float]] = []
    try:
        drawings = page.get_drawings()
    except Exception:
        drawings = []

    for d in drawings:
        rect = d.get("rect")
        fill = d.get("fill")
        if rect is None or fill is None:
            continue
        if not (rect.y0 - 3 <= y <= rect.y1 + 3):
            continue
        if rect.x0 > page.rect.width * 0.18:
            continue
        if rect.width < page.rect.width * 0.20:
            continue
        if rect.x1 > indication_x + 20:
            continue
        if rect.height < 10 or rect.height > 80:
            continue
        candidates.append((rect.width, rect.x1))

    if not candidates:
        return None
    return max(candidates, key=lambda x: x[0])[1]


def _phase_from_edge(edge: Optional[float], headers: Dict[int, float]) -> str:
    if edge is None or len(headers) < 3:
        return ""
    reached = [n for n, center in headers.items() if edge >= center]
    if not reached:
        return ""
    return f"Phase {max(reached)}"


def _clean_indication_label(text: str) -> str:
    s = clean(text)
    s = re.sub(r"\s+NEW\b.*$", "", s, flags=re.I)
    s = re.sub(r"\s+-\s+.*$", "", s)
    s = re.sub(r"\s+(?:Positive\s+)?Phase\s*[123](?:[ab])?(?:\s+initiated)?\b.*$", "", s, flags=re.I)
    s = re.sub(r"\s+Phase\s*[123](?:[ab])?\b.*$", "", s, flags=re.I)
    return clean(s)


def _indications_for_band(
    lines: List[Dict[str, Any]],
    indication_x: float,
    y0: float,
    y1: float,
) -> List[str]:
    candidates: List[str] = []
    for line in lines:
        if not (y0 <= line["yc"] < y1):
            continue
        if line["x0"] < indication_x - 5:
            continue
        if not line["bold"]:
            continue
        txt = _clean_indication_label(line["text"])
        if not txt or norm(txt) in {"new", "indication planned timelines"}:
            continue
        if re.search(r"^Topline results|^Initiated|^Next steps|^Filed$", txt, re.I):
            continue
        candidates.append(txt)

    # Some rows have multiple indication labels on one line in separate spans;
    # line extraction can merge them. Split only on wide repeated spacing that
    # survives text extraction.
    expanded: List[str] = []
    for text in candidates:
        parts = [clean(x) for x in re.split(r"\s{3,}", text) if clean(x)]
        expanded.extend(parts or [text])

    seen = set()
    out = []
    for x in expanded:
        k = norm(x)
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(x)
    return out


def _identity(raw: str) -> Dict[str, str]:
    raw = clean(raw)
    brand = ""
    molecule = raw
    mechanism = ""

    m = re.match(r"^(.*?)\s*\(([^()]*)\)\s*\*?$", raw)
    if m:
        molecule = clean(m.group(1))
        mechanism = clean(m.group(2))

    if " " in molecule and re.search(r"STACCATO", molecule, re.I):
        parts = molecule.split()
        brand = clean(parts[0])
        molecule = clean(" ".join(parts[1:]))

    return {
        "asset": molecule or raw,
        "molecule": molecule or raw,
        "developmentCode": "",
        "brand": brand,
        "mechanism": mechanism,
    }


async def download_pdf(timeout_seconds: float) -> bytes:
    await _assert_public_http_url(SOURCE_URL)
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; PharmaIntelligenceAdapter/1.0)",
        "Accept": "application/pdf,*/*;q=0.8",
    }
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds, connect=12.0),
            headers=headers,
            follow_redirects=True,
        ) as client:
            response = await client.get(SOURCE_URL)
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="UCB pipeline PDF fetch timed out") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"UCB pipeline PDF fetch failed: {exc}") from exc

    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"UCB pipeline PDF returned HTTP {response.status_code}")
    if not response.content.startswith(b"%PDF"):
        raise HTTPException(status_code=502, detail="UCB source did not return a PDF")
    return response.content


@app.get("/extract/ucb/pipeline", response_model=GenericPipelineExtractionResponse)
async def extract_ucb_pipeline(
    company: str = Query(..., min_length=1, max_length=160),
    source_url: str = Query(..., min_length=8),
    timeout_seconds: float = Query(default=35.0, ge=5.0, le=35.0),
    x_adapter_key: Optional[str] = Header(default=None),
) -> GenericPipelineExtractionResponse:
    _auth(x_adapter_key)

    if norm(company) != "ucb":
        raise HTTPException(status_code=400, detail="This adapter is restricted to UCB.")

    # Accept either the canonical live pipeline page or the official H1 PDF
    # supplied as Machine Source URL by Source Watch.
    allowed = {
        SOURCE_URL.rstrip("/"),
        "https://www.ucb.com/innovation/pipeline".rstrip("/"),
    }
    if source_url.rstrip("/") not in allowed:
        raise HTTPException(status_code=400, detail="Unexpected UCB pipeline source URL.")

    data = await download_pdf(timeout_seconds)
    doc = fitz.open(stream=data, filetype="pdf")
    if len(doc) < 1:
        raise HTTPException(status_code=422, detail="UCB pipeline PDF has no pages")

    page = doc[0]
    lines = _line_items(page)
    headers = _phase_headers(lines)
    heading_indication_x = _indication_start(lines)
    indication_x = (
        _phase_grid_right(headers) + 12.0
        if set(headers) == {1, 2, 3}
        else None
    )
    issues: List[Dict[str, Any]] = []

    if set(headers) != {1, 2, 3}:
        issues.append({"issue": f"phase headers unresolved: {headers}"})
    if heading_indication_x is None:
        issues.append({"issue": "Indication / Planned Timelines header not found"})

    rows: List[Dict[str, Any]] = []
    unresolved_assets: List[str] = []

    if indication_x is not None and set(headers) == {1, 2, 3}:
        header_y = min(
            line["yc"] for line in lines
            if re.fullmatch(r"PHASE\s*[123]", line["text"], re.I)
        )
        assets = _asset_lines(lines, headers, header_y, page.rect.height)

        centers = [a["yc"] for a in assets]
        for idx, asset_line in enumerate(assets):
            y0 = (centers[idx - 1] + centers[idx]) / 2.0 if idx > 0 else header_y + 8
            y1 = (centers[idx] + centers[idx + 1]) / 2.0 if idx + 1 < len(centers) else page.rect.height - 45

            edge = _bar_right_edge(page, asset_line["yc"], indication_x)
            phase = _phase_from_edge(edge, headers)
            indications = _indications_for_band(lines, indication_x, y0, y1)

            if not phase or not indications:
                unresolved_assets.append(
                    f"{asset_line['text']}|phase={phase or 'blank'}|indications={len(indications)}|edge={edge}"
                )
                continue

            ident = _identity(asset_line["text"])
            for indication in indications:
                key = (norm(ident["asset"]), norm(indication), norm(phase))
                rid = "ucb:" + hashlib.sha1("|".join(key).encode("utf-8")).hexdigest()[:16]
                rows.append({
                    "company": "UCB",
                    "sourceFamily": "UCB H1 Pipeline Overview",
                    "sourceRecordId": rid,
                    "sourceUrl": SOURCE_URL,
                    "asset": ident["asset"],
                    "molecule": ident["molecule"],
                    "developmentCode": ident["developmentCode"],
                    "brand": ident["brand"],
                    "indication": indication,
                    "phase": phase,
                    "therapeuticArea": "",
                    "modality": "",
                    "mechanismOfAction": ident["mechanism"],
                    "description": "",
                    "additionalInformation": "",
                    "programStatus": "Active",
                    "sponsorOwner": "UCB",
                    "partners": ["Biogen"] if "dapirolizumab" in norm(ident["asset"]) else [],
                    "study": "",
                    "trialIds": [],
                    "sourceAdapter": ADAPTER_PROFILE,
                    "sourceCardOrdinal": len(rows) + 1,
                    "sourceTherapeuticArea": "",
                })

    # Exact dedupe.
    dedup = []
    seen = set()
    for row in rows:
        key = (norm(row["asset"]), norm(row["indication"]), norm(row["phase"]))
        if key in seen:
            continue
        seen.add(key)
        dedup.append(row)
    rows = dedup

    if len(rows) < 4:
        issues.append({"issue": f"too few structured rows: {len(rows)} < 4"})
    if unresolved_assets:
        issues.append({"issue": f"{len(unresolved_assets)} programme rows unresolved"})

    print(
        "UCB_PIPELINE_DIAG " + json.dumps(
            {
                "phaseHeaders": headers,
                "indicationStartX": indication_x,
                "headingIndicationX": heading_indication_x,
                "lineSample": [
                    {
                        "text": x["text"],
                        "x0": round(x["x0"], 1),
                        "x1": round(x["x1"], 1),
                        "yc": round(x["yc"], 1),
                        "bold": x["bold"],
                    }
                    for x in lines
                ],
                "unresolvedAssets": unresolved_assets,
                "rows": [
                    {
                        "asset": r["asset"],
                        "indication": r["indication"],
                        "phase": r["phase"],
                    }
                    for r in rows
                ],
            },
            ensure_ascii=False,
        ),
        flush=True,
    )

    structural_pass = not issues
    diagnostics = {
        "selectedMethod": "UCB_PDF_PHASE_BAR_GEOMETRY_V1",
        "rowFailures": len(unresolved_assets),
        "phaseUnresolved": sum("phase=blank" in x for x in unresolved_assets),
        "boundaryWarnings": 0,
        "coverageWarnings": 0,
        "exactDuplicates": 0,
        "phaseHeaderCenters": headers,
        "indicationStartX": indication_x,
        "headingIndicationX": heading_indication_x,
        "unresolvedSample": unresolved_assets[:12],
        "portfolioDependentValidation": False,
        "retrievalMode": "STATIC_DOCUMENT",
    }
    summary = {
        "structuralValidationPass": structural_pass,
        "actual": {"Total": len(rows)},
        "selectedMethod": diagnostics["selectedMethod"],
        "retrievalMode": "STATIC_DOCUMENT",
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

    return GenericPipelineExtractionResponse(
        version=ADAPTER_PROFILE,
        routeVersion=ROUTE_VERSION,
        interpreterVersion=ROUTE_VERSION,
        company="UCB",
        sourceUrl=SOURCE_URL,
        finalUrl=SOURCE_URL,
        sourceDate="2026-07",
        readOnly=True,
        readyForDiscovery=structural_pass,
        rowCount=len(rows),
        rows=rows,
        summary=summary,
        issues=issues,
        diagnostics=diagnostics,
        validation={
            "pass": structural_pass,
            "issues": [x["issue"] for x in issues],
        },
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


@app.get("/extract/ucb/pipeline/health")
async def ucb_pipeline_health() -> Dict[str, Any]:
    return {
        "ok": True,
        "version": ADAPTER_PROFILE,
        "routeVersion": ROUTE_VERSION,
        "sourceUrl": SOURCE_URL,
        "readOnly": True,
    }


@app.get("/extract/ucb/pipeline/probe")
async def ucb_pipeline_probe() -> Dict[str, Any]:
    """Fixed-source geometry diagnostic for parser validation; read-only."""
    data = await download_pdf(35.0)
    doc = fitz.open(stream=data, filetype="pdf")
    page = doc[0]
    lines = _line_items(page)
    headers = _phase_headers(lines)
    heading_indication_x = _indication_start(lines)
    indication_x = (
        _phase_grid_right(headers) + 12.0
        if set(headers) == {1, 2, 3}
        else None
    )
    header_y = min(
        (line["yc"] for line in lines if re.fullmatch(r"PHASE\\s*[123]", line["text"], re.I)),
        default=0,
    )
    assets = _asset_lines(lines, headers, header_y, page.rect.height) if set(headers) == {1, 2, 3} else []
    return {
        "ok": True,
        "version": ADAPTER_PROFILE,
        "page": {"width": page.rect.width, "height": page.rect.height},
        "phaseHeaders": headers,
        "indicationStartX": indication_x,
        "headingIndicationX": heading_indication_x,
        "assetCandidates": assets,
        "lines": lines,
        "drawings": [
            {
                "rect": [d["rect"].x0, d["rect"].y0, d["rect"].x1, d["rect"].y1]
                if d.get("rect") is not None else None,
                "fill": d.get("fill"),
                "width": d["rect"].width if d.get("rect") is not None else None,
                "height": d["rect"].height if d.get("rect") is not None else None,
            }
            for d in page.get_drawings()
            if d.get("rect") is not None
        ][:250],
        "readOnly": True,
    }
