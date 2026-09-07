import os
import re
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

import fitz  # PyMuPDF
import httpx
from fastapi import FastAPI, Header, HTTPException, Query
from pydantic import BaseModel


APP_VERSION = "V2.39.1 PFIZER ROW-BAND PDF PARSER VALIDATION"

PFIZER_PDF_URL = (
    "https://cdn.pfizer.com/pfizercom/product-pipeline/"
    "Q2_2026_Pipeline_Update_Final.pdf"
    "?VersionId=9kN5fQu52H8nq8Iop.6GssdYR2EzAJZE"
)

EXPECTED_PFIZER = {
    "Phase 1": 37,
    "Phase 2": 25,
    "Phase 3": 31,
    "Filed / Registration": 2,
    "Total": 95,
}

PHASE_RE = re.compile(r"\b(Phase\s*[123]|Registration)\b", re.I)
SUBMISSION_RE = re.compile(r"\b(New Molecular Entity|Product Enhancement)\b", re.I)
PF_CODE_RE = re.compile(r"\bPF[-\u2010-\u2015]?\d{5,8}\b", re.I)

app = FastAPI(
    title="Pharma Pipeline PDF Adapter",
    version=APP_VERSION,
    description="Read-only official-PDF extraction service for the Airtable pharma intelligence bootstrap.",
)


class ExtractionResponse(BaseModel):
    version: str
    company: str
    sourceUrl: str
    sourceDate: Optional[str] = None
    rows: List[Dict[str, Any]]
    summary: Dict[str, Any]
    issues: List[Dict[str, Any]]
    diagnostics: Dict[str, Any]


def _clean(value: Any) -> str:
    if value is None:
        return ""
    value = str(value)
    value = (
        value.replace("\u00ad", "")
        .replace("\u2010", "-")
        .replace("\u2011", "-")
        .replace("\u2012", "-")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("\u2212", "-")
        .replace("\uf0a7", "")
        .replace("\u25ba", "")
        .replace("\u0002", "-")
    )
    return re.sub(r"\s+", " ", value).strip()


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", _clean(value).lower()).strip()


def _auth(x_adapter_key: Optional[str]) -> None:
    expected = os.getenv("ADAPTER_API_KEY", "").strip()
    if expected and x_adapter_key != expected:
        raise HTTPException(status_code=401, detail="Invalid adapter key")


async def _download_pdf(url: str) -> bytes:
    headers = {
        "User-Agent": "PharmaPipelineAdapter/2.39.1 (+official-source-reader)",
        "Accept": "application/pdf,*/*;q=0.8",
    }
    timeout = httpx.Timeout(45.0, connect=15.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers=headers) as client:
        response = await client.get(url)
        response.raise_for_status()
        content = response.content

    if not content.startswith(b"%PDF"):
        raise HTTPException(status_code=502, detail="Official source did not return a valid PDF")
    return content


def _page_ta(page_text: str) -> str:
    t = _norm(page_text)
    if "inflammation and immunology" in t:
        return "Inflammation & Immunology"
    if "internal medicine" in t:
        return "Internal Medicine"
    if re.search(r"\boncology\b", t):
        return "Oncology"
    if re.search(r"\bvaccines?\b", t):
        return "Vaccines"
    return ""


def _find_header_anchors(words: List[Tuple]) -> Optional[Dict[str, float]]:
    """
    Find the x positions of the five Pfizer table columns from the header itself.
    PyMuPDF word tuple:
      x0, y0, x1, y1, text, block_no, line_no, word_no
    """
    candidates = []
    for w in words:
        text = _clean(w[4])
        n = _norm(text)
        if n in {"compound", "mechanism", "indication", "phase", "submission"}:
            candidates.append(w)

    # Group candidate header words by y coordinate. The real header sits on one/two nearby lines.
    by_y: Dict[int, List[Tuple]] = {}
    for w in candidates:
        key = int(round(float(w[1]) / 3.0) * 3)
        by_y.setdefault(key, []).append(w)

    for y in sorted(by_y):
        nearby = []
        for yy, vals in by_y.items():
            if abs(yy - y) <= 12:
                nearby.extend(vals)
        labels = {_norm(w[4]): w for w in nearby}

        needed = ["compound", "mechanism", "indication", "phase", "submission"]
        if all(k in labels for k in needed):
            return {
                "compound": float(labels["compound"][0]),
                "mechanism": float(labels["mechanism"][0]),
                "indication": float(labels["indication"][0]),
                "phase": float(labels["phase"][0]),
                "submission": float(labels["submission"][0]),
                "header_bottom": max(float(labels[k][3]) for k in needed),
            }
    return None


def _column_starts(a: Dict[str, float]) -> Dict[str, float]:
    """
    Pfizer's table headers are left-aligned with the actual data columns.
    V2.39 incorrectly used midpoints between header starts as column boundaries,
    which cut compound/mechanism/indication text in half.

    We now use the NEXT column's left edge as the boundary and assign words by x0.
    """
    return {
        "compound": float(a["compound"]),
        "mechanism": float(a["mechanism"]),
        "indication": float(a["indication"]),
        "phase": float(a["phase"]),
        "submission": float(a["submission"]),
    }


def _assign_col_by_x0(x0: float, starts: Dict[str, float], tolerance: float = 4.0) -> str:
    if x0 < starts["mechanism"] - tolerance:
        return "compound"
    if x0 < starts["indication"] - tolerance:
        return "mechanism"
    if x0 < starts["phase"] - tolerance:
        return "indication"
    if x0 < starts["submission"] - tolerance:
        return "phase"
    return "submission"


def _line_groups(words: List[Tuple], y_tol: float = 3.0) -> List[List[Tuple]]:
    words = sorted(words, key=lambda w: (float(w[1]), float(w[0])))
    lines: List[List[Tuple]] = []

    for w in words:
        y = (float(w[1]) + float(w[3])) / 2
        if not lines:
            lines.append([w])
            continue

        current_y = sum(
            (float(x[1]) + float(x[3])) / 2 for x in lines[-1]
        ) / len(lines[-1])

        if abs(y - current_y) <= y_tol:
            lines[-1].append(w)
        else:
            lines.append([w])

    for line in lines:
        line.sort(key=lambda w: float(w[0]))
    return lines


def _join_words_in_band(words: List[Tuple]) -> str:
    if not words:
        return ""
    lines = _line_groups(words, y_tol=3.2)
    parts = []
    for line in lines:
        s = _clean(" ".join(_clean(w[4]) for w in line if _clean(w[4])))
        if s:
            parts.append(s)
    return _clean(" ".join(parts))


def _phase_row_anchors(
    table_words: List[Tuple],
    starts: Dict[str, float],
) -> List[Dict[str, Any]]:
    """
    Every live Pfizer programme row has exactly one phase cell.
    Use the vertical center of that cell as the row anchor, then construct row
    bands halfway between adjacent phase cells. This is much safer than waiting
    for phase/submission text while accumulating lines across the whole page.
    """
    phase_words = [
        w for w in table_words
        if starts["phase"] - 8 <= float(w[0]) < starts["submission"] - 4
    ]

    anchors = []
    for line in _line_groups(phase_words, y_tol=3.2):
        line_text = _clean(" ".join(_clean(w[4]) for w in line))
        m = PHASE_RE.search(line_text)
        if not m:
            continue

        y0 = min(float(w[1]) for w in line)
        y1 = max(float(w[3]) for w in line)
        anchors.append({
            "y": (y0 + y1) / 2,
            "phaseRaw": m.group(1),
            "lineText": line_text,
        })

    # Remove accidental duplicate phase detections at essentially the same y.
    anchors = sorted(anchors, key=lambda a: a["y"])
    deduped = []
    for a in anchors:
        if deduped and abs(a["y"] - deduped[-1]["y"]) < 2.5:
            continue
        deduped.append(a)
    return deduped


def _row_from_band(
    row_words: List[Tuple],
    starts: Dict[str, float],
    ta: str,
    page_number: int,
    source_url: str,
    row_ordinal: int,
) -> Optional[Dict[str, Any]]:
    cols: Dict[str, List[Tuple]] = {
        "compound": [],
        "mechanism": [],
        "indication": [],
        "phase": [],
        "submission": [],
    }

    for w in row_words:
        t = _clean(w[4])
        if not t:
            continue
        col = _assign_col_by_x0(float(w[0]), starts)
        cols[col].append(w)

    compound = _join_words_in_band(cols["compound"])
    mechanism = _join_words_in_band(cols["mechanism"])
    indication = _join_words_in_band(cols["indication"])
    phase_raw = _join_words_in_band(cols["phase"])
    submission_raw = _join_words_in_band(cols["submission"])

    joined = " | ".join([compound, mechanism, indication, phase_raw, submission_raw])
    phase_match = PHASE_RE.search(phase_raw) or PHASE_RE.search(joined)
    submission_match = SUBMISSION_RE.search(submission_raw) or SUBMISSION_RE.search(joined)

    if not phase_match or not submission_match:
        return None

    phase_label = phase_match.group(1)
    phase = (
        "Filed / Registration"
        if _norm(phase_label) == "registration"
        else f"Phase {re.search(r'[123]', phase_label).group(0)}"
    )

    # Clean project-progress glyphs and footnote-only superscripts from the beginning/end.
    compound = re.sub(r"^[►▶]+\s*", "", compound).strip()
    compound = re.sub(r"\s+[0-9]{1,2}$", "", compound).strip()

    # Remove phase/submission tokens if a PDF word crossed the visible column edge.
    for field_name, value in [
        ("compound", compound),
        ("mechanism", mechanism),
        ("indication", indication),
    ]:
        value = PHASE_RE.sub("", value)
        value = SUBMISSION_RE.sub("", value)
        value = _clean(value)
        if field_name == "compound":
            compound = value
        elif field_name == "mechanism":
            mechanism = value
        else:
            indication = value

    if not compound or not indication:
        return None

    code_match = PF_CODE_RE.search(compound)
    development_code = _clean(code_match.group(0)).upper() if code_match else ""

    return {
        "company": "Pfizer",
        "asset": compound,
        "developmentCode": development_code,
        "mechanismOfAction": mechanism,
        "indication": indication,
        "phase": phase,
        "therapeuticArea": ta,
        "submissionType": submission_match.group(1),
        "sourceUrl": source_url,
        "sourcePage": page_number,
        "sourceRow": row_ordinal,
        "sourceConfidence": "High",
        "sourceAdapter": "PFIZER_OFFICIAL_PDF_ROW_BAND",
    }


def _parse_pfizer_pdf(pdf_bytes: bytes, source_url: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    rows: List[Dict[str, Any]] = []
    page_diags: List[Dict[str, Any]] = []
    source_date = None

    for page_idx in range(doc.page_count):
        page = doc.load_page(page_idx)
        page_text_raw = page.get_text("text", sort=True)
        page_text = _clean(page_text_raw)

        if not source_date:
            m = re.search(
                r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+20\d{2}\b",
                page_text,
            )
            if m:
                source_date = m.group(0)

        # Exclude Pfizer's discontinued-program table. It deliberately uses the
        # same five-column grammar but must never enter live Portfolio.
        if re.search(r"Programs Discontinued Since Last Update", page_text, re.I):
            page_diags.append({
                "page": page_idx + 1,
                "status": "SKIPPED_DISCONTINUED_PAGE",
                "rows": 0,
            })
            continue

        if "Compound Name" not in page_text or "Submission Type" not in page_text:
            continue

        ta = _page_ta(page_text)
        if not ta:
            page_diags.append({
                "page": page_idx + 1,
                "status": "SKIPPED_NON_LIVE_PIPELINE_TABLE",
                "rows": 0,
            })
            continue

        words = page.get_text("words", sort=True)
        anchors = _find_header_anchors(words)
        if not anchors:
            page_diags.append({
                "page": page_idx + 1,
                "status": "HEADER_ANCHORS_NOT_FOUND",
                "therapeuticArea": ta,
                "rows": 0,
            })
            continue

        starts = _column_starts(anchors)

        # Body starts immediately below the two-line header.
        body_top = anchors["header_bottom"] + 2

        # Stop before the notes/footer. The first "Indicates" / "Regulatory"
        # line below the table is the safest delimiter on Pfizer's slides.
        stop_y = float(page.rect.height) - 30
        body_candidate_words = [w for w in words if float(w[1]) > body_top]

        footer_candidates = []
        for w in body_candidate_words:
            n = _norm(w[4])
            if n in {"indicates", "regulatory"} and float(w[1]) > page.rect.height * 0.55:
                footer_candidates.append(float(w[1]))
        if footer_candidates:
            stop_y = min(stop_y, min(footer_candidates) - 3)

        table_words = [
            w for w in words
            if body_top < ((float(w[1]) + float(w[3])) / 2) < stop_y
        ]

        phase_anchors = _phase_row_anchors(table_words, starts)
        page_rows: List[Dict[str, Any]] = []
        row_failures = []

        if not phase_anchors:
            page_diags.append({
                "page": page_idx + 1,
                "status": "NO_PHASE_ROW_ANCHORS",
                "therapeuticArea": ta,
                "rows": 0,
                "headerStarts": {k: round(v, 1) for k, v in starts.items()},
            })
            continue

        # Construct a vertical band around each phase cell.
        for i, phase_anchor in enumerate(phase_anchors):
            if i == 0:
                top = body_top
            else:
                top = (phase_anchors[i - 1]["y"] + phase_anchor["y"]) / 2

            if i == len(phase_anchors) - 1:
                bottom = stop_y
            else:
                bottom = (phase_anchor["y"] + phase_anchors[i + 1]["y"]) / 2

            row_words = [
                w for w in table_words
                if top <= ((float(w[1]) + float(w[3])) / 2) < bottom
            ]

            row = _row_from_band(
                row_words=row_words,
                starts=starts,
                ta=ta,
                page_number=page_idx + 1,
                source_url=source_url,
                row_ordinal=i + 1,
            )

            if row:
                page_rows.append(row)
            else:
                row_failures.append({
                    "row": i + 1,
                    "phaseAnchor": phase_anchor,
                    "top": round(top, 1),
                    "bottom": round(bottom, 1),
                    "rawText": _clean(" ".join(_clean(w[4]) for w in row_words))[:1200],
                })

        rows.extend(page_rows)

        page_diags.append({
            "page": page_idx + 1,
            "status": "PARSED_ROW_BANDS",
            "therapeuticArea": ta,
            "phaseAnchors": len(phase_anchors),
            "rows": len(page_rows),
            "rowFailures": row_failures,
            "headerStarts": {k: round(v, 1) for k, v in starts.items()},
            "bodyTop": round(body_top, 1),
            "stopY": round(stop_y, 1),
        })

    # De-duplicate exact source rows only.
    deduped: List[Dict[str, Any]] = []
    seen = set()
    duplicate_count = 0

    for row in rows:
        key = (
            _norm(row["asset"]),
            _norm(row["mechanismOfAction"]),
            _norm(row["indication"]),
            row["phase"],
            _norm(row["submissionType"]),
        )
        if key in seen:
            duplicate_count += 1
            continue
        seen.add(key)
        deduped.append(row)

    diagnostics = {
        "parser": "PFIZER_ROW_BAND_V2",
        "sourceDate": source_date,
        "pages": page_diags,
        "rawRows": len(rows),
        "dedupedRows": len(deduped),
        "exactDuplicatesRemoved": duplicate_count,
    }
    return deduped, diagnostics

def _validate_pfizer(rows: List[Dict[str, Any]]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    counts = Counter(r.get("phase", "") for r in rows)
    actual = {
        "Phase 1": counts.get("Phase 1", 0),
        "Phase 2": counts.get("Phase 2", 0),
        "Phase 3": counts.get("Phase 3", 0),
        "Filed / Registration": counts.get("Filed / Registration", 0),
        "Total": len(rows),
    }

    issues: List[Dict[str, Any]] = []

    coverage_matches = actual == EXPECTED_PFIZER
    if not coverage_matches:
        issues.append({
            "issue": "Official Pfizer coverage reconciliation failed",
            "expected": EXPECTED_PFIZER,
            "actual": actual,
        })

    missing_core = [
        {
            "asset": r.get("asset", ""),
            "page": r.get("sourcePage"),
            "missing": [
                k for k in ["asset", "indication", "phase", "submissionType"]
                if not _clean(r.get(k, ""))
            ],
        }
        for r in rows
        if any(not _clean(r.get(k, "")) for k in ["asset", "indication", "phase", "submissionType"])
    ]
    if missing_core:
        issues.append({
            "issue": "Rows missing core fields",
            "count": len(missing_core),
            "sample": missing_core[:20],
        })

    summary = {
        "expected": EXPECTED_PFIZER,
        "actual": actual,
        "coverageMatches": coverage_matches,
        "productionStatus": (
            "READY FOR AIRTABLE MERGE VALIDATION"
            if coverage_matches and not missing_core
            else "FAIL CLOSED - DO NOT MERGE"
        ),
    }
    return summary, issues


@app.get("/health")
async def health() -> Dict[str, Any]:
    return {
        "ok": True,
        "version": APP_VERSION,
        "service": "pharma-pipeline-pdf-adapter",
    }


@app.get("/extract/pfizer", response_model=ExtractionResponse)
async def extract_pfizer(
    source_url: str = Query(default=PFIZER_PDF_URL),
    x_adapter_key: Optional[str] = Header(default=None),
) -> ExtractionResponse:
    _auth(x_adapter_key)

    pdf_bytes = await _download_pdf(source_url)
    rows, diagnostics = _parse_pfizer_pdf(pdf_bytes, source_url)
    summary, issues = _validate_pfizer(rows)

    return ExtractionResponse(
        version=APP_VERSION,
        company="Pfizer",
        sourceUrl=source_url,
        sourceDate=diagnostics.get("sourceDate"),
        rows=rows,
        summary=summary,
        issues=issues,
        diagnostics=diagnostics,
    )


@app.get("/debug/pfizer")
async def debug_pfizer(
    source_url: str = Query(default=PFIZER_PDF_URL),
    x_adapter_key: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    _auth(x_adapter_key)

    pdf_bytes = await _download_pdf(source_url)
    rows, diagnostics = _parse_pfizer_pdf(pdf_bytes, source_url)
    summary, issues = _validate_pfizer(rows)

    return {
        "version": APP_VERSION,
        "summary": summary,
        "issues": issues,
        "diagnostics": diagnostics,
        "sampleRows": rows[:20],
    }
