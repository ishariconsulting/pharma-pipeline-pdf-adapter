import os
import re
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

import fitz  # PyMuPDF
import httpx
from fastapi import FastAPI, Header, HTTPException, Query
from pydantic import BaseModel


APP_VERSION = "V2.39 EXTERNAL PDF ADAPTER - PFIZER FULL COVERAGE VALIDATION"

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
        "User-Agent": "PharmaPipelineAdapter/2.39 (+official-source-reader)",
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


def _column_boundaries(a: Dict[str, float]) -> Dict[str, Tuple[float, float]]:
    xs = [
        ("compound", a["compound"]),
        ("mechanism", a["mechanism"]),
        ("indication", a["indication"]),
        ("phase", a["phase"]),
        ("submission", a["submission"]),
    ]
    bounds: Dict[str, Tuple[float, float]] = {}
    for i, (name, x) in enumerate(xs):
        left = -1e9 if i == 0 else (xs[i - 1][1] + x) / 2
        right = 1e9 if i == len(xs) - 1 else (x + xs[i + 1][1]) / 2
        bounds[name] = (left, right)
    return bounds


def _assign_col(x_center: float, bounds: Dict[str, Tuple[float, float]]) -> str:
    for name, (left, right) in bounds.items():
        if left <= x_center < right:
            return name
    return "submission"


def _line_groups(words: List[Tuple], y_tol: float = 3.0) -> List[List[Tuple]]:
    words = sorted(words, key=lambda w: (float(w[1]), float(w[0])))
    lines: List[List[Tuple]] = []

    for w in words:
        y = float(w[1])
        if not lines:
            lines.append([w])
            continue

        current_y = sum(float(x[1]) for x in lines[-1]) / len(lines[-1])
        if abs(y - current_y) <= y_tol:
            lines[-1].append(w)
        else:
            lines.append([w])

    for line in lines:
        line.sort(key=lambda w: float(w[0]))
    return lines


def _row_from_buffer(
    buffer: Dict[str, List[str]],
    ta: str,
    page_number: int,
    source_url: str,
) -> Optional[Dict[str, Any]]:
    compound = _clean(" ".join(buffer["compound"]))
    mechanism = _clean(" ".join(buffer["mechanism"]))
    indication = _clean(" ".join(buffer["indication"]))
    phase_raw = _clean(" ".join(buffer["phase"]))
    submission = _clean(" ".join(buffer["submission"]))

    # Sometimes extraction nudges a phase/submission token into a neighboring column.
    joined = " | ".join([compound, mechanism, indication, phase_raw, submission])

    phase_match = PHASE_RE.search(phase_raw) or PHASE_RE.search(joined)
    submission_match = SUBMISSION_RE.search(submission) or SUBMISSION_RE.search(joined)

    if not phase_match or not submission_match:
        return None

    phase_label = phase_match.group(1)
    phase = (
        "Filed / Registration"
        if _norm(phase_label) == "registration"
        else f"Phase {re.search(r'[123]', phase_label).group(0)}"
    )

    # Remove obvious spillover from the indication if phase/submission landed there.
    indication = PHASE_RE.sub("", indication)
    indication = SUBMISSION_RE.sub("", indication)
    indication = _clean(indication)

    # Remove phase/submission from mechanism/compound if extraction overlap caused it.
    compound = PHASE_RE.sub("", compound)
    compound = SUBMISSION_RE.sub("", compound)
    mechanism = PHASE_RE.sub("", mechanism)
    mechanism = SUBMISSION_RE.sub("", mechanism)
    compound = _clean(compound)
    mechanism = _clean(mechanism)

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
        "sourceConfidence": "High",
        "sourceAdapter": "PFIZER_OFFICIAL_PDF_COORDINATE_TABLE",
    }


def _parse_pfizer_pdf(pdf_bytes: bytes, source_url: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    rows: List[Dict[str, Any]] = []
    page_diags: List[Dict[str, Any]] = []
    source_date = None

    for page_idx in range(doc.page_count):
        page = doc.load_page(page_idx)
        page_text = _clean(page.get_text("text"))

        if not source_date:
            m = re.search(r"\b(August|May|February|November)\s+\d{1,2},\s+2026\b", page_text)
            if m:
                source_date = m.group(0)

        if "Compound Name" not in page_text or "Submission Type" not in page_text:
            continue

        words = page.get_text("words")
        anchors = _find_header_anchors(words)
        if not anchors:
            page_diags.append({
                "page": page_idx + 1,
                "status": "HEADER_ANCHORS_NOT_FOUND",
                "rows": 0,
            })
            continue

        bounds = _column_boundaries(anchors)
        table_words = [
            w for w in words
            if float(w[1]) > anchors["header_bottom"] + 3
        ]

        # Stop before known footer / note zones where possible.
        stop_y = float(page.rect.height) - 35
        for w in table_words:
            n = _norm(w[4])
            if n in {"indicates", "regulatory"} and float(w[1]) > page.rect.height * 0.65:
                stop_y = min(stop_y, float(w[1]) - 4)

        table_words = [w for w in table_words if float(w[1]) < stop_y]
        lines = _line_groups(table_words)
        ta = _page_ta(page_text)

        buffer = {
            "compound": [],
            "mechanism": [],
            "indication": [],
            "phase": [],
            "submission": [],
        }
        page_rows = 0

        for line in lines:
            line_cols = {k: [] for k in buffer}
            for w in line:
                text = _clean(w[4])
                if not text:
                    continue
                x_center = (float(w[0]) + float(w[2])) / 2
                col = _assign_col(x_center, bounds)
                line_cols[col].append(text)

            line_text = _clean(" ".join(_clean(" ".join(v)) for v in line_cols.values()))

            # Ignore recurring counters/headers if they appear in table area.
            if re.search(r"\bR&D Projects\b", line_text, re.I):
                continue
            if re.fullmatch(r"(Phase\s*[123]|Registration|Total|\d+)", line_text, re.I):
                continue

            for k in buffer:
                if line_cols[k]:
                    buffer[k].append(" ".join(line_cols[k]))

            # Finalize when a phase and submission type are both present anywhere in the buffer.
            combined = " | ".join(_clean(" ".join(buffer[k])) for k in buffer)
            if PHASE_RE.search(combined) and SUBMISSION_RE.search(combined):
                row = _row_from_buffer(buffer, ta, page_idx + 1, source_url)
                if row:
                    rows.append(row)
                    page_rows += 1
                buffer = {k: [] for k in buffer}

        page_diags.append({
            "page": page_idx + 1,
            "status": "PARSED",
            "therapeuticArea": ta,
            "rows": page_rows,
            "anchors": {k: round(v, 1) for k, v in anchors.items() if k != "header_bottom"},
        })

    # De-duplicate exact source rows only.
    deduped: List[Dict[str, Any]] = []
    seen = set()
    for row in rows:
        key = (
            _norm(row["asset"]),
            _norm(row["mechanismOfAction"]),
            _norm(row["indication"]),
            row["phase"],
            _norm(row["submissionType"]),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)

    diagnostics = {
        "sourceDate": source_date,
        "pages": page_diags,
        "rawRows": len(rows),
        "dedupedRows": len(deduped),
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
