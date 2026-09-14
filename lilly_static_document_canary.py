"""
Lilly STATIC_DOCUMENT source canary — READ ONLY.

Purpose
-------
Prove a stable first-party Lilly acquisition route using the official Q2 2026
investor presentation rather than the intermittently blocked live pipeline page.

The canary downloads the official investor PDF, locates the Lilly Select Pipeline
slide, extracts programme cells from PDF vector geometry, separates asset vs
indication using source typography, and emits structured rows.

NO Airtable or master-data writes are performed.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from typing import Any, Dict, List, Tuple

import fitz  # PyMuPDF
import httpx

VERSION = "LILLY_STATIC_DOCUMENT_CANARY_V1.1_READ_ONLY"
SOURCE_URL = "https://investor.lilly.com/static-files/ab69001c-650b-44f6-b629-309ee33f2335"
EXPECTED_SOURCE_DATE = "August 3, 2026"


def clean(value: Any) -> str:
    s = str(value or "")
    s = (
        s.replace("\u00ad", "")
        .replace("\u2010", "-")
        .replace("\u2011", "-")
        .replace("\u2012", "-")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("\u2212", "-")
    )
    return re.sub(r"\s+", " ", s).strip()


def norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", clean(value).lower()).strip()


def is_red(color: int) -> bool:
    r = (int(color) >> 16) & 255
    g = (int(color) >> 8) & 255
    b = int(color) & 255
    return r >= 150 and g <= 130 and b <= 130


def is_italic(span: Dict[str, Any]) -> bool:
    font = str(span.get("font", "")).lower()
    flags = int(span.get("flags", 0))
    # PyMuPDF TEXT_FONT_ITALIC is bit 1; retain a font-name fallback.
    return bool(flags & 2) or "italic" in font or "oblique" in font


def download_pdf() -> bytes:
    headers = {
        "User-Agent": "PharmaPipelineAdapter/2.41 (+official-investor-source-reader)",
        "Accept": "application/pdf,*/*;q=0.8",
    }
    with httpx.Client(timeout=45.0, follow_redirects=True, headers=headers) as client:
        response = client.get(SOURCE_URL)
        status = response.status_code
        content = response.content
    if status != 200:
        raise RuntimeError(f"Official Lilly investor document returned HTTP {status}")
    if not content.startswith(b"%PDF"):
        raise RuntimeError("Official Lilly investor source did not return a PDF")
    return content


def find_pipeline_page(doc: fitz.Document) -> Tuple[int, fitz.Page, str]:
    matches: List[Tuple[int, str]] = []
    for idx in range(len(doc)):
        page = doc[idx]
        text = clean(page.get_text("text"))
        if "Lilly Select Pipeline" in text and "PHASE 2" in text and "PHASE 3" in text:
            matches.append((idx, text))
    if len(matches) != 1:
        raise RuntimeError(f"Expected exactly one Lilly Select Pipeline slide; found {len(matches)}")
    idx, text = matches[0]
    return idx, doc[idx], text


def rect_key(r: fitz.Rect) -> Tuple[int, int, int, int]:
    return tuple(int(round(v * 2)) for v in (r.x0, r.y0, r.x1, r.y1))


def candidate_cell_rects(page: fitz.Page) -> List[fitz.Rect]:
    w, h = page.rect.width, page.rect.height
    rects: Dict[Tuple[int, int, int, int], fitz.Rect] = {}
    for drawing in page.get_drawings():
        for item in drawing.get("items", []):
            if not item or item[0] != "re":
                continue
            r = fitz.Rect(item[1])
            rw, rh = r.width / w, r.height / h
            if not (0.09 <= rw <= 0.135 and 0.035 <= rh <= 0.08):
                continue
            if r.y0 < 0.16 * h or r.y1 > 0.88 * h:
                continue
            rects[rect_key(r)] = r
    return sorted(rects.values(), key=lambda r: (r.y0, r.x0))


def spans_in_rect(page_dict: Dict[str, Any], rect: fitz.Rect) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for block in page_dict.get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                srect = fitz.Rect(span.get("bbox", (0, 0, 0, 0)))
                cx = (srect.x0 + srect.x1) / 2
                cy = (srect.y0 + srect.y1) / 2
                if rect.x0 - 1 <= cx <= rect.x1 + 1 and rect.y0 - 1 <= cy <= rect.y1 + 1:
                    txt = clean(span.get("text", ""))
                    if txt:
                        out.append(
                            {
                                "text": txt,
                                "color": int(span.get("color", 0)),
                                "bbox": tuple(float(x) for x in srect),
                                "size": float(span.get("size", 0)),
                                "font": str(span.get("font", "")),
                                "flags": int(span.get("flags", 0)),
                            }
                        )
    return sorted(out, key=lambda s: (s["bbox"][1], s["bbox"][0]))


def join_spans(spans: List[Dict[str, Any]]) -> str:
    if not spans:
        return ""
    lines: List[List[Dict[str, Any]]] = []
    for span in spans:
        cy = (span["bbox"][1] + span["bbox"][3]) / 2
        if not lines:
            lines.append([span])
            continue
        current = lines[-1]
        current_y = sum((x["bbox"][1] + x["bbox"][3]) / 2 for x in current) / len(current)
        if abs(cy - current_y) <= 4.0:
            current.append(span)
        else:
            lines.append([span])
    parts = []
    for line in lines:
        line = sorted(line, key=lambda s: s["bbox"][0])
        part = clean(" ".join(s["text"] for s in line))
        if part:
            parts.append(part)
    return clean(" ".join(parts))


def classify_status(rect: fitz.Rect, page: fitz.Page, approved_y: float) -> str:
    x = ((rect.x0 + rect.x1) / 2) / page.rect.width
    cy = (rect.y0 + rect.y1) / 2
    if x < 0.375:
        return "Phase 2"
    if x < 0.855:
        return "Phase 3"
    return "Approved" if cy < approved_y else "Reg Review"


def parse_pipeline(page: fitz.Page) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    page_dict = page.get_text("dict")
    words = page.get_text("words")
    approved_words = [w for w in words if norm(w[4]) == "approved"]
    if len(approved_words) != 1:
        raise RuntimeError(f"Expected one APPROVED banner label; found {len(approved_words)}")
    approved_y = float(approved_words[0][1])

    rows: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []
    for rect in candidate_cell_rects(page):
        spans = spans_in_rect(page_dict, rect)
        all_text = join_spans(spans)
        n = norm(all_text)
        if not all_text:
            continue
        if n in {"nme", "nilex other"}:
            continue
        if any(k in n for k in ["addition or milestone achieved", "updates since"]):
            continue

        # Lilly encodes the programme name in upright text and the indication in
        # italic text. Colour is retained as an additional signal, but typography
        # is the primary split because PDF extraction normalises some red glyphs.
        indication_spans = [s for s in spans if is_italic(s) or is_red(s["color"])]
        asset_spans = [s for s in spans if s not in indication_spans]
        asset = join_spans(asset_spans)
        indication = join_spans(indication_spans)

        if not asset or not indication:
            rejected.append(
                {
                    "text": all_text,
                    "asset": asset,
                    "indication": indication,
                    "rect": [round(v, 2) for v in (rect.x0, rect.y0, rect.x1, rect.y1)],
                    "spans": [
                        {
                            "text": s["text"],
                            "font": s["font"],
                            "flags": s["flags"],
                            "color": s["color"],
                        }
                        for s in spans[:8]
                    ],
                }
            )
            continue

        status = classify_status(rect, page, approved_y)
        rows.append(
            {
                "phase": status,
                "asset": asset,
                "indication": indication,
                "sourcePage": page.number + 1,
                "sourceUrl": SOURCE_URL,
            }
        )

    deduped: List[Dict[str, Any]] = []
    seen = set()
    for row in rows:
        key = (norm(row["phase"]), norm(row["asset"]), norm(row["indication"]))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)

    diagnostics = {
        "candidateCellCount": len(candidate_cell_rects(page)),
        "rejectedCellCount": len(rejected),
        "rejectedSamples": rejected[:8],
        "approvedBannerY": round(approved_y, 2),
    }
    return deduped, diagnostics


def main() -> int:
    result: Dict[str, Any] = {
        "version": VERSION,
        "sourceUrl": SOURCE_URL,
        "retrievalMode": "STATIC_DOCUMENT",
        "readOnly": True,
        "masterWritesPerformed": 0,
        "parserBindingValidated": False,
        "failClosed": True,
    }

    try:
        pdf = download_pdf()
        doc = fitz.open(stream=pdf, filetype="pdf")
        page_idx, page, page_text = find_pipeline_page(doc)
        rows, diagnostics = parse_pipeline(page)

        date_match = re.search(r"As of\s+([A-Z][a-z]+\s+\d{1,2},\s+\d{4})", page_text)
        source_date = date_match.group(1) if date_match else ""
        counts = Counter(r["phase"] for r in rows)
        orforglipron = [r for r in rows if "orforglipron" in norm(r["asset"])]

        checks = {
            "officialPdfHttp200": True,
            "pipelineSlideUnique": True,
            "sourceDatePresent": bool(source_date),
            "expectedSourceDate": source_date == EXPECTED_SOURCE_DATE,
            "minimumProgrammeCount": len(rows) >= 40,
            "phase2Present": counts.get("Phase 2", 0) >= 20,
            "phase3Present": counts.get("Phase 3", 0) >= 20,
            "regReviewPresent": counts.get("Reg Review", 0) >= 1,
            "approvedPresent": counts.get("Approved", 0) >= 1,
            "orforglipronParsed": len(orforglipron) >= 4,
            "allRowsStructurallyComplete": all(r["asset"] and r["indication"] and r["phase"] for r in rows),
        }
        passed = all(checks.values())
        result.update(
            {
                "pdfBytes": len(pdf),
                "pageCount": len(doc),
                "pipelinePage": page_idx + 1,
                "sourceDate": source_date,
                "projectCount": len(rows),
                "phaseCounts": dict(counts),
                "orforglipronRows": orforglipron,
                "sampleProjects": rows[:12],
                "diagnostics": diagnostics,
                "checks": checks,
                "parserBindingValidated": passed,
                "failClosed": not passed,
            }
        )
        print("LILLY_STATIC_DOCUMENT_RESULT " + json.dumps(result, sort_keys=True, ensure_ascii=False))
        return 0 if passed else 2
    except Exception as exc:
        result["error"] = str(exc)
        print("LILLY_STATIC_DOCUMENT_RESULT " + json.dumps(result, sort_keys=True, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())
