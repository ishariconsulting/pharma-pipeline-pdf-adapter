"""Read-only Lilly parser canary using browser-rendered HTML.

Purpose:
- retrieve Lilly's official clinical development pipeline with Chromium
- run the same structural parsing rules used by PIPELINE_LILLY_HTML_V1_READ_ONLY
- validate programme grain before any Airtable binding or master-data write

This script performs NO Airtable writes and NO source mutations.
"""

from __future__ import annotations

import asyncio
import html as html_lib
import json
import re
import unicodedata
from collections import Counter
from typing import Dict, List, Optional

from playwright.async_api import async_playwright


VERSION = "LILLY_RENDERED_PARSER_CANARY_V1.0_READ_ONLY"
SOURCE_URL = "https://www.lilly.com/science/research-development/pipeline"
MIN_VALID_SOURCE_PROJECTS = 20

TA_VALUES = {
    "Cardiometabolic Health",
    "Immunology",
    "Neuroscience",
    "Cancer",
}

BOILERPLATE = {
    "one", "left", "right", "center",
    "small", "medium", "large",
    "white", "pink", "stone", "orange", "gold",
    "16px", "20px", "24px", "28px", "32px", "48px", "60px", "100px",
    "NME", "New Indication / Other", "NILEX / Other",
    "Small Molecule", "Large Molecule",
    "milestone_achieved", "new_to_pipeline", "regulatory_approval_achieved",
    "spacer", "link", "select", "1Column", "standardTitle",
    "contentTypeDescription", "secContentTypeNone",
}


def emit(label: str, payload: dict) -> None:
    print(label, json.dumps(payload, ensure_ascii=False, sort_keys=True), flush=True)


def text(v) -> str:
    return "" if v is None else str(v).strip()


def normalize(v) -> str:
    s = text(v).lower()
    s = unicodedata.normalize("NFKD", s)
    s = s.replace("’", "'").replace("‘", "'")
    s = s.replace("–", "-").replace("—", "-").replace("−", "-")
    replacements = [
        (r"\bnon small cell lung cancer\b", "nsclc"),
        (r"\btype 2 diabetes mellitus\b", "type 2 diabetes"),
        (r"\bt2dm\b", "type 2 diabetes"),
        (r"\bt2d\b", "type 2 diabetes"),
        (r"\bobstructive sleep apnoea\b", "obstructive sleep apnea"),
        (r"\bosa\b", "obstructive sleep apnea"),
        (r"\bosteoarthritis\b", "oa"),
        (r"\bcardiovascular\b", "cv"),
        (r"\bchronic kidney disease\b", "ckd"),
        (r"\balzheimer'?s\b", "alzheimer"),
        (r"\bleukaemia\b", "leukemia"),
        (r"\btumours\b", "tumors"),
        (r"\boverweight\b", "obesity"),
    ]
    for pattern, repl in replacements:
        s = re.sub(pattern, repl, s)
    s = re.sub(r"[^a-z0-9+\-/ ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def html_to_lines(raw_html: str) -> List[str]:
    s = text(raw_html)
    s = re.sub(r"<script\b[^>]*>[\s\S]*?</script>", "\n", s, flags=re.I)
    s = re.sub(r"<style\b[^>]*>[\s\S]*?</style>", "\n", s, flags=re.I)
    s = re.sub(r"<!--[\s\S]*?-->", "\n", s)
    s = re.sub(r"<(br|hr)\b[^>]*>", "\n", s, flags=re.I)
    s = re.sub(
        r"</(p|div|section|article|li|ul|ol|h1|h2|h3|h4|h5|h6|button|a|span)>",
        "\n",
        s,
        flags=re.I,
    )
    s = re.sub(r"<[^>]+>", " ", s)
    s = html_lib.unescape(s)
    return [re.sub(r"\s+", " ", x).strip() for x in s.splitlines() if re.sub(r"\s+", " ", x).strip()]


def phase_from_heading(line: str) -> str:
    n = normalize(line)
    if n == "regulatory approval achieved":
        return "Regulatory Approval Achieved"
    if n == "regulatory review":
        return "Regulatory Review"
    if n == "phase 3":
        return "Phase 3"
    if n == "phase 2":
        return "Phase 2"
    if n == "phase 1":
        return "Phase 1"
    return ""


def is_boilerplate(line: str) -> bool:
    s = text(line)
    if not s or s in BOILERPLATE:
        return True
    if re.match(r"^\d+px$", s, flags=re.I):
        return True
    if re.match(r"^Press Release\s*\|", s, flags=re.I):
        return True
    if re.match(r"^https?://", s, flags=re.I):
        return True
    if re.match(r"^(backgroundColor|additionalPadding|additionalMargins|sameTab)$", s, flags=re.I):
        return True
    return False


def next_meaningful(lines: List[str], start: int, max_look: int = 12) -> Optional[Dict[str, object]]:
    for i in range(start, min(len(lines), start + max_look)):
        line = lines[i]
        if phase_from_heading(line):
            return None
        if line in TA_VALUES:
            return None
        if not is_boilerplate(line):
            return {"line": line, "index": i}
    return None


def extract_ly_code(window_text: str) -> str:
    m = re.search(r"\bLY[- ]?\d{6,9}\b", text(window_text), flags=re.I)
    return re.sub(r"\s+", "", m.group(0).upper()) if m else ""


def parse_lilly_html(raw_html: str) -> dict:
    lines = html_to_lines(raw_html)
    joined = "\n".join(lines)

    date_match = re.search(
        r"(?:Molecule\s*&\s*potential indication data|Data)\s+as of\s+([A-Z][a-z]+\s+\d{1,2},\s+\d{4})",
        joined,
        flags=re.I,
    )
    source_date = date_match.group(1) if date_match else ""
    phase1_suppressed = bool(re.search(r"Phase 1 projects are no longer disclosed", joined, flags=re.I))

    projects = []
    current_phase = ""
    for i, line in enumerate(lines):
        p = phase_from_heading(line)
        if p:
            current_phase = p
            continue

        if not current_phase or current_phase == "Phase 1":
            continue
        if line not in TA_VALUES:
            continue

        therapeutic_area = line
        mol = next_meaningful(lines, i + 1, 10)
        if not mol:
            continue
        ind = next_meaningful(lines, int(mol["index"]) + 1, 10)
        if not ind:
            continue

        if "pipeline disclaimer" in normalize(mol["line"]):
            continue
        if "pipeline disclaimer" in normalize(ind["line"]):
            continue

        window_end = min(len(lines), int(ind["index"]) + 12)
        detail_window = " | ".join(lines[int(ind["index"]) + 1 : window_end])
        dev_code = extract_ly_code(detail_window)

        projects.append(
            {
                "phase": current_phase,
                "therapeuticArea": therapeutic_area,
                "molecule": str(mol["line"]),
                "indication": str(ind["line"]),
                "devCode": dev_code,
            }
        )

    deduped = []
    seen = set()
    duplicate_count = 0
    for p in projects:
        key = "|".join(normalize(x) for x in (p["phase"], p["molecule"], p["indication"]))
        if not key:
            continue
        if key in seen:
            duplicate_count += 1
            continue
        seen.add(key)
        deduped.append(p)

    return {
        "sourceDate": source_date,
        "phase1Suppressed": phase1_suppressed,
        "projects": deduped,
        "lineCount": len(lines),
        "duplicateRowsRemoved": duplicate_count,
    }


async def main() -> None:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=["--no-sandbox"])
        try:
            page = await browser.new_page(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                )
            )
            response = await page.goto(SOURCE_URL, wait_until="domcontentloaded", timeout=35_000)
            if response is None:
                raise RuntimeError("No document response")
            try:
                await page.wait_for_load_state("networkidle", timeout=10_000)
            except Exception:
                pass
            await page.wait_for_timeout(1_000)
            raw_html = await page.content()
            visible_text = await page.locator("body").inner_text(timeout=5_000)
        finally:
            await browser.close()

    parsed = parse_lilly_html(raw_html)
    projects = parsed["projects"]
    phase_counts = Counter(p["phase"] for p in projects)
    ta_counts = Counter(p["therapeuticArea"] for p in projects)

    orforglipron_rows = [p for p in projects if "orforglipron" in normalize(p["molecule"])]
    malformed = [p for p in projects if not p["phase"] or not p["therapeuticArea"] or not p["molecule"] or not p["indication"]]
    allowed_phases = {"Regulatory Approval Achieved", "Regulatory Review", "Phase 3", "Phase 2"}
    invalid_phase_rows = [p for p in projects if p["phase"] not in allowed_phases]
    invalid_ta_rows = [p for p in projects if p["therapeuticArea"] not in TA_VALUES]

    checks = {
        "browserHttp200": response.status == 200,
        "renderedVisibleText": len(visible_text) >= 5_000,
        "sourceDatePresent": bool(parsed["sourceDate"]),
        "phase1SuppressionDetected": parsed["phase1Suppressed"],
        "minimumProgrammeCount": len(projects) >= MIN_VALID_SOURCE_PROJECTS,
        "orforglipronParsed": len(orforglipron_rows) >= 1,
        "allRowsStructurallyComplete": len(malformed) == 0,
        "allPhasesControlled": len(invalid_phase_rows) == 0,
        "allTherapeuticAreasControlled": len(invalid_ta_rows) == 0,
    }
    parser_binding_pass = all(checks.values())

    payload = {
        "version": VERSION,
        "readOnly": True,
        "sourceUrl": SOURCE_URL,
        "browserHttpStatus": response.status,
        "renderedVisibleTextLength": len(visible_text),
        "renderedHtmlLength": len(raw_html),
        "sourceDate": parsed["sourceDate"],
        "phase1Suppressed": parsed["phase1Suppressed"],
        "lineCount": parsed["lineCount"],
        "projectCount": len(projects),
        "phaseCounts": dict(sorted(phase_counts.items())),
        "therapeuticAreaCounts": dict(sorted(ta_counts.items())),
        "duplicateRowsRemoved": parsed["duplicateRowsRemoved"],
        "orforglipronRows": orforglipron_rows[:5],
        "sampleProjects": projects[:12],
        "malformedRowCount": len(malformed),
        "invalidPhaseRowCount": len(invalid_phase_rows),
        "invalidTherapeuticAreaRowCount": len(invalid_ta_rows),
        "checks": checks,
        "parserBindingValidated": parser_binding_pass,
        "masterWritesPerformed": 0,
        "failClosed": not parser_binding_pass,
    }
    emit("LILLY_RENDERED_PARSER_RESULT", payload)

    if not parser_binding_pass:
        raise SystemExit(2)


if __name__ == "__main__":
    asyncio.run(main())
