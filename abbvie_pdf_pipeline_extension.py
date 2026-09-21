"""Read-only AbbVie investor pipeline PDF adapter.

Parses the official quarterly AbbVie Pipeline Update PDF. The source encodes
phase by four visual columns and therapeutic area by colored bullet squares.
No Airtable or master-data writes.
"""
from __future__ import annotations

import asyncio
import hashlib
import math
import re
from typing import Any, Dict, List, Optional, Tuple

import fitz
from fastapi import Header, HTTPException, Query
from pydantic import BaseModel

from main import _auth, app
from generic_pdf_pipeline_extension import download_pdf


ADAPTER_PROFILE = "PIPELINE_ABBVIE_PDF_V1"
ROUTE_VERSION = "ABBVIE_PIPELINE_PDF_V1.0_READ_ONLY"
MIN_ROWS = 20


class AbbViePipelineResponse(BaseModel):
    version: str
    routeVersion: str
    company: str
    sourceUrl: str
    finalUrl: str
    sourceDate: Optional[str] = None
    retrievalMode: str
    readOnly: bool
    readyForDiscovery: bool
    rowCount: int
    rows: List[Dict[str, Any]]
    summary: Dict[str, Any]
    issues: List[Dict[str, Any]]
    diagnostics: Dict[str, Any]
    guardrails: Dict[str, Any]


def clean(v: Any) -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip()


def norm(v: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", clean(v).lower()).strip()


def word_y(w: Tuple[Any, ...]) -> float:
    return (float(w[1]) + float(w[3])) / 2.0


def line_groups(words: List[Tuple[Any, ...]], tol: float = 3.5) -> List[Dict[str, Any]]:
    lines: List[Dict[str, Any]] = []
    for w in sorted(words, key=lambda x: (word_y(x), float(x[0]))):
        y = word_y(w)
        target = None
        for line in reversed(lines[-4:]):
            if abs(line["y"] - y) <= tol:
                target = line
                break
        if target is None:
            target = {"y": y, "words": []}
            lines.append(target)
        target["words"].append(w)
        target["y"] = sum(word_y(x) for x in target["words"]) / len(target["words"])
    for line in lines:
        line["words"].sort(key=lambda x: float(x[0]))
        line["text"] = clean(" ".join(str(w[4]) for w in line["words"]))
        line["x0"] = min(float(w[0]) for w in line["words"])
        line["x1"] = max(float(w[2]) for w in line["words"])
    return lines


def _header_columns(page: fitz.Page) -> Optional[List[Dict[str, Any]]]:
    words = page.get_text("words")
    lines = line_groups(words, 4.0)
    target = None
    for line in lines:
        t = norm(line["text"])
        if "phase 1" in t and "phase 2" in t and "submitted" in t and ("registrational" in t or "phase 3" in t):
            target = line
            break
    if target is None:
        return None

    header_words = target["words"]

    def span_for(pattern: str) -> Optional[Tuple[float, float]]:
        text_tokens = [clean(w[4]) for w in header_words]
        joined = " ".join(text_tokens)
        m = re.search(pattern, joined, re.I)
        if not m:
            return None
        prefix = joined[:m.start()]
        start_idx = len(prefix.split())
        count = max(1, len(joined[m.start():m.end()].split()))
        selected = header_words[start_idx:start_idx + count]
        if not selected:
            return None
        return min(float(w[0]) for w in selected), max(float(w[2]) for w in selected)

    specs = [
        ("Phase 1", r"Phase\s+1"),
        ("Phase 2", r"Phase\s+2"),
        ("Registrational / Phase 3", r"Registrational\s*/\s*Phase\s+3"),
        ("Submitted", r"Submitted"),
    ]
    cols = []
    for phase, pat in specs:
        span = span_for(pat)
        if not span:
            return None
        cols.append({"phase": phase, "center": (span[0] + span[1]) / 2.0, "headerY": target["y"]})

    cols.sort(key=lambda x: x["center"])
    bounds = [0.0]
    for a, b in zip(cols, cols[1:]):
        bounds.append((a["center"] + b["center"]) / 2.0)
    bounds.append(float(page.rect.width))
    for i, col in enumerate(cols):
        col["left"] = bounds[i]
        col["right"] = bounds[i + 1]
    return cols


def _small_filled_rectangles(page: fitz.Page) -> List[Dict[str, Any]]:
    out = []
    for d in page.get_drawings():
        rect = d.get("rect")
        fill = d.get("fill")
        if not rect or fill is None:
            continue
        width = float(rect.x1 - rect.x0)
        height = float(rect.y1 - rect.y0)
        if 3.0 <= width <= 16.0 and 3.0 <= height <= 16.0:
            out.append({
                "x": (float(rect.x0) + float(rect.x1)) / 2.0,
                "y": (float(rect.y0) + float(rect.y1)) / 2.0,
                "rect": rect,
                "fill": tuple(round(float(c), 4) for c in fill),
            })
    return out


def _color_distance(a: Tuple[float, ...], b: Tuple[float, ...]) -> float:
    return math.sqrt(sum((float(x) - float(y)) ** 2 for x, y in zip(a, b)))


def _legend_map(page: fitz.Page, rects: List[Dict[str, Any]]) -> Dict[Tuple[float, ...], str]:
    words = page.get_text("words")
    labels = {
        "immunology": "Immunology",
        "oncology": "Oncology",
        "neuroscience": "Neuroscience",
        "aesthetics": "Aesthetics",
        "eye care": "Eye Care",
        "targeted investment": "Targeted Investment",
    }
    mapping: Dict[Tuple[float, ...], str] = {}
    for line in line_groups(words, 3.5):
        key = norm(line["text"])
        label = labels.get(key)
        if not label:
            continue
        y = float(line["y"])
        x0 = float(line["x0"])
        candidates = [
            r for r in rects
            if abs(r["y"] - y) <= 8.0 and r["x"] < x0 and x0 - r["x"] <= 45.0
        ]
        if candidates:
            nearest = min(candidates, key=lambda r: abs(r["y"] - y) + abs(x0 - r["x"]) / 10.0)
            mapping[nearest["fill"]] = label
    return mapping


def _ta_for_fill(fill: Tuple[float, ...], legend: Dict[Tuple[float, ...], str]) -> str:
    if not legend:
        return ""
    best = min(legend.items(), key=lambda kv: _color_distance(fill, kv[0]))
    return best[1] if _color_distance(fill, best[0]) <= 0.08 else ""


def _extract_code(text: str) -> str:
    patterns = [
        r"\bABBV[- ]?\d{2,5}\b",
        r"\bAGN[- ]?\d{3,8}\b",
        r"\bAPG[- ]?\d{2,6}\b",
        r"\bKST[- ]?\d{2,6}\b",
        r"\bSIM\d{3,6}\b",
        r"\bUB[- ]?VV\d{2,5}\b",
        r"\bRC\d{2,6}\b",
    ]
    for p in patterns:
        m = re.search(p, text, re.I)
        if m:
            return clean(m.group(0).upper().replace(" ", "-") if " " in m.group(0) else m.group(0).upper())
    return ""


def _parse_entry(text: str) -> Tuple[str, str, str]:
    s = clean(text).lstrip("■▪•").strip()
    if not s:
        return "", "", ""

    # Base asset name is the text before the first immediate parenthetical
    # mechanism/alias. Without one, use the first token; AbbVie's source uses
    # that form for entries such as GemibotA.
    first_paren = s.find("(")
    if first_paren >= 0:
        asset = clean(s[:first_paren]).rstrip("*‡").strip()
        pos = first_paren

        # Consume one or more adjacent parenthetical groups belonging to the
        # base asset (mechanism, alias/development code).
        while pos < len(s):
            while pos < len(s) and s[pos].isspace():
                pos += 1
            if pos < len(s) and s[pos] in "*‡":
                pos += 1
                continue
            if pos >= len(s) or s[pos] != "(":
                break
            depth = 0
            j = pos
            while j < len(s):
                if s[j] == "(":
                    depth += 1
                elif s[j] == ")":
                    depth -= 1
                    if depth == 0:
                        j += 1
                        break
                j += 1
            pos = j
    else:
        m = re.match(r"(\S+)\s+(.*)$", s)
        if not m:
            return "", "", ""
        asset = clean(m.group(1)).rstrip("*‡")
        pos = len(m.group(1))

    # Include explicit combination partners after "+" in asset identity.
    while True:
        remainder = s[pos:].lstrip()
        if not remainder.startswith("+"):
            break
        pos = len(s) - len(remainder) + 1
        while pos < len(s) and s[pos].isspace():
            pos += 1
        m = re.match(r"([^\s(]+)", s[pos:])
        if not m:
            break
        partner = clean(m.group(1)).rstrip("*‡")
        asset = clean(asset + " + " + partner)
        pos += len(m.group(1))
        while pos < len(s) and s[pos].isspace():
            pos += 1
        if pos < len(s) and s[pos] == "(":
            depth = 0
            j = pos
            while j < len(s):
                if s[j] == "(":
                    depth += 1
                elif s[j] == ")":
                    depth -= 1
                    if depth == 0:
                        j += 1
                        break
                j += 1
            pos = j

    indication = clean(s[pos:])
    indication = re.sub(r"^[*‡]+", "", indication).strip()
    code = _extract_code(s)
    return asset, indication, code


def _pdf_bullet_spans(page: fitz.Page) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    info = page.get_text("dict")
    for block in info.get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                if clean(span.get("text")) != "■":
                    continue
                bbox = span.get("bbox") or [0, 0, 0, 0]
                out.append({
                    "x0": float(bbox[0]),
                    "y0": float(bbox[1]),
                    "x1": float(bbox[2]),
                    "y1": float(bbox[3]),
                    "cx": (float(bbox[0]) + float(bbox[2])) / 2.0,
                    "cy": (float(bbox[1]) + float(bbox[3])) / 2.0,
                    "size": float(span.get("size") or 0.0),
                    "color": int(span.get("color") or 0),
                })
    return out


def _legend_from_bullet_spans(page: fitz.Page, bullet_spans: List[Dict[str, Any]]) -> Dict[int, str]:
    words = page.get_text("words")
    expected = {
        "immunology": "Immunology",
        "oncology": "Oncology",
        "neuroscience": "Neuroscience",
        "aesthetics": "Aesthetics",
        "eye care": "Eye Care",
        "targeted investment": "Targeted Investment",
    }

    # Isolate the right-side legend text before line grouping. Pipeline rows
    # elsewhere on the same baseline must not be merged with legend labels.
    legend_words = [w for w in words if float(w[0]) >= 590.0]
    legend_lines = line_groups(legend_words, 3.5)
    label_lines = sorted(
        [line for line in legend_lines if norm(line["text"]) in expected],
        key=lambda line: float(line["y"]),
    )
    legend_bullets = sorted(
        [b for b in bullet_spans if b["size"] >= 15.0],
        key=lambda b: b["cy"],
    )

    mapping: Dict[int, str] = {}
    if len(legend_bullets) == 6 and len(label_lines) == 6:
        for bullet, line in zip(legend_bullets, label_lines):
            mapping[int(bullet["color"])] = expected[norm(line["text"])]
        return mapping

    # Defensive fallback for future source layout changes. Match only a label
    # immediately to the right and slightly below the square's visual centre.
    for bullet in legend_bullets:
        candidates = [
            line for line in label_lines
            if -1.0 <= float(line["y"]) - bullet["cy"] <= 12.0
        ]
        if not candidates:
            continue
        chosen = min(candidates, key=lambda line: abs(float(line["y"]) - bullet["cy"]))
        mapping[int(bullet["color"])] = expected[norm(chosen["text"])]
    return mapping

def _ta_for_anchor(
    anchor_word: Tuple[Any, ...],
    bullet_spans: List[Dict[str, Any]],
    legend: Dict[int, str],
) -> str:
    x = float(anchor_word[0])
    y = word_y(anchor_word)
    candidates = [
        b for b in bullet_spans
        if b["size"] < 15.0
        and abs(b["x0"] - x) <= 4.0
        and abs(b["cy"] - y) <= 6.0
    ]
    if not candidates:
        return ""
    bullet = min(candidates, key=lambda b: abs(b["cy"] - y) + abs(b["x0"] - x))
    return legend.get(int(bullet["color"]), "")


def _stable_source_record_id(phase: str, asset: str, indication: str) -> str:
    raw = "|".join([norm(phase), norm(asset), norm(indication)])
    return "abbvie:" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:18]


def _source_date(page_text: str) -> Optional[str]:
    m = re.search(r"As of\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})", page_text, re.I)
    return clean(m.group(1)) if m else None


def parse_pdf(company: str, source_url: str, data: bytes) -> Tuple[List[Dict[str, Any]], Dict[str, Any], Optional[str]]:
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid AbbVie pipeline PDF: {exc}") from exc

    selected_page = None
    columns = None
    for idx in range(len(doc)):
        page = doc[idx]
        cols = _header_columns(page)
        if cols:
            selected_page = page
            columns = cols
            page_index = idx
            break
    if selected_page is None or not columns:
        return [], {"pageCount": len(doc), "reason": "PHASE_COLUMN_HEADER_NOT_FOUND", "writes": 0}, None

    page = selected_page
    words = page.get_text("words")
    page_text = page.get_text("text", sort=True)
    bullet_spans = _pdf_bullet_spans(page)
    ta_legend = _legend_from_bullet_spans(page, bullet_spans)

    header_y = min(float(c["headerY"]) for c in columns)
    footer_y_candidates = []
    for line in line_groups(words, 3.5):
        t = norm(line["text"])
        if t.startswith("new clinical programs") or t.startswith("as of july"):
            footer_y_candidates.append(float(line["y"]))
    body_top = header_y + 10.0
    body_bottom = min(footer_y_candidates) - 5.0 if footer_y_candidates else float(page.rect.height) - 55.0

    # In this source PDF the coloured therapeutic-area square and the first
    # asset token are emitted as one word (e.g. "■ABBV-243"). That is a more
    # reliable row boundary than vector drawings, because the phase columns
    # have independent vertical spacing and wrapped indications.
    rows: List[Dict[str, Any]] = []
    failures = []
    phase_counts: Dict[str, int] = {}
    column_diags = []

    for col_idx, col in enumerate(columns, 1):
        anchors = []
        for w in words:
            token = clean(w[4])
            x0 = float(w[0])
            y = word_y(w)
            if not (col["left"] <= x0 < col["right"]):
                continue
            if not (body_top <= y < body_bottom):
                continue
            if not token.startswith("■") or token == "■":
                continue
            anchors.append((y, w))

        # Word extraction can theoretically duplicate a glyph at the same
        # baseline. Keep one source anchor per visual row.
        dedup_anchors = []
        for y, w in sorted(anchors, key=lambda item: item[0]):
            if dedup_anchors and abs(dedup_anchors[-1][0] - y) <= 2.0:
                continue
            dedup_anchors.append((y, w))
        anchors = dedup_anchors

        parsed_here = 0
        for i, (anchor_y, anchor_word) in enumerate(anchors):
            next_y = anchors[i + 1][0] if i + 1 < len(anchors) else body_bottom
            # Include all text belonging to this row until the next explicit
            # bullet in the same phase column. This preserves wrapped disease
            # names without borrowing text from adjacent columns.
            item_words = [
                w for w in words
                if col["left"] <= float(w[0]) < col["right"]
                and anchor_y - 3.5 <= word_y(w) < next_y - 2.0
            ]
            if not item_words:
                continue

            grouped = line_groups(item_words, 3.2)
            entry = clean(" ".join(line["text"] for line in grouped))
            asset, indication, code = _parse_entry(entry)

            if not asset or not indication:
                failures.append({
                    "phaseColumn": col["phase"],
                    "entry": entry,
                    "reason": "ASSET_INDICATION_SPLIT",
                })
                continue

            phase = (
                "Phase 3" if col["phase"] == "Registrational / Phase 3"
                else "Filed / Registration" if col["phase"] == "Submitted"
                else col["phase"]
            )

            therapeutic_area = _ta_for_anchor(anchor_word, bullet_spans, ta_legend)

            rows.append({
                "company": company,
                "sourceFamily": "Company Pipeline",
                "sourceRecordId": _stable_source_record_id(phase, asset, indication),
                "sourceUrl": source_url,
                "asset": asset,
                "molecule": "",
                "developmentCode": code,
                "brand": "",
                "indication": indication,
                "phase": phase,
                "phaseEvidence": "SOURCE_PDF_PHASE_COLUMN",
                "programStatus": "Submitted" if col["phase"] == "Submitted" else "Active",
                "sponsorOwner": company,
                "partners": [],
                "study": "",
                "trialIds": [],
                "therapeuticArea": therapeutic_area,
                "sourceStageText": col["phase"],
                "sourceOrdinal": len(rows) + 1,
                "parserMethod": "ABBVIE_PDF_BULLET_ROW",
                "sourceAdapter": ADAPTER_PROFILE,
                "sourceEntry": entry,
            })
            parsed_here += 1
            phase_counts[phase] = phase_counts.get(phase, 0) + 1

        column_diags.append({
            "phaseColumn": col["phase"],
            "anchorRows": len(anchors),
            "parsedRows": parsed_here,
        })

    # Exact source-grain de-duplication only.
    deduped = []
    seen = set()
    duplicates = 0
    for row in rows:
        key = (norm(row["asset"]), norm(row["indication"]), norm(row["phase"]))
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        row["sourceOrdinal"] = len(deduped) + 1
        deduped.append(row)

    ta_missing = sum(1 for row in deduped if not clean(row.get("therapeuticArea")))

    diag = {
        "pageCount": len(doc),
        "pipelinePage": page_index + 1,
        "phaseColumns": column_diags,
        "candidateRows": len(rows),
        "dedupedRows": len(deduped),
        "exactDuplicates": duplicates,
        "rowFailures": len(failures),
        "failureSamples": failures[:12],
        "phaseCounts": phase_counts,
        "therapeuticAreaLegend": ta_legend,
        "therapeuticAreaMissing": ta_missing,
        "portfolioDependentValidation": False,
        "companySpecificParserBranch": True,
        "writes": 0,
    }
    return deduped, diag, _source_date(page_text)


async def _download_with_retry(source_url: str, timeout_seconds: float) -> tuple[bytes, str]:
    last_error = None
    for attempt in range(3):
        try:
            return await download_pdf(source_url, timeout_seconds)
        except HTTPException as exc:
            last_error = exc
            retryable = exc.status_code in {502, 504}
            if not retryable or attempt == 2:
                raise
            await asyncio.sleep(1.5 * (attempt + 1))
    raise last_error or HTTPException(status_code=502, detail="AbbVie PDF retrieval failed")


async def extract_abbvie_pipeline(company: str, source_url: str, timeout_seconds: float = 35.0) -> AbbViePipelineResponse:
    data, final_url = await _download_with_retry(source_url, timeout_seconds)
    rows, diagnostics, source_date = parse_pdf(company, final_url, data)

    issues = []
    if len(rows) < MIN_ROWS:
        issues.append(f"too few structured rows: {len(rows)} < {MIN_ROWS}")
    if diagnostics.get("rowFailures", 0) > 0:
        issues.append(f"{diagnostics['rowFailures']} PDF rows could not be split into asset and indication")
    if diagnostics.get("exactDuplicates", 0) > 0:
        issues.append(f"{diagnostics['exactDuplicates']} exact duplicate PDF rows detected")
    if diagnostics.get("therapeuticAreaMissing", 0) > 0:
        issues.append(f"{diagnostics['therapeuticAreaMissing']} PDF rows are missing source therapeutic-area mapping")
    if len(diagnostics.get("phaseCounts", {})) < 4:
        issues.append("not all four source phase columns produced rows")
    ready = not issues

    return AbbViePipelineResponse(
        version=ADAPTER_PROFILE,
        routeVersion=ROUTE_VERSION,
        company=company,
        sourceUrl=source_url,
        finalUrl=final_url,
        sourceDate=source_date,
        retrievalMode="STATIC_DOCUMENT",
        readOnly=True,
        readyForDiscovery=ready,
        rowCount=len(rows),
        rows=rows,
        summary={
            "structuralValidationPass": ready,
            "actual": {"Total": len(rows)},
            "productionStatus": "READY FOR AIRTABLE DELTA COMPARISON" if ready else "FAIL CLOSED - PARSER/STRUCTURE REVIEW REQUIRED",
            "selectedMethod": "ABBVIE_PDF_BULLET_ROW",
            "portfolioDependentValidation": False,
            "writeMode": "READ_ONLY",
        },
        issues=[{"issue": x} for x in issues],
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


@app.get("/extract/abbvie/pdf-pipeline/health")
async def abbvie_health() -> Dict[str, Any]:
    return {"ok": True, "version": ADAPTER_PROFILE, "routeVersion": ROUTE_VERSION, "readOnly": True}


@app.get("/extract/abbvie/pdf-pipeline", response_model=AbbViePipelineResponse)
async def abbvie_route(
    company: str = Query(default="AbbVie", min_length=1, max_length=160),
    source_url: str = Query(..., min_length=8),
    timeout_seconds: float = Query(default=35.0, ge=5.0, le=35.0),
    x_adapter_key: Optional[str] = Header(default=None),
) -> AbbViePipelineResponse:
    _auth(x_adapter_key)
    return await extract_abbvie_pipeline(company, source_url, timeout_seconds)
