"""Read-only semantic PDF-grid pipeline adapter.

Purpose
-------
Parse official company pipeline PDFs that expose a repeated semantic grid:
molecule/asset, therapeutic area, indication, modality and phase.

Phase markers may be embedded as small coloured images rather than extractable
text. The adapter classifies marker hue (orange=1, blue=2, green=3) and uses
the marker's row geometry to extract the other semantic columns.

Guardrails
----------
- public HTTP(S) only;
- PDF only;
- semantic header discovery on each parsed page;
- row geometry is derived from the source, not company-specific coordinates;
- no Portfolio/Airtable/master-data writes;
- fail closed on unknown marker colours, missing headers, or incomplete rows.
"""

from __future__ import annotations

import colorsys
import re
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import fitz
import httpx
from fastapi import Header, HTTPException, Query
from pydantic import BaseModel

from main import _auth, app
from html_fetch_extension import _assert_public_http_url


ADAPTER_PROFILE = "PIPELINE_SEMANTIC_PDF_GRID_V1"
ROUTE_VERSION = "SEMANTIC_PDF_GRID_PIPELINE_V1.0_READ_ONLY"
MAX_BYTES = 12_000_000
MIN_ROWS = 4

HEADER_PATTERNS = {
    "asset": re.compile(r"^molecule(?:\s+name)?$", re.I),
    "therapeuticArea": re.compile(r"^therapeutic(?:\s+area)?$", re.I),
    "indication": re.compile(r"^(?:investigational\s+)?indication$", re.I),
    "modality": re.compile(r"^modality$", re.I),
    "phase": re.compile(r"^phase$", re.I),
}


class GenericPdfGridPipelineResponse(BaseModel):
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
    validation: Dict[str, Any]
    diagnostics: Dict[str, Any]
    guardrails: Dict[str, Any]


def clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", clean(value).lower()).strip()


def _clip_text(page: fitz.Page, rect: fitz.Rect) -> str:
    text = page.get_text("text", clip=rect, sort=True)
    return clean(text)


def _header_positions(page: fitz.Page) -> Optional[Dict[str, float]]:
    """Locate semantic column starts from header words, independent of page size."""

    words = page.get_text("words", sort=True)
    found: Dict[str, Tuple[float, float]] = {}

    # First pass: exact individual header words. This matches layouts where
    # "MOLECULE NAME" and "THERAPEUTIC AREA" are split into separate words.
    for word in words:
  x0, y0, x1, y1, text = word[:5]
  token = clean(text)
  if not token:
      continue

  if re.fullmatch(r"MOLECULE", token, re.I):
      found.setdefault("asset", (float(x0), float(y0)))
  elif re.fullmatch(r"THERAPEUTIC", token, re.I):
      found.setdefault("therapeuticArea", (float(x0), float(y0)))
  elif re.fullmatch(r"INDICATION", token, re.I):
      found.setdefault("indication", (float(x0), float(y0)))
  elif re.fullmatch(r"MODALITY", token, re.I):
      found.setdefault("modality", (float(x0), float(y0)))
  elif re.fullmatch(r"PHASE", token, re.I):
      found.setdefault("phase", (float(x0), float(y0)))

    if len(found) != 5:
  return None

    ys = [v[1] for v in found.values()]
    if max(ys) - min(ys) > 30:
  return None

    xs = {k: v[0] for k, v in found.items()}
    ordered = [
  xs["asset"],
  xs["therapeuticArea"],
  xs["indication"],
  xs["modality"],
  xs["phase"],
    ]
    if any(b <= a for a, b in zip(ordered, ordered[1:])):
  return None

    xs["headerY"] = min(ys)
    return xs


def _pixmap_rgb_samples(doc: fitz.Document, xref: int) -> List[Tuple[int, int, int]]:
    try:
  pix = fitz.Pixmap(doc, xref)
  if pix.colorspace is None:
      return []
  if pix.colorspace.n not in (3,):
      pix = fitz.Pixmap(fitz.csRGB, pix)
    except Exception:
  return []

    n = pix.n
    if n < 3:
  return []

    data = pix.samples
    out: List[Tuple[int, int, int]] = []
    step = n

    # Keep coloured pixels only; white digit/background transparency and grey
    # anti-aliasing must not dominate the hue estimate.
    for i in range(0, len(data) - (n - 1), step):
  r, g, b = data[i], data[i + 1], data[i + 2]
  if n >= 4 and pix.alpha and data[i + 3] < 80:
      continue
  mx, mn = max(r, g, b), min(r, g, b)
  if mx < 60 or mx - mn < 30:
      continue
  if r > 242 and g > 242 and b > 242:
      continue
  out.append((r, g, b))

    return out


def _phase_from_icon(doc: fitz.Document, xref: int) -> Tuple[str, Dict[str, Any]]:
    samples = _pixmap_rgb_samples(doc, xref)
    if not samples:
  return "", {"xref": xref, "reason": "NO_COLOURED_PIXELS"}

    # Median-ish robust centre via channel means over coloured pixels.
    r = sum(x[0] for x in samples) / len(samples)
    g = sum(x[1] for x in samples) / len(samples)
    b = sum(x[2] for x in samples) / len(samples)
    h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)

    phase = ""
    # Hue bands intentionally broad enough for anti-aliased icon variants but
    # disjoint enough to fail closed on unrelated graphics.
    if 0.035 <= h <= 0.16 and s >= 0.35:
  phase = "Phase 1"
    elif 0.48 <= h <= 0.64 and s >= 0.25:
  phase = "Phase 2"
    elif 0.20 <= h <= 0.46 and s >= 0.25:
  phase = "Phase 3"

    return phase, {
  "xref": xref,
  "rgb": [round(r, 1), round(g, 1), round(b, 1)],
  "hsv": [round(h, 4), round(s, 4), round(v, 4)],
  "samplePixels": len(samples),
    }


def _row_band_for_marker(page: fitz.Page, marker: fitz.Rect) -> fitz.Rect:
    yc = (marker.y0 + marker.y1) / 2
    xc = (marker.x0 + marker.x1) / 2
    candidates: List[fitz.Rect] = []

    for drawing in page.get_drawings():
  rr = drawing.get("rect")
  fill = drawing.get("fill")
  if rr is None or fill is None:
      continue
  if not (rr.x0 <= xc <= rr.x1 and rr.y0 <= yc <= rr.y1):
      continue
  if rr.width < 18 or rr.height < 20 or rr.height > 55:
      continue
  vals = [float(x) for x in fill]
  if max(vals) - min(vals) > 0.05:
      continue
  if sum(vals) / len(vals) < 0.78:
      continue
  candidates.append(rr)

    if candidates:
  # The phase-cell background is normally the narrowest rectangle that
  # contains the marker centre while spanning the complete data row.
  rr = min(candidates, key=lambda x: (x.height, x.width))
  return fitz.Rect(0, rr.y0, page.rect.width, rr.y1)

    return fitz.Rect(0, max(0, yc - 18), page.rect.width, min(page.rect.height, yc + 18))


def _phase_markers(
    doc: fitz.Document,
    page: fitz.Page,
    phase_x: float,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    markers: List[Dict[str, Any]] = []
    unresolved: List[Dict[str, Any]] = []
    seen = set()

    for image in page.get_images(full=True):
  xref = int(image[0])
  try:
      rects = page.get_image_rects(xref)
  except Exception:
      rects = []

  phase, colour = _phase_from_icon(doc, xref)

  for rr in rects:
      cx = (rr.x0 + rr.x1) / 2
      if cx < phase_x - 15:
          continue
      if rr.y0 < 150 or rr.y1 > page.rect.height - 80:
          continue
      if not (6 <= rr.width <= 30 and 6 <= rr.height <= 30):
          continue

      key = (
          xref,
          round(rr.x0, 1),
          round(rr.y0, 1),
          round(rr.x1, 1),
          round(rr.y1, 1),
      )
      if key in seen:
          continue
      seen.add(key)

      item = {
          "xref": xref,
          "rect": rr,
          "phase": phase,
          "colour": colour,
      }
      if phase:
          markers.append(item)
      else:
          unresolved.append({
              "xref": xref,
              "rect": [round(v, 2) for v in (rr.x0, rr.y0, rr.x1, rr.y1)],
              "colour": colour,
          })

    markers.sort(key=lambda x: x["rect"].y0)
    return markers, unresolved


def _parse_identity(raw: str) -> Dict[str, str]:
    raw = clean(raw)
    label = clean(re.split(r"\(", raw, maxsplit=1)[0])
    label = re.sub(r"[®™]+", "", label).strip()

    brand = ""
    molecule = ""
    development_code = ""

    if "®" in raw or "™" in raw:
  brand = label

    code_match = re.fullmatch(r"(?:AMG|ABP|TAK|RG|BNT|BI|JNJ|MK|GSK|ION|ISIS|ARO)[ -]?\d+[A-Z]?", label, re.I)
    if code_match:
  development_code = label

    former = re.search(
  r"formerly\s+((?:AMG|ABP|TAK|RG|BNT|BI|JNJ|MK|GSK|ION|ISIS|ARO)[ -]?\d+[A-Z]?)",
  raw,
  re.I,
    )
    if former:
  development_code = clean(former.group(1))

    # Branded rows often put the generic name in the first parenthesis.
    first_paren = re.search(r"\(([^()]]{2,100})\)", raw)
    if brand and first_paren:
  candidate = clean(first_paren.group(1))
  if not re.search(r"investigational|formerly|biosimilar", candidate, re.I):
      molecule = candidate

    if not brand and not development_code:
  molecule = label

    asset = molecule or label or development_code or brand
    return {
  "asset": asset,
  "molecule": molecule,
  "developmentCode": development_code,
  "brand": brand,
  "sourceIdentity": raw,
    }


def parse_semantic_pdf_grid(
    company: str,
    source_url: str,
    data: bytes,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    try:
  doc = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:
  raise HTTPException(status_code=422, detail=f"Could not open PDF: {exc}") from exc

    candidates: List[Dict[str, Any]] = []
    page_diagnostics: List[Dict[str, Any]] = []
    unresolved_icons: List[Dict[str, Any]] = []
    header_pages = 0
    current_identity: Optional[Dict[str, str]] = None

    for page_index, page in enumerate(doc):
  headers = _header_positions(page)
  if not headers:
      page_diagnostics.append({
          "page": page_index + 1,
          "status": "NO_SEMANTIC_GRID_HEADER",
      })
      continue

  header_pages += 1
  markers, unresolved = _phase_markers(doc, page, headers["phase"])
  unresolved_icons.extend([
      {"page": page_index + 1, **x} for x in unresolved
  ])

  # Column starts are supplied by the document's own semantic headers.
  asset_x = max(0.0, headers["asset"] - 8)
  ta_x = headers["therapeuticArea"] - 5
  ind_x = headers["indication"] - 5
  mod_x = headers["modality"] - 5
  phase_x = headers["phase"] - 5
  right_x = min(page.rect.width - 8, phase_x + max(42, page.rect.width * 0.10))

  parsed_here = 0
  rejected_here = 0

  for marker in markers:
      band = _row_band_for_marker(page, marker["rect"])
      # Clip strictly to the data-row band to avoid DESCRIPTION prose.
      raw_asset = _clip_text(page, fitz.Rect(asset_x, band.y0, ta_x, band.y1))
      therapeutic_area = _clip_text(page, fitz.Rect(ta_x, band.y0, ind_x, band.y1))
      indication = _clip_text(page, fitz.Rect(ind_x, band.y0, mod_x, band.y1))
      modality = _clip_text(page, fitz.Rect(mod_x, band.y0, phase_x, band.y1))

      if raw_asset:
          current_identity = _parse_identity(raw_asset)

      identity = current_identity or {
          "asset": "",
          "molecule": "",
          "developmentCode": "",
          "brand": "",
          "sourceIdentity": "",
      }

      if not (identity["asset"] and indication and marker["phase"]):
          rejected_here += 1
          continue

      candidates.append({
          "company": company,
          "sourceFamily": "Company Pipeline",
          "sourceRecordId": f"pdf-grid:{page_index + 1}:{len(candidates) + 1}",
          "sourceUrl": source_url,
          "asset": identity["asset"],
          "molecule": identity["molecule"],
          "developmentCode": identity["developmentCode"],
          "brand": identity["brand"],
          "indication": indication,
          "phase": marker["phase"],
          "phaseEvidence": "SOURCE_PDF_ICON",
          "programStatus": "",
          "sponsorOwner": company,
          "partners": [],
          "study": "",
          "trialIds": [],
          "therapeuticArea": therapeutic_area,
          "mechanismOfAction": "",
          "modality": modality,
          "sourceNotes": "",
          "sourceOrdinal": len(candidates) + 1,
          "parserMethod": "SEMANTIC_PDF_GRID",
          "sourceAdapter": ADAPTER_PROFILE,
          "sourcePage": page_index + 1,
          "sourceIdentity": identity["sourceIdentity"],
          "phaseIcon": marker["colour"],
      })
      parsed_here += 1

  page_diagnostics.append({
      "page": page_index + 1,
      "status": "PARSED",
      "headerStarts": {
          k: round(v, 2)
          for k, v in headers.items()
          if k != "headerY"
      },
      "phaseMarkers": len(markers),
      "unresolvedPhaseIcons": len(unresolved),
      "parsedRows": parsed_here,
      "rejectedRows": rejected_here,
  })

    deduped: List[Dict[str, Any]] = []
    seen = set()
    duplicate_count = 0
    for row in candidates:
  key = (
      norm(row["asset"]),
      norm(row["indication"]),
      norm(row["phase"]),
  )
  if key in seen:
      duplicate_count += 1
      continue
  seen.add(key)
  row["sourceOrdinal"] = len(deduped) + 1
  row["sourceRecordId"] = f"pdf-grid:{row['sourcePage']}:{row['sourceOrdinal']}"
  deduped.append(row)

    phase_counts = Counter(r["phase"] for r in deduped)
    diagnostics = {
  "pageCount": len(doc),
  "semanticHeaderPages": header_pages,
  "pages": page_diagnostics,
  "candidateRows": len(candidates),
  "dedupedRows": len(deduped),
  "phaseCounts": dict(phase_counts),
  "unresolvedPhaseIcons": unresolved_icons[:30],
  "unresolvedPhaseIconCount": len(unresolved_icons),
  "duplicateRowsRemoved": duplicate_count,
  "exactDuplicatesRemoved": duplicate_count,
  "exactDuplicates": 0,
  "phaseUnresolved": len(unresolved_icons),
  "rowFailures": sum(int(x.get("rejectedRows", 0)) for x in page_diagnostics),
  "boundaryWarnings": 0,
  "companySpecificParserBranch": False,
  "portfolioDependentValidation": False,
  "writes": 0,
    }
    return deduped, diagnostics


async def download_pdf(url: str, timeout_seconds: float) -> Tuple[bytes, str]:
    await _assert_public_http_url(url)
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
  raise HTTPException(status_code=400, detail="Only public http/https URLs are allowed")

    headers = {
  "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) SemanticPipelinePdf/1.0",
  "Accept": "application/pdf,*/*;q=0.8",
    }
    try:
  async with httpx.AsyncClient(
      timeout=httpx.Timeout(timeout_seconds, connect=12.0),
      follow_redirects=True,
      headers=headers,
  ) as client:
      response = await client.get(url)
    except httpx.TimeoutException as exc:
  raise HTTPException(status_code=504, detail="Pipeline PDF fetch timed out") from exc
    except httpx.HTTPError as exc:
  raise HTTPException(status_code=502, detail=f"Pipeline PDF fetch failed: {exc}") from exc

    if response.status_code != 200:
  raise HTTPException(status_code=502, detail=f"Pipeline PDF source returned HTTP {response.status_code}")
    if len(response.content) > MAX_BYTES:
  raise HTTPException(status_code=413, detail="Pipeline PDF exceeds size limit")
    if not response.content.startswith(b"%PDF"):
  raise HTTPException(status_code=502, detail="Pipeline source did not return a PDF")

    final_url = str(response.url)
    await _assert_public_http_url(final_url)
    return response.content, final_url


async def extract_generic_pdf_grid(
    company: str,
    source_url: str,
    timeout_seconds: float = 35.0,
) -> GenericPdfGridPipelineResponse:
    data, final_url = await download_pdf(source_url, timeout_seconds)
    rows, diagnostics = parse_semantic_pdf_grid(company, final_url, data)

    issues: List[str] = []
    incomplete = [
  r["sourceRecordId"]
  for r in rows
  if not (r.get("asset") and r.get("indication") and r.get("phase"))
    ]

    if len(rows) < MIN_ROWS:
  issues.append(f"too few structured rows: {len(rows)} < {MIN_ROWS}")
    if diagnostics.get("semanticHeaderPages", 0) < 1:
  issues.append("no semantic PDF-grid headers detected")
    if diagnostics.get("unresolvedPhaseIconCount", 0) > 0:
  issues.append(
      f"{diagnostics['unresolvedPhaseIconCount']} phase-column icons could not be classified"
  )
    if diagnostics.get("rowFailures", 0) > 0:
  issues.append(f"{diagnostics['rowFailures']} source rows were structurally incomplete")
    if incomplete:
  issues.append(f"{len(incomplete)} parsed rows missing core fields")

    ready = not issues
    validation = {
  "pass": ready,
  "rowCount": len(rows),
  "issues": issues,
  "allCoreRowsComplete": not incomplete,
  "semanticHeaderFound": diagnostics.get("semanticHeaderPages", 0) > 0,
  "phaseMarkersResolved": diagnostics.get("unresolvedPhaseIconCount", 0) == 0,
    }
    summary = {
  "structuralValidationPass": ready,
  "actual": {"Total": len(rows)},
  "productionStatus": (
      "READY FOR AIRTABLE DELTA COMPARISON"
      if ready
      else "FAIL CLOSED - PARSER/STRUCTURE REVIEW REQUIRED"
  ),
  "selectedMethod": "SEMANTIC_PDF_GRID",
  "portfolioDependentValidation": False,
  "companySpecificParserBranch": False,
  "writeMode": "READ_ONLY",
    }

    return GenericPdfGridPipelineResponse(
  version=ADAPTER_PROFILE,
  routeVersion=ROUTE_VERSION,
  company=company,
  sourceUrl=source_url,
  finalUrl=final_url,
  retrievalMode="STATIC_DOCUMENT",
  readOnly=True,
  readyForDiscovery=ready,
  rowCount=len(rows),
  rows=rows,
  summary=summary,
  issues=[{"issue": issue} for issue in issues],
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
      "semanticHeaderRequired": True,
      "unknownPhaseIconFailsClosed": True,
  },
    )


@app.get("/extract/generic/pdf-grid-pipeline/health")
async def generic_pdf_grid_health() -> Dict[str, Any]:
    return {
  "ok": True,
  "version": ADAPTER_PROFILE,
  "routeVersion": ROUTE_VERSION,
  "retrievalMode": "STATIC_DOCUMENT",
  "readOnly": True,
    }


@app.get("/extract/generic/pdf-grid-pipeline", response_model=GenericPdfGridPipelineResponse)
async def generic_pdf_grid_pipeline(
    company: str = Query(..., min_length=1, max_length=160),
    source_url: str = Query(..., min_length=8),
    timeout_seconds: float = Query(default=35.0, ge=5.0, le=35.0),
    x_adapter_key: Optional[str] = Header(default=None),
) -> GenericPdfGridPipelineResponse:
    _auth(x_adapter_key)
    return await extract_generic_pdf_grid(company, source_url, timeout_seconds)
