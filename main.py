import os
import re
import html as html_lib
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

import fitz  # PyMuPDF
import httpx
from fastapi import FastAPI, Header, HTTPException, Query
from pydantic import BaseModel


APP_VERSION = "V2.40.0 MULTI-COMPANY PIPELINE ADAPTER - PFIZER + SANOFI"

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


SANOFI_PIPELINE_URL = "https://www.sanofi.com/en/our-science/our-pipeline"

# Historical validated snapshot only. These counts are regression references,
# not permanent production invariants.
EXPECTED_SANOFI = {
    "Phase 1": 16,
    "Phase 2": 21,
    "Phase 3": 20,
    "Filed / Registration": 4,
    "Total": 61,
}

PHASE_RE = re.compile(r"\b(Phase\s*[123]|Registration)\b", re.I)
SUBMISSION_RE = re.compile(r"\b(New Molecular Entity|Product Enhancement)\b", re.I)
PF_CODE_RE = re.compile(r"\bPF[-\u2010-\u2015]?\d{5,8}\b", re.I)

# Verified text-extraction artefacts in Pfizer's Q2 2026 pipeline PDF.
# These are parser-output corrections only; they do not alter source provenance.
# Exact matching keeps this fail-safe for future pipeline revisions.
PFIZER_EXTRACTED_TEXT_CORRECTIONS = {
    "PF-086425343": "PF-08642534",
    "PF-072612711": "PF-07261271",
    "Dekavil2": "Dekavil",
    "MET-815i2": "MET-815i",
    "PF-08654696": "PF-08654698",
}

app = FastAPI(
    title="Pharma Pipeline PDF Adapter",
    version=APP_VERSION,
    description="Read-only source-adapter service for recurring pharma pipeline intelligence monitoring.",
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


def _normalize_pfizer_extracted_text(value: Any) -> Tuple[str, List[Dict[str, str]]]:
    """
    Normalize only verified PDF text-extraction artefacts.

    The official source text/provenance is still retained through sourceUrl,
    sourcePage and sourceRow. Corrections are emitted in diagnostics so a
    future source revision cannot silently change identities.
    """
    original = _clean(value)
    corrected = original
    applied: List[Dict[str, str]] = []

    for wrong, right in PFIZER_EXTRACTED_TEXT_CORRECTIONS.items():
        if wrong in corrected:
            corrected = corrected.replace(wrong, right)
            applied.append({"from": wrong, "to": right})

    return _clean(corrected), applied


def _auth(x_adapter_key: Optional[str]) -> None:
    expected = os.getenv("ADAPTER_API_KEY", "").strip()
    if expected and x_adapter_key != expected:
        raise HTTPException(status_code=401, detail="Invalid adapter key")


async def _download_pdf(url: str) -> bytes:
    headers = {
        "User-Agent": "PharmaPipelineAdapter/2.39.3 (+official-source-reader)",
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

    # IMPORTANT:
    # Pfizer's visual table places the first word of Submission Type ("New" or
    # "Product") slightly left of the header's x-start. That means it can land
    # in the phase column while "Molecular Entity" / "Enhancement" lands in the
    # submission column. V2.39.1 therefore found all 95 row bands but rejected
    # every row because the submission phrase was split by our artificial
    # column separator.
    #
    # Search the natural reading-order text for phase/submission classification,
    # while still using x-coordinate columns for asset/mechanism/indication.
    natural_words = sorted(
        row_words,
        key=lambda w: (
            round(((float(w[1]) + float(w[3])) / 2) / 2.5) * 2.5,
            float(w[0]),
        ),
    )
    natural_text = _clean(" ".join(_clean(w[4]) for w in natural_words if _clean(w[4])))

    phase_match = PHASE_RE.search(phase_raw) or PHASE_RE.search(natural_text)
    submission_match = SUBMISSION_RE.search(submission_raw) or SUBMISSION_RE.search(natural_text)

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

    # Apply only verified Pfizer PDF extraction corrections. This prevents
    # superscript/embedded-glyph artefacts from becoming false Portfolio deltas.
    compound, compound_corrections = _normalize_pfizer_extracted_text(compound)

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
        "_parserCorrections": compound_corrections,
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
                debug_cols = {
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
                    debug_cols[_assign_col_by_x0(float(w[0]), starts)].append(w)

                row_failures.append({
                    "row": i + 1,
                    "phaseAnchor": phase_anchor,
                    "top": round(top, 1),
                    "bottom": round(bottom, 1),
                    "rawText": _clean(" ".join(_clean(w[4]) for w in row_words))[:1200],
                    "classified": {
                        k: _join_words_in_band(v)[:700]
                        for k, v in debug_cols.items()
                    },
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

    anchor_phase_counts = Counter()
    total_phase_anchors = 0
    for p in page_diags:
        for failure in p.get("rowFailures", []):
            raw = _clean(failure.get("phaseAnchor", {}).get("phaseRaw", ""))
            if raw:
                mapped = (
                    "Filed / Registration"
                    if _norm(raw) == "registration"
                    else f"Phase {re.search(r'[123]', raw).group(0)}"
                )
                anchor_phase_counts[mapped] += 1
                total_phase_anchors += 1

        # Parsed rows are no longer present in rowFailures, so add them back
        # using page-level phaseAnchors only when there were no failures.
        if p.get("status") == "PARSED_ROW_BANDS" and not p.get("rowFailures"):
            # Page-level count is kept as a structural total; exact phase totals
            # come from returned rows below once parsing succeeds.
            total_phase_anchors += int(p.get("phaseAnchors", 0))

    returned_phase_counts = Counter(r.get("phase", "") for r in deduped)

    parser_corrections = []
    for row in deduped:
        for correction in row.get("_parserCorrections", []):
            parser_corrections.append({
                "asset": row.get("asset", ""),
                "page": row.get("sourcePage"),
                "row": row.get("sourceRow"),
                **correction,
            })

    # Internal parser metadata is useful in diagnostics but should not leak into
    # the source-row contract consumed by Airtable.
    for row in deduped:
        row.pop("_parserCorrections", None)

    row_failures_total = sum(
        len(p.get("rowFailures", []))
        for p in page_diags
        if p.get("status") == "PARSED_ROW_BANDS"
    )
    parsed_page_count = sum(
        1 for p in page_diags if p.get("status") == "PARSED_ROW_BANDS"
    )

    diagnostics = {
        "parser": "PFIZER_ROW_BAND_V3",
        "sourceDate": source_date,
        "pages": page_diags,
        "parsedPageCount": parsed_page_count,
        "rawRows": len(rows),
        "dedupedRows": len(deduped),
        "exactDuplicatesRemoved": duplicate_count,
        "rowFailures": row_failures_total,
        "returnedPhaseCounts": dict(returned_phase_counts),
        "textCorrectionsApplied": len(parser_corrections),
        "textCorrectionDetails": parser_corrections,
        "structuralNote": (
            "Recurring mode validates parser integrity independently of the "
            "historical 95-row Q2 2026 baseline. Baseline counts remain visible "
            "for regression monitoring but no longer block legitimate future "
            "pipeline additions, removals or phase changes."
        ),
    }
    return deduped, diagnostics

def _validate_pfizer(
    rows: List[Dict[str, Any]],
    diagnostics: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Structural validation for recurring delta monitoring.

    IMPORTANT:
    The historical 95-row / 37-25-31-2 Q2 2026 snapshot is a regression
    reference, not a production invariant. A real Pfizer pipeline change must
    be allowed through to Airtable's delta layer rather than being mistaken for
    a parser failure.
    """
    diagnostics = diagnostics or {}
    counts = Counter(r.get("phase", "") for r in rows)
    actual = {
        "Phase 1": counts.get("Phase 1", 0),
        "Phase 2": counts.get("Phase 2", 0),
        "Phase 3": counts.get("Phase 3", 0),
        "Filed / Registration": counts.get("Filed / Registration", 0),
        "Total": len(rows),
    }

    issues: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []

    allowed_phases = {
        "Phase 1",
        "Phase 2",
        "Phase 3",
        "Filed / Registration",
    }

    missing_core = [
        {
            "asset": r.get("asset", ""),
            "page": r.get("sourcePage"),
            "row": r.get("sourceRow"),
            "missing": [
                k for k in ["asset", "indication", "phase", "submissionType"]
                if not _clean(r.get(k, ""))
            ],
        }
        for r in rows
        if any(
            not _clean(r.get(k, ""))
            for k in ["asset", "indication", "phase", "submissionType"]
        )
    ]
    if missing_core:
        issues.append({
            "issue": "Rows missing core fields",
            "count": len(missing_core),
            "sample": missing_core[:20],
        })

    invalid_phase_rows = [
        {
            "asset": r.get("asset", ""),
            "phase": r.get("phase", ""),
            "page": r.get("sourcePage"),
            "row": r.get("sourceRow"),
        }
        for r in rows
        if r.get("phase") not in allowed_phases
    ]
    if invalid_phase_rows:
        issues.append({
            "issue": "Rows contain unsupported phase values",
            "count": len(invalid_phase_rows),
            "sample": invalid_phase_rows[:20],
        })

    # One official programme row should occupy one page/row coordinate.
    source_positions = [
        (r.get("sourcePage"), r.get("sourceRow"))
        for r in rows
    ]
    duplicate_positions = [
        pos for pos, n in Counter(source_positions).items()
        if n > 1
    ]
    if duplicate_positions:
        issues.append({
            "issue": "Duplicate source page/row coordinates",
            "count": len(duplicate_positions),
            "sample": duplicate_positions[:20],
        })

    row_failures = int(diagnostics.get("rowFailures", 0) or 0)
    if row_failures:
        issues.append({
            "issue": "One or more phase-row bands failed extraction",
            "count": row_failures,
        })

    exact_duplicates_removed = int(
        diagnostics.get("exactDuplicatesRemoved", 0) or 0
    )
    if exact_duplicates_removed:
        issues.append({
            "issue": "Exact source rows were unexpectedly duplicated",
            "count": exact_duplicates_removed,
        })

    parsed_page_count = int(diagnostics.get("parsedPageCount", 0) or 0)
    if parsed_page_count <= 0:
        issues.append({
            "issue": "No live Pfizer pipeline pages were parsed",
        })

    # Sanity bounds catch catastrophic parser collapse/explosion without
    # hard-coding the live programme count.
    if len(rows) < 40 or len(rows) > 200:
        issues.append({
            "issue": "Programme count outside structural sanity bounds",
            "actualTotal": len(rows),
            "allowedRange": [40, 200],
        })

    # At least one development row should remain in each major live phase.
    for phase in ["Phase 1", "Phase 2", "Phase 3"]:
        if actual[phase] <= 0:
            issues.append({
                "issue": "Major development phase unexpectedly empty",
                "phase": phase,
            })

    baseline_matches = actual == EXPECTED_PFIZER
    if not baseline_matches:
        warnings.append({
            "warning": (
                "Source no longer matches the Q2 2026 95-row baseline. "
                "This may be a legitimate pipeline delta and should be "
                "reconciled in Airtable rather than automatically rejected."
            ),
            "baseline": EXPECTED_PFIZER,
            "actual": actual,
        })

    structural_valid = len(issues) == 0

    summary = {
        "baselineExpected": EXPECTED_PFIZER,
        "actual": actual,
        "baselineCoverageMatches": baseline_matches,
        "structuralValidationPass": structural_valid,
        "productionStatus": (
            "READY FOR AIRTABLE DELTA COMPARISON"
            if structural_valid
            else "FAIL CLOSED - PARSER/STRUCTURE REVIEW REQUIRED"
        ),
        "warnings": warnings,
    }
    return summary, issues



# ---------------------------------------------------------------------------
# Sanofi official HTML pipeline adapter
# ---------------------------------------------------------------------------

def _html_decode(value: Any) -> str:
    return html_lib.unescape("" if value is None else str(value))


def _sanofi_block_text_lines(raw_html: str) -> List[str]:
    value = _html_decode(raw_html)
    value = re.sub(r"<script\b[\s\S]*?</script>", "\n", value, flags=re.I)
    value = re.sub(r"<style\b[\s\S]*?</style>", "\n", value, flags=re.I)
    value = re.sub(r"<(?:br|hr)\b[^>]*>", "\n", value, flags=re.I)
    value = re.sub(
        r"<(?:div|p|li|section|article|tr|td|th|h1|h2|h3|h4|h5|h6|span|a|strong|em|button)\b[^>]*>",
        "\n",
        value,
        flags=re.I,
    )
    value = re.sub(
        r"</(?:div|p|li|section|article|tr|td|th|h1|h2|h3|h4|h5|h6|span|a|strong|em|button)>",
        "\n",
        value,
        flags=re.I,
    )
    value = re.sub(r"<[^>]+>", " ", value)
    value = value.replace("\r", "\n")
    return [
        re.sub(r"\s+", " ", x).strip()
        for x in re.split(r"\n+", value)
        if re.sub(r"\s+", " ", x).strip()
    ]


def _sanofi_normalized_label(value: Any) -> str:
    return _norm(_clean(value).rstrip(":："))


def _sanofi_value_after_label(lines: List[str], label: str) -> str:
    wanted = _norm(label)
    stop_labels = {
        "name",
        "phase",
        "description",
        "indication",
        "therapeutic area",
        "downloads available",
    }

    for i in range(0, max(0, len(lines) - 1)):
        if _sanofi_normalized_label(lines[i]) != wanted:
            continue

        for j in range(i + 1, len(lines)):
            candidate = _clean(lines[j]).replace("®", "").replace("™", "")
            if not candidate:
                continue

            n = _norm(candidate)
            if n in {"new", "new phase"}:
                continue
            if _sanofi_normalized_label(candidate) in stop_labels:
                break
            return candidate

    return ""


def _sanofi_phase_map(label: str) -> str:
    return {
        "1": "Phase 1",
        "2": "Phase 2",
        "3": "Phase 3",
        "R": "Filed / Registration",
    }.get(label, "")


def _parse_sanofi_html(
    raw_html: str,
    source_url: str,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    starts = [
        m.start()
        for m in re.finditer(
            r"<p\b[^>]*>\s*Name\s*</p>",
            raw_html,
            flags=re.I,
        )
    ][:300]

    rows: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []
    class_role_counts: Dict[str, Dict[str, Any]] = {}

    for idx, start in enumerate(starts):
        end = starts[idx + 1] if idx + 1 < len(starts) else min(
            len(raw_html),
            start + 30000,
        )
        raw = raw_html[start:end]
        lines = _sanofi_block_text_lines(raw)

        name_idx = next(
            (
                i
                for i, line in enumerate(lines)
                if _sanofi_normalized_label(line) == "name"
            ),
            -1,
        )
        asset = (
            _clean(lines[name_idx + 1]).replace("®", "").replace("™", "")
            if 0 <= name_idx < len(lines) - 1
            else ""
        )
        indication = _sanofi_value_after_label(lines, "Indication")
        description = _sanofi_value_after_label(lines, "Description")
        source_ta = _sanofi_value_after_label(lines, "Therapeutic Area")

        if not asset or not indication:
            continue

        phase_match = re.search(
            r"<p\b[^>]*>\s*Phase\s*</p>",
            raw,
            flags=re.I,
        )
        states: List[Dict[str, str]] = []

        if phase_match:
            after = raw[
                phase_match.end() : min(len(raw), phase_match.end() + 2600)
            ]
            stop_match = re.search(
                r"<p\b[^>]*>\s*Description\s*</p>",
                after,
                flags=re.I,
            )
            phase_raw = after[: stop_match.start()] if stop_match else after

            state_re = re.compile(
                r"<div\b[^>]*class\s*=\s*[\"']([^\"']+)[\"'][^>]*>\s*(1|2|3|R)\s*</div>",
                re.I,
            )
            for sm in state_re.finditer(phase_raw):
                label = sm.group(2).upper()
                if any(s["label"] == label for s in states):
                    continue
                states.append({
                    "label": label,
                    "className": _clean(sm.group(1)),
                })
                if len(states) >= 8:
                    break

        states = [s for s in states if s["label"] in {"1", "2", "3", "R"}]

        frequencies = Counter(s["className"] for s in states)
        unique_states = [
            s for s in states if frequencies[s["className"]] == 1
        ]
        common_states = [
            s for s in states if frequencies[s["className"]] >= 2
        ]

        active = (
            unique_states[0]
            if (
                len(states) == 4
                and len(unique_states) == 1
                and len(common_states) == 3
            )
            else None
        )
        phase = _sanofi_phase_map(active["label"]) if active else ""

        for state in states:
            rec = class_role_counts.setdefault(
                state["className"],
                {
                    "className": state["className"],
                    "activeUnique": 0,
                    "inactiveCommon": 0,
                    "total": 0,
                },
            )
            rec["total"] += 1
            if active and state["className"] == active["className"]:
                rec["activeUnique"] += 1
            else:
                rec["inactiveCommon"] += 1

        if len(states) != 4:
            warnings.append({
                "asset": asset,
                "indication": indication,
                "sourceCardOrdinal": idx + 1,
                "issue": f"Expected 4 phase states but found {len(states)}",
                "states": states,
            })
        elif not active:
            warnings.append({
                "asset": asset,
                "indication": indication,
                "sourceCardOrdinal": idx + 1,
                "issue": "Could not identify exactly one unique phase-state class",
                "states": states,
                "frequencies": dict(frequencies),
            })

        rows.append({
            "company": "Sanofi",
            "asset": asset,
            "developmentCode": asset if re.fullmatch(
                r"(?:SAR|SP)\d{4,9}",
                asset,
                flags=re.I,
            ) else "",
            "indication": indication,
            "phase": phase,
            "description": description,
            "mechanismOfAction": description,
            "sourceTherapeuticArea": source_ta,
            "sourceUrl": source_url,
            "sourceConfidence": "High" if phase else "Low",
            "sourceAdapter": "SANOFI_PHASE_STATE_CARD",
            "sourceCardOrdinal": idx + 1,
        })

    phase_counts = Counter(r.get("phase", "") for r in rows)

    exact_fingerprints = [
        (
            _norm(r.get("asset")),
            _norm(r.get("indication")),
            _norm(r.get("phase")),
            _norm(r.get("description")),
        )
        for r in rows
    ]
    exact_duplicate_count = sum(
        n - 1
        for n in Counter(exact_fingerprints).values()
        if n > 1
    )

    coarse_groups: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = {}
    for row in rows:
        key = (
            _norm(row.get("asset")),
            _norm(row.get("indication")),
            _norm(row.get("phase")),
        )
        coarse_groups.setdefault(key, []).append(row)

    variant_collisions = []
    for key, grouped in coarse_groups.items():
        if len(grouped) <= 1:
            continue

        descriptions = {_norm(r.get("description")) for r in grouped}
        if len(descriptions) <= 1:
            continue

        variant_collisions.append({
            "key": "|".join(key),
            "count": len(grouped),
            "interpretation": (
                "Same asset + indication + phase but different source descriptions. "
                "Preserve as separate source programmes/variants."
            ),
            "rows": [
                {
                    "sourceCardOrdinal": r.get("sourceCardOrdinal"),
                    "asset": r.get("asset"),
                    "indication": r.get("indication"),
                    "phase": r.get("phase"),
                    "description": r.get("description"),
                    "sourceTherapeuticArea": r.get("sourceTherapeuticArea"),
                }
                for r in grouped
            ],
        })

    diagnostics = {
        "parser": "SANOFI_PHASE_STATE_CARD_V1",
        "rawCardAnchors": len(starts),
        "parsedRows": len(rows),
        "phaseResolved": sum(1 for r in rows if r.get("phase")),
        "phaseUnresolved": sum(1 for r in rows if not r.get("phase")),
        "phaseCounts": dict(phase_counts),
        "boundaryWarnings": len(warnings),
        "warningDetails": warnings,
        "exactDuplicates": exact_duplicate_count,
        "variantCollisions": variant_collisions,
        "classRoles": sorted(
            class_role_counts.values(),
            key=lambda x: (-x["activeUnique"], -x["total"]),
        ),
        "structuralNote": (
            "Sanofi phase is resolved from the unique active CSS state among "
            "1/2/3/R inside each source card. Therapeutic area is diagnostic only; "
            "production TA must continue to come from the controlled indication taxonomy."
        ),
    }
    return rows, diagnostics


def _validate_sanofi(
    rows: List[Dict[str, Any]],
    diagnostics: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    diagnostics = diagnostics or {}
    counts = Counter(r.get("phase", "") for r in rows)
    actual = {
        "Phase 1": counts.get("Phase 1", 0),
        "Phase 2": counts.get("Phase 2", 0),
        "Phase 3": counts.get("Phase 3", 0),
        "Filed / Registration": counts.get("Filed / Registration", 0),
        "Total": len(rows),
    }

    issues: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []

    allowed_phases = {
        "Phase 1",
        "Phase 2",
        "Phase 3",
        "Filed / Registration",
    }

    missing_core = [
        {
            "asset": r.get("asset", ""),
            "sourceCardOrdinal": r.get("sourceCardOrdinal"),
            "missing": [
                field
                for field in ["asset", "indication", "phase"]
                if not _clean(r.get(field, ""))
            ],
        }
        for r in rows
        if any(
            not _clean(r.get(field, ""))
            for field in ["asset", "indication", "phase"]
        )
    ]
    if missing_core:
        issues.append({
            "issue": "Rows missing core fields",
            "count": len(missing_core),
            "sample": missing_core[:20],
        })

    invalid_phases = [
        {
            "asset": r.get("asset", ""),
            "phase": r.get("phase", ""),
            "sourceCardOrdinal": r.get("sourceCardOrdinal"),
        }
        for r in rows
        if r.get("phase") not in allowed_phases
    ]
    if invalid_phases:
        issues.append({
            "issue": "Rows contain unsupported phase values",
            "count": len(invalid_phases),
            "sample": invalid_phases[:20],
        })

    if int(diagnostics.get("boundaryWarnings", 0) or 0) > 0:
        issues.append({
            "issue": "One or more Sanofi cards failed the four-state phase guardrail",
            "count": int(diagnostics.get("boundaryWarnings", 0) or 0),
        })

    if int(diagnostics.get("exactDuplicates", 0) or 0) > 0:
        issues.append({
            "issue": "Exact Sanofi source cards are duplicated",
            "count": int(diagnostics.get("exactDuplicates", 0) or 0),
        })

    if len(rows) < 20 or len(rows) > 150:
        issues.append({
            "issue": "Programme count outside structural sanity bounds",
            "actualTotal": len(rows),
            "allowedRange": [20, 150],
        })

    for phase in ["Phase 1", "Phase 2", "Phase 3"]:
        if actual[phase] <= 0:
            issues.append({
                "issue": "Major development phase unexpectedly empty",
                "phase": phase,
            })

    baseline_matches = actual == EXPECTED_SANOFI
    if not baseline_matches:
        warnings.append({
            "warning": (
                "Source no longer matches the previously validated 61-row Sanofi "
                "snapshot. This may be a legitimate pipeline delta and should be "
                "reconciled in Airtable rather than automatically rejected."
            ),
            "baseline": EXPECTED_SANOFI,
            "actual": actual,
        })

    structural_valid = len(issues) == 0

    summary = {
        "baselineExpected": EXPECTED_SANOFI,
        "actual": actual,
        "baselineCoverageMatches": baseline_matches,
        "structuralValidationPass": structural_valid,
        "productionStatus": (
            "READY FOR AIRTABLE DELTA COMPARISON"
            if structural_valid
            else "FAIL CLOSED - PARSER/STRUCTURE REVIEW REQUIRED"
        ),
        "warnings": warnings,
    }
    return summary, issues


async def _download_html(url: str) -> str:
    headers = {
        "User-Agent": "PharmaPipelineAdapter/2.40.0 (+official-source-reader)",
        "Accept": "text/html,application/xhtml+xml",
    }
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(25.0, connect=10.0),
        follow_redirects=True,
        headers=headers,
    ) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.text


@app.get("/health")
async def health() -> Dict[str, Any]:
    return {
        "ok": True,
        "version": APP_VERSION,
        "service": "pharma-pipeline-adapter",
    }


@app.get("/extract/pfizer", response_model=ExtractionResponse)
async def extract_pfizer(
    source_url: str = Query(default=PFIZER_PDF_URL),
    x_adapter_key: Optional[str] = Header(default=None),
) -> ExtractionResponse:
    _auth(x_adapter_key)

    pdf_bytes = await _download_pdf(source_url)
    rows, diagnostics = _parse_pfizer_pdf(pdf_bytes, source_url)
    summary, issues = _validate_pfizer(rows, diagnostics)

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
    summary, issues = _validate_pfizer(rows, diagnostics)

    return {
        "version": APP_VERSION,
        "summary": summary,
        "issues": issues,
        "diagnostics": diagnostics,
        "sampleRows": rows[:20],
    }


@app.get("/extract/sanofi", response_model=ExtractionResponse)
async def extract_sanofi(
    source_url: str = Query(default=SANOFI_PIPELINE_URL),
    x_adapter_key: Optional[str] = Header(default=None),
) -> ExtractionResponse:
    _auth(x_adapter_key)

    raw_html = await _download_html(source_url)
    rows, diagnostics = _parse_sanofi_html(raw_html, source_url)
    summary, issues = _validate_sanofi(rows, diagnostics)

    return ExtractionResponse(
        version=APP_VERSION,
        company="Sanofi",
        sourceUrl=source_url,
        sourceDate=None,
        rows=rows,
        summary=summary,
        issues=issues,
        diagnostics=diagnostics,
    )


@app.get("/debug/sanofi")
async def debug_sanofi(
    source_url: str = Query(default=SANOFI_PIPELINE_URL),
    x_adapter_key: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    _auth(x_adapter_key)

    raw_html = await _download_html(source_url)
    rows, diagnostics = _parse_sanofi_html(raw_html, source_url)
    summary, issues = _validate_sanofi(rows, diagnostics)

    return {
        "version": APP_VERSION,
        "summary": summary,
        "issues": issues,
        "diagnostics": diagnostics,
        "sampleRows": rows[:20],
    }


@app.get("/extract/{company_slug}", response_model=ExtractionResponse)
async def extract_company(
    company_slug: str,
    x_adapter_key: Optional[str] = Header(default=None),
) -> ExtractionResponse:
    _auth(x_adapter_key)
    slug = _norm(company_slug).replace(" ", "-")

    if slug == "pfizer":
        pdf_bytes = await _download_pdf(PFIZER_PDF_URL)
        rows, diagnostics = _parse_pfizer_pdf(pdf_bytes, PFIZER_PDF_URL)
        summary, issues = _validate_pfizer(rows, diagnostics)
        return ExtractionResponse(
            version=APP_VERSION,
            company="Pfizer",
            sourceUrl=PFIZER_PDF_URL,
            sourceDate=diagnostics.get("sourceDate"),
            rows=rows,
            summary=summary,
            issues=issues,
            diagnostics=diagnostics,
        )

    if slug == "sanofi":
        raw_html = await _download_html(SANOFI_PIPELINE_URL)
        rows, diagnostics = _parse_sanofi_html(raw_html, SANOFI_PIPELINE_URL)
        summary, issues = _validate_sanofi(rows, diagnostics)
        return ExtractionResponse(
            version=APP_VERSION,
            company="Sanofi",
            sourceUrl=SANOFI_PIPELINE_URL,
            sourceDate=None,
            rows=rows,
            summary=summary,
            issues=issues,
            diagnostics=diagnostics,
        )

    raise HTTPException(
        status_code=404,
        detail=(
            f"No validated pipeline adapter profile exists for '{company_slug}'. "
            "Add and validate the official source profile before enabling recurring monitoring."
        ),
    )


