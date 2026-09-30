"""Read-only generic pipeline interpreter canary.

Purpose
-------
Prove that one company-agnostic HTML interpretation path can recover canonical
pipeline discovery rows from multiple official company pipeline pages before
anything is wired into Airtable or production monitoring.

Canary sources
--------------
- Sobi
- Ipsen
- Jazz Pharmaceuticals

Guardrails
----------
- Public GET requests only.
- No Airtable access.
- No master-data writes.
- No Render configuration changes.
- No company-specific parsing branches. Company names/URLs are data only.
- Fail closed when core fields cannot be recovered reliably.

The interpreter supports two reusable structural patterns:
1. structured HTML tables with semantic column headers;
2. labelled programme/card flows such as:
   <asset> <molecule> Indication <...> Clinical phase <...> Study <...>

The output contract is deliberately aligned to PORTFOLIO_DISCOVERY_V1.
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from dataclasses import dataclass, asdict
from functools import lru_cache
from html.parser import HTMLParser
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import httpx


VERSION = "GENERIC_PIPELINE_INTERPRETER_V1.2_SECTIONED_CARD_FALLBACK_READ_ONLY"

SOURCES = [
    {
        "company": "Sobi",
        "url": "https://www.sobi.com/en/pipeline",
    },
    {
        "company": "Ipsen",
        "url": "https://www.ipsen.com/science/pipeline/",
    },
    {
        "company": "Jazz Pharmaceuticals",
        "url": "https://www.jazzpharma.com/science/pipeline",
    },
]

MIN_ROWS_PER_SOURCE = 4
MAX_HTML_BYTES = 8_000_000

BLOCK_TAGS = {
    "address",
    "article",
    "aside",
    "blockquote",
    "br",
    "dd",
    "div",
    "dl",
    "dt",
    "figcaption",
    "figure",
    "footer",
    "form",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "header",
    "hr",
    "li",
    "main",
    "nav",
    "ol",
    "p",
    "section",
    "table",
    "tbody",
    "td",
    "tfoot",
    "th",
    "thead",
    "tr",
    "ul",
}

IDENTITY_STOP_TERMS = {
    "pipeline",
    "phase 1",
    "phase 2",
    "phase 3",
    "phase 4",
    "registration",
    "regulatory",
    "haematology",
    "hematology",
    "immunology",
    "lipids",
    "nephrology",
    "oncology",
    "rare diseases",
    "rare disease",
    "neuroscience",
    "filters",
    "reset",
    "program",
    "programme",
    "potential indications",
    "potential indication s",
}

HEADER_ALIASES = {
    "asset": (
        "program",
        "programme",
        "compound",
        "compound name",
        "asset",
        "product",
        "medicine",
        "drug",
    ),
    "molecule": (
        "molecule",
        "inn",
        "generic name",
    ),
    "developmentCode": (
        "development code",
        "code",
        "project code",
    ),
    "brand": (
        "brand",
        "brand name",
    ),
    "indication": (
        "indication",
        "potential indication",
        "potential indications",
        "disease",
    ),
    "phase": (
        "phase",
        "clinical phase",
        "stage",
    ),
    "study": (
        "trial",
        "study",
        "clinical trial",
    ),
    "therapeuticArea": (
        "therapy area",
        "therapeutic area",
        "disease area",
    ),
    "partners": (
        "partner",
        "partners",
        "collaboration",
    ),
}


def clean(value: Any) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value))
    text = (
        text.replace("\u00ad", "")
        .replace("\u2010", "-")
        .replace("\u2011", "-")
        .replace("\u2012", "-")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("\u2212", "-")
    )
    return re.sub(r"\s+", " ", text).strip()


def norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", clean(value).lower()).strip()


def uniq(values: Iterable[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for value in values:
        s = clean(value)
        n = norm(s)
        if not s or not n or n in seen:
            continue
        seen.add(n)
        out.append(s)
    return out


def phase_canonical(value: Any) -> str:
    text = clean(value)
    n = norm(text)

    if not n:
        return ""

    if "registration" in n or "regulatory" in n or "filed" in n:
        return "Filed / Registration"

    # Prefer the highest explicit clinical phase if a cell includes a range.
    phase_hits = [
        int(x)
        for x in re.findall(r"\bphase\s*([1-4])\b", n, flags=re.I)
    ]
    if phase_hits:
        return f"Phase {max(phase_hits)}"

    # Some tables expose only numeric phase columns/cells.
    if re.fullmatch(r"[1-4]", n):
        return f"Phase {n}"

    if "pre clinical" in n or "preclinical" in n or n in {"phase 0", "0"}:
        return "Preclinical"

    return ""


def trial_ids(value: Any) -> List[str]:
    # Keep trial IDs deterministic. Named studies remain in the separate
    # study field; do not reinterpret arbitrary capitalized prose as an ID.
    return uniq(
        re.findall(
            r"\bNCT\d{8}\b",
            clean(value),
            flags=re.I,
        )
    )


@lru_cache(maxsize=256)
def ctgov_phase(nct_id: str) -> str:
    """Read-only phase fallback for pipeline rows that expose an NCT ID
    but encode phase only through visual/CSS state rather than text.
    """
    nct = clean(nct_id).upper()
    if not re.fullmatch(r"NCT\d{8}", nct):
        return ""

    url = f"https://clinicaltrials.gov/api/v2/studies/{nct}"
    try:
        with httpx.Client(
            timeout=httpx.Timeout(20.0, connect=8.0),
            follow_redirects=True,
            headers={"Accept": "application/json"},
        ) as client:
            response = client.get(url)
            response.raise_for_status()
            payload = response.json()
    except Exception:
        return ""

    phases = (
        payload.get("protocolSection", {})
        .get("designModule", {})
        .get("phases", [])
    )

    ranks = {
        "EARLY_PHASE1": 1,
        "PHASE1": 1,
        "PHASE1|PHASE2": 2,
        "PHASE2": 2,
        "PHASE2|PHASE3": 3,
        "PHASE3": 3,
        "PHASE4": 4,
    }

    best = 0
    for raw in phases or []:
        value = clean(raw).upper()
        if value in ranks:
            best = max(best, ranks[value])
            continue
        if value == "NA":
            continue
        m = re.search(r"([1-4])", value)
        if m:
            best = max(best, int(m.group(1)))

    return f"Phase {best}" if best else ""


@dataclass
class DiscoveryRow:
    company: str
    sourceFamily: str
    sourceRecordId: str
    sourceUrl: str
    asset: str
    molecule: str = ""
    developmentCode: str = ""
    brand: str = ""
    indication: str = ""
    phase: str = ""
    phaseEvidence: str = ""
    programStatus: str = ""
    sponsorOwner: str = ""
    partners: List[str] = None
    study: str = ""
    trialIds: List[str] = None
    therapeuticArea: str = ""
    sourceOrdinal: int = 0
    parserMethod: str = ""

    def as_discovery_contract(self) -> Dict[str, Any]:
        row = asdict(self)
        row["partners"] = self.partners or []
        row["trialIds"] = self.trialIds or []
        return row


class PageShapeParser(HTMLParser):
    """Collect plain text lines plus semantic table cells from arbitrary HTML."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.text_parts: List[str] = []
        self.tables: List[List[List[str]]] = []

        self._current_table: Optional[List[List[str]]] = None
        self._current_row: Optional[List[str]] = None
        self._current_cell: Optional[List[str]] = None

        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: Sequence[Tuple[str, Optional[str]]]) -> None:
        tag = tag.lower()

        if tag in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1
            return

        if self._skip_depth:
            return

        if tag in BLOCK_TAGS:
            self.text_parts.append("\n")

        if tag == "table":
            self._current_table = []
        elif tag == "tr" and self._current_table is not None:
            self._current_row = []
        elif tag in {"th", "td"} and self._current_row is not None:
            self._current_cell = []

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()

        if tag in {"script", "style", "noscript", "svg"}:
            if self._skip_depth:
                self._skip_depth -= 1
            return

        if self._skip_depth:
            return

        if tag in {"th", "td"} and self._current_cell is not None:
            cell = clean(" ".join(self._current_cell))
            if self._current_row is not None:
                self._current_row.append(cell)
            self._current_cell = None

        elif tag == "tr" and self._current_row is not None:
            # Public pages can contain malformed or nested table markup where an
            # outer </table> closes before a trailing </tr>. Treat that as a
            # recoverable table-shape defect: retain visible text, discard only
            # the orphan semantic row, and continue parsing instead of crashing
            # the whole source adapter.
            if self._current_table is not None and any(clean(cell) for cell in self._current_row):
                self._current_table.append(self._current_row)
            self._current_row = None

        elif tag == "table" and self._current_table is not None:
            if self._current_table:
                self.tables.append(self._current_table)
            self._current_table = None

        if tag in BLOCK_TAGS:
            self.text_parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return

        value = clean(data)
        if not value:
            return

        self.text_parts.append(value + " ")
        if self._current_cell is not None:
            self._current_cell.append(value)

    @property
    def visible_lines(self) -> List[str]:
        text = "".join(self.text_parts)
        return [
            clean(line)
            for line in text.splitlines()
            if clean(line)
        ]


def fetch_html(url: str) -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36 "
            "GenericPipelineInterpreterCanary/1.0"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-GB,en;q=0.9,en-US;q=0.8",
        "Cache-Control": "no-cache",
    }

    timeout = httpx.Timeout(35.0, connect=12.0)
    with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
        response = client.get(url)
        response.raise_for_status()

    content = response.content
    if len(content) > MAX_HTML_BYTES:
        raise RuntimeError(
            f"source HTML too large: {len(content)} > {MAX_HTML_BYTES}"
        )

    return response.text


def header_field(value: str) -> Optional[str]:
    n = norm(value)
    if not n:
        return None

    for field, aliases in HEADER_ALIASES.items():
        for alias in aliases:
            a = norm(alias)
            if n == a or a in n:
                return field

    return None


def table_header_map(row: Sequence[str]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for idx, cell in enumerate(row):
        field = header_field(cell)
        if field and field not in out:
            out[field] = idx
    return out


def useful_table_header(mapping: Dict[str, int]) -> bool:
    return (
        "asset" in mapping
        and "indication" in mapping
        and (
            "phase" in mapping
            or len(mapping) >= 4
        )
    )


def value_at(row: Sequence[str], mapping: Dict[str, int], field: str) -> str:
    idx = mapping.get(field)
    if idx is None or idx >= len(row):
        return ""
    return clean(row[idx])


def extract_rows_from_tables(
    company: str,
    source_url: str,
    tables: Sequence[Sequence[Sequence[str]]],
) -> List[DiscoveryRow]:
    out: List[DiscoveryRow] = []
    ordinal = 0

    for table in tables:
        header_idx = None
        header_map: Dict[str, int] = {}

        for idx, row in enumerate(table[:8]):
            candidate = table_header_map(row)
            if useful_table_header(candidate):
                header_idx = idx
                header_map = candidate
                break

        if header_idx is None:
            continue

        current_ta = ""
        for raw_row in table[header_idx + 1 :]:
            if not any(clean(x) for x in raw_row):
                continue

            # Occasionally a section row carries only the TA / section label.
            nonempty = [clean(x) for x in raw_row if clean(x)]
            if len(nonempty) == 1 and len(nonempty[0]) <= 80:
                maybe_ta = clean(nonempty[0])
                if not phase_canonical(maybe_ta):
                    current_ta = maybe_ta
                continue

            asset = value_at(raw_row, header_map, "asset")
            indication = value_at(raw_row, header_map, "indication")
            phase_raw = value_at(raw_row, header_map, "phase")

            # Some matrix-style tables encode phase in one of several cells.
            if not phase_raw:
                for cell in raw_row:
                    if phase_canonical(cell):
                        phase_raw = cell
                        break

            study = value_at(raw_row, header_map, "study")
            phase = phase_canonical(phase_raw)
            phase_evidence = "SOURCE_TEXT" if phase else ""

            # Generic, source-backed fallback: some pipeline tables render the
            # active phase as CSS/graphics while exposing a trial NCT in text.
            # When that happens, resolve phase from the public CT.gov record.
            if not phase:
                ids = trial_ids(study)
                if ids:
                    phase = ctgov_phase(ids[0])
                    if phase:
                        phase_evidence = "CLINICALTRIALS_GOV_FALLBACK"

            if not asset or not indication or not phase:
                continue

            ordinal += 1

            molecule = value_at(raw_row, header_map, "molecule")
            development_code = value_at(raw_row, header_map, "developmentCode")
            brand = value_at(raw_row, header_map, "brand")
            ta = value_at(raw_row, header_map, "therapeuticArea") or current_ta
            partner_text = value_at(raw_row, header_map, "partners")

            out.append(
                DiscoveryRow(
                    company=company,
                    sourceFamily="Company Pipeline",
                    sourceRecordId=f"table:{ordinal}",
                    sourceUrl=source_url,
                    asset=asset,
                    molecule=molecule,
                    developmentCode=development_code,
                    brand=brand,
                    indication=indication,
                    phase=phase,
                    phaseEvidence=phase_evidence,
                    sponsorOwner=company,
                    partners=[partner_text] if partner_text else [],
                    study=study,
                    trialIds=trial_ids(study),
                    therapeuticArea=ta,
                    sourceOrdinal=ordinal,
                    parserMethod="SEMANTIC_TABLE",
                )
            )

    return out


LABEL_RE = re.compile(
    r"\b(Indication|Clinical\s+phase|Study)\b",
    flags=re.I,
)


def split_labels(lines: Sequence[str]) -> List[str]:
    """Split mixed label/value lines while preserving source order."""

    out: List[str] = []

    for line in lines:
        line = clean(line)
        if not line:
            continue

        cursor = 0
        matches = list(LABEL_RE.finditer(line))
        if not matches:
            out.append(line)
            continue

        for idx, match in enumerate(matches):
            prefix = clean(line[cursor : match.start()])
            if prefix:
                out.append(prefix)

            label = clean(match.group(1))
            out.append(label)

            value_start = match.end()
            value_end = matches[idx + 1].start() if idx + 1 < len(matches) else len(line)
            value = clean(line[value_start:value_end])
            if value:
                out.append(value)

            cursor = value_end

    return out


def is_identity_candidate(value: str) -> bool:
    s = clean(value)
    n = norm(s)

    if not s or not n:
        return False

    if len(s) > 120:
        return False

    if n in IDENTITY_STOP_TERMS:
        return False

    if re.fullmatch(r"\d+", n):
        return False

    if phase_canonical(s):
        return False

    if any(
        n.startswith(prefix)
        for prefix in (
            "updated ",
            "last updated ",
            "major ongoing clinical studies",
            "download",
            "overview",
            "clinical trials",
        )
    ):
        return False

    # Sentence-like prose is a poor candidate for an asset/molecule label.
    if len(s.split()) > 12:
        return False

    return True


def next_value(tokens: Sequence[str], start: int, stop_labels: Sequence[str]) -> Tuple[str, int]:
    values: List[str] = []
    i = start

    stop_norm = {norm(x) for x in stop_labels}

    while i < len(tokens):
        current = clean(tokens[i])
        if norm(current) in stop_norm:
            break

        if current:
            values.append(current)

        i += 1

        # Labels on these pages are expected to carry one compact value.
        if len(values) >= 1:
            break

    return clean(" ".join(values)), i


def prior_identity_pair(tokens: Sequence[str], index: int) -> Tuple[str, str]:
    candidates: List[str] = []

    for j in range(index - 1, max(-1, index - 9), -1):
        value = clean(tokens[j])
        if norm(value) in {
            "indication",
            "clinical phase",
            "study",
        }:
            break

        if is_identity_candidate(value):
            candidates.append(value)

        if len(candidates) >= 2:
            break

    candidates.reverse()

    if len(candidates) >= 2:
        return candidates[-2], candidates[-1]

    if len(candidates) == 1:
        return candidates[0], ""

    return "", ""


def extract_rows_from_labelled_flow(
    company: str,
    source_url: str,
    lines: Sequence[str],
) -> List[DiscoveryRow]:
    tokens = split_labels(lines)
    out: List[DiscoveryRow] = []
    ordinal = 0

    i = 0
    while i < len(tokens):
        if norm(tokens[i]) != "indication":
            i += 1
            continue

        indication, after_ind = next_value(
            tokens,
            i + 1,
            ["Clinical phase", "Study", "Indication"],
        )

        phase_label_idx = None
        for j in range(after_ind, min(len(tokens), after_ind + 6)):
            if norm(tokens[j]) == "clinical phase":
                phase_label_idx = j
                break

        if phase_label_idx is None:
            i += 1
            continue

        phase_raw, after_phase = next_value(
            tokens,
            phase_label_idx + 1,
            ["Study", "Indication", "Clinical phase"],
        )
        phase = phase_canonical(phase_raw)

        study = ""
        for j in range(after_phase, min(len(tokens), after_phase + 5)):
            if norm(tokens[j]) == "study":
                study, _ = next_value(
                    tokens,
                    j + 1,
                    ["Indication", "Clinical phase", "Study"],
                )
                # Fail closed on prose accidentally captured after an empty
                # Study label. Named studies should be compact labels.
                if len(study) > 120 or len(study.split()) > 12:
                    study = ""
                break

        asset, molecule = prior_identity_pair(tokens, i)

        if asset and indication and phase:
            ordinal += 1
            out.append(
                DiscoveryRow(
                    company=company,
                    sourceFamily="Company Pipeline",
                    sourceRecordId=f"labelled:{ordinal}",
                    sourceUrl=source_url,
                    asset=asset,
                    molecule=molecule,
                    indication=indication,
                    phase=phase,
                    phaseEvidence="SOURCE_TEXT",
                    sponsorOwner=company,
                    partners=[],
                    study=study,
                    trialIds=trial_ids(study),
                    sourceOrdinal=ordinal,
                    parserMethod="LABELLED_FLOW",
                )
            )

        i = max(i + 1, after_phase)

    return out


def dedupe_rows(rows: Sequence[DiscoveryRow]) -> List[DiscoveryRow]:
    out: List[DiscoveryRow] = []
    seen = set()

    for row in rows:
        key = (
            norm(row.asset),
            norm(row.molecule),
            norm(row.indication),
            norm(row.phase),
            norm(row.study),
        )
        if not key[0] or not key[2] or not key[3]:
            continue
        if key in seen:
            continue
        seen.add(key)
        out.append(row)

    for idx, row in enumerate(out, start=1):
        row.sourceOrdinal = idx
        row.sourceRecordId = f"{row.parserMethod.lower()}:{idx}"

    return out



LAYOUT_STOP_TERMS = {
    "pipeline",
    "clinical pipeline",
    "development pipeline",
    "research pipeline",
    "program",
    "programme",
    "programs",
    "programmes",
    "asset",
    "assets",
    "indication",
    "indications",
    "phase",
    "stage",
    "stages",
    "learn more",
    "read more",
    "reset",
    "filters",
}


def _layout_number(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def _layout_structural(node: Dict[str, Any]) -> bool:
    blob = " ".join(
        clean(node.get(key))
        for key in (
            "className",
            "parentClassName",
            "id",
            "style",
            "role",
            "ariaLabel",
        )
    )
    return bool(
        re.search(
            r"\b(pipeline|programme|program|phase|stage|progress|bar|track|clinical|row|card|grid)\b",
            blob,
            flags=re.I,
        )
    )


def _layout_text_ok(value: Any) -> bool:
    s = clean(value)
    n = norm(s)
    if not s or not n:
        return False
    if n in LAYOUT_STOP_TERMS or phase_canonical(s):
        return False
    if len(s) > 220:
        return False
    if s.count(" ") > 24:
        return False
    if re.fullmatch(r"[\W_]+", s):
        return False
    return True


def _dedupe_layout_nodes(nodes: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen = set()
    for raw in nodes:
        if not isinstance(raw, dict):
            continue
        text = clean(raw.get("text"))
        x = _layout_number(raw.get("x"))
        y = _layout_number(raw.get("y"))
        width = _layout_number(raw.get("width"))
        height = _layout_number(raw.get("height"))
        if width <= 0 or height <= 0:
            continue
        key = (norm(text), round(x / 4.0), round(y / 4.0), round(width / 6.0))
        if key in seen:
            continue
        seen.add(key)
        node = dict(raw)
        node["_text"] = text
        node["_x"] = x
        node["_y"] = y
        node["_width"] = width
        node["_height"] = height
        node["_cx"] = x + width / 2.0
        node["_cy"] = y + height / 2.0
        out.append(node)
    return out


def _layout_row_bands(nodes: Sequence[Dict[str, Any]]) -> List[Tuple[float, float]]:
    candidates: List[Tuple[float, float, float]] = []
    for node in nodes:
        width = float(node["_width"])
        height = float(node["_height"])
        if width < 240 or height < 24 or height > 320:
            continue
        blob = " ".join(
            clean(node.get(key))
            for key in ("className", "parentClassName", "id", "role")
        )
        if not (
            bool(node.get("inPipelineRow"))
            or re.search(r"\b(pipeline[-_ ]?row|programme[-_ ]?row|program[-_ ]?row|asset[-_ ]?row|pipeline[-_ ]?card|programme[-_ ]?card|program[-_ ]?card)\b", blob, re.I)
        ):
            continue
        candidates.append(
            (
                float(node["_y"]),
                float(node["_y"]) + height,
                width,
            )
        )

    # Keep the widest container for strongly overlapping vertical bands.
    bands: List[Tuple[float, float, float]] = []
    for top, bottom, width in sorted(candidates, key=lambda x: (x[0], -x[2])):
        replaced = False
        for idx, (et, eb, ew) in enumerate(bands):
            overlap = max(0.0, min(bottom, eb) - max(top, et))
            smaller = max(1.0, min(bottom - top, eb - et))
            if overlap / smaller >= 0.72:
                if width > ew:
                    bands[idx] = (top, bottom, width)
                replaced = True
                break
        if not replaced:
            bands.append((top, bottom, width))

    return [(top, bottom) for top, bottom, _ in sorted(bands)]


def _layout_fallback_bands(text_nodes: Sequence[Dict[str, Any]]) -> List[Tuple[float, float]]:
    if not text_nodes:
        return []
    ordered = sorted(text_nodes, key=lambda n: float(n["_cy"]))
    groups: List[List[Dict[str, Any]]] = []
    for node in ordered:
        cy = float(node["_cy"])
        if not groups:
            groups.append([node])
            continue
        current_y = sum(float(x["_cy"]) for x in groups[-1]) / len(groups[-1])
        if abs(cy - current_y) <= 15.0:
            groups[-1].append(node)
        else:
            groups.append([node])

    bands: List[Tuple[float, float]] = []
    for group in groups:
        if len(group) < 2:
            continue
        top = min(float(n["_y"]) for n in group) - 6.0
        bottom = max(float(n["_y"]) + float(n["_height"]) for n in group) + 6.0
        bands.append((top, bottom))
    return bands


def interpret_pipeline_layout(
    company: str,
    source_url: str,
    layout_nodes: Sequence[Dict[str, Any]],
) -> Tuple[List[DiscoveryRow], Dict[str, Any]]:
    """Conservative spatial fallback for visual/CSS pipeline grids.

    It uses only rendered DOM geometry and source text. No company names,
    Portfolio records, disease dictionaries, or hard-coded source coordinates
    are used. Rows are emitted only when asset, indication and phase can all be
    resolved from one visual row band.
    """

    nodes = _dedupe_layout_nodes(layout_nodes)
    text_nodes = [n for n in nodes if clean(n.get("_text"))]

    phase_headers: List[Dict[str, Any]] = []
    for node in text_nodes:
        phase = phase_canonical(node.get("_text"))
        if not phase or len(clean(node.get("_text"))) > 60:
            continue
        phase_headers.append({**node, "_phase": phase})

    # Collapse duplicate header labels at almost the same rendered position.
    compact_headers: List[Dict[str, Any]] = []
    for node in sorted(phase_headers, key=lambda n: (float(n["_cy"]), float(n["_cx"]))):
        duplicate = False
        for existing in compact_headers:
            if (
                existing["_phase"] == node["_phase"]
                and abs(float(existing["_cx"]) - float(node["_cx"])) <= 24.0
                and abs(float(existing["_cy"]) - float(node["_cy"])) <= 55.0
            ):
                duplicate = True
                break
        if not duplicate:
            compact_headers.append(node)
    phase_headers = compact_headers

    # Prefer a header row containing at least two distinct canonical phases.
    header_groups: List[List[Dict[str, Any]]] = []
    for node in sorted(phase_headers, key=lambda n: float(n["_cy"])):
        if not header_groups:
            header_groups.append([node])
            continue
        gy = sum(float(x["_cy"]) for x in header_groups[-1]) / len(header_groups[-1])
        if abs(float(node["_cy"]) - gy) <= 26.0:
            header_groups[-1].append(node)
        else:
            header_groups.append([node])

    global_headers: List[Dict[str, Any]] = []
    for group in header_groups:
        phases = {x["_phase"] for x in group}
        if len(phases) >= 2 and len(group) > len(global_headers):
            global_headers = sorted(group, key=lambda n: float(n["_cx"]))

    bands = _layout_row_bands(nodes)
    if not bands:
        candidate_text = [
            n for n in text_nodes
            if _layout_text_ok(n.get("_text"))
        ]
        bands = _layout_fallback_bands(candidate_text)

    rows: List[DiscoveryRow] = []
    rejected: List[Dict[str, Any]] = []

    first_phase_x = (
        min(float(h["_cx"]) for h in global_headers)
        if global_headers
        else None
    )

    for band_no, (top, bottom) in enumerate(bands, start=1):
        in_band = [
            n for n in nodes
            if top <= float(n["_cy"]) <= bottom
        ]
        band_text = [
            n for n in in_band
            if clean(n.get("_text"))
        ]
        if not band_text:
            continue

        explicit_phase_nodes = [
            n for n in band_text
            if phase_canonical(n.get("_text"))
        ]
        phase = ""
        phase_evidence = ""

        if explicit_phase_nodes:
            # Prefer the highest explicit source phase when a band contains a
            # range such as "Phase 1 / Phase 2".
            ranked = []
            for n in explicit_phase_nodes:
                p = phase_canonical(n.get("_text"))
                rank = {
                    "Preclinical": 0,
                    "Phase 1": 1,
                    "Phase 2": 2,
                    "Phase 3": 3,
                    "Phase 4": 4,
                    "Filed / Registration": 5,
                }.get(p, -1)
                ranked.append((rank, p))
            ranked.sort()
            if ranked and ranked[-1][0] >= 0:
                phase = ranked[-1][1]
                phase_evidence = "SOURCE_LAYOUT_TEXT"

        if not phase and global_headers:
            structural = [
                n for n in in_band
                if _layout_structural(n)
                and float(n["_width"]) >= 18.0
            ]
            if structural:
                right_edge = max(
                    float(n["_x"]) + float(n["_width"])
                    for n in structural
                )
                nearest = min(
                    global_headers,
                    key=lambda h: abs(float(h["_cx"]) - right_edge),
                )
                if abs(float(nearest["_cx"]) - right_edge) <= 180.0:
                    phase = str(nearest["_phase"])
                    phase_evidence = "SOURCE_LAYOUT_GEOMETRY"

        content = [
            n for n in band_text
            if _layout_text_ok(n.get("_text"))
            and (
                first_phase_x is None
                or float(n["_cx"]) < first_phase_x - 8.0
            )
        ]

        # Remove nested duplicates where the same text appears repeatedly in
        # parent and child elements.
        compact_content: List[Dict[str, Any]] = []
        seen_text = set()
        for node in sorted(content, key=lambda n: (float(n["_x"]), float(n["_y"]))):
            key = norm(node.get("_text"))
            if not key or key in seen_text:
                continue
            seen_text.add(key)
            compact_content.append(node)

        asset_node: Optional[Dict[str, Any]] = None
        for node in compact_content:
            text = clean(node.get("_text"))
            if is_identity_candidate(text) and len(text) <= 110:
                asset_node = node
                break

        indication_node: Optional[Dict[str, Any]] = None
        if asset_node is not None:
            ax = float(asset_node["_cx"])
            candidates = [
                n for n in compact_content
                if n is not asset_node
                and float(n["_cx"]) >= ax + 28.0
                and len(clean(n.get("_text"))) <= 180
            ]
            if candidates:
                # Prefer the closest distinct text column; ties prefer the more
                # descriptive disease/indication phrase.
                candidates.sort(
                    key=lambda n: (
                        float(n["_cx"]) - ax,
                        -len(clean(n.get("_text"))),
                    )
                )
                indication_node = candidates[0]

        asset = clean(asset_node.get("_text")) if asset_node else ""
        indication = clean(indication_node.get("_text")) if indication_node else ""

        if not (asset and indication and phase):
            if asset or indication or phase:
                rejected.append(
                    {
                        "band": band_no,
                        "asset": asset,
                        "indication": indication,
                        "phase": phase,
                        "text": [clean(n.get("_text")) for n in compact_content[:8]],
                    }
                )
            continue

        rows.append(
            DiscoveryRow(
                company=company,
                sourceFamily="Company Pipeline",
                sourceRecordId=f"layout:{band_no}",
                sourceUrl=source_url,
                asset=asset,
                molecule="",
                developmentCode="",
                brand="",
                indication=indication,
                phase=phase,
                phaseEvidence=phase_evidence,
                sponsorOwner=company,
                partners=[],
                study="",
                trialIds=[],
                therapeuticArea="",
                sourceOrdinal=len(rows) + 1,
                parserMethod="VISUAL_LAYOUT_GRID",
            )
        )

    selected = dedupe_rows(rows)
    diagnostics = {
        "version": VERSION,
        "company": company,
        "sourceUrl": source_url,
        "layoutNodeCount": len(nodes),
        "layoutTextNodeCount": len(text_nodes),
        "phaseHeaderCount": len(phase_headers),
        "globalPhaseHeaderCount": len(global_headers),
        "rowBandCount": len(bands),
        "visualLayoutRows": len(selected),
        "visualLayoutRejectedBands": len(rejected),
        "visualLayoutRejectedSamples": rejected[:10],
        "selectedMethod": "VISUAL_LAYOUT_GRID",
        "selectedRows": len(selected),
        "coreCompleteRows": sum(
            1 for row in selected
            if row.asset and row.indication and row.phase
        ),
        "companySpecificParserBranch": False,
        "portfolioDependentValidation": False,
        "writes": 0,
    }
    return selected, diagnostics



SECTIONED_CARD_ASSET_LABELS = {
    "molecule name",
    "compound name",
    "asset",
    "asset name",
    "program",
    "program name",
    "programme",
    "programme name",
    "candidate",
    "candidate name",
}
SECTIONED_CARD_INDICATION_LABELS = {
    "indication",
    "indications",
    "potential indication",
    "potential indications",
    "disease",
    "disease indication",
}
SECTIONED_CARD_PHASE_LABELS = {
    "clinical phase",
    "development phase",
    "phase status",
    "phase/status",
    "development stage",
}
SECTIONED_CARD_OTHER_LABELS = {
    "therapeutic area",
    "therapeutic areas",
    "therapeutic area(s)",
    "therapy area",
    "modality",
    "target",
    "targets",
    "study",
    "clinical study",
    "partner",
    "partners",
    "collaboration",
    "development details",
}


def _sectioned_label(value: Any) -> str:
    raw = clean(value).strip().rstrip(":")
    return norm(raw)


def _section_phase(value: Any) -> str:
    s = clean(value).strip()
    n = norm(s)
    if len(s) > 48:
        return ""
    if re.fullmatch(r"phase\s*[1-4]", n):
        return phase_canonical(s)
    if n in {
        "filed",
        "filing",
        "registration",
        "regulatory review",
        "filed registration",
    }:
        return "Filed / Registration"
    if n in {"preclinical", "pre clinical"}:
        return "Preclinical"
    return ""


def _known_sectioned_label(value: Any) -> bool:
    n = _sectioned_label(value)
    return (
        n in SECTIONED_CARD_ASSET_LABELS
        or n in SECTIONED_CARD_INDICATION_LABELS
        or n in SECTIONED_CARD_PHASE_LABELS
        or n in {norm(x) for x in SECTIONED_CARD_OTHER_LABELS}
    )


def _next_sectioned_value(
    lines: Sequence[str],
    start: int,
    max_lines: int = 2,
) -> Tuple[str, int]:
    values: List[str] = []
    i = start
    while i < len(lines) and len(values) < max_lines:
        value = clean(lines[i])
        if not value:
            i += 1
            continue
        if _section_phase(value) or _known_sectioned_label(value):
            break
        if len(value) > 260:
            break
        values.append(value)
        i += 1
        # Most source cards expose one value per label. A second line is only
        # retained when it is clearly a short continuation rather than prose.
        if values and (len(values) == 1 and len(value) > 120):
            break
    return clean(" ".join(values)), i


def extract_rows_from_sectioned_cards(
    company: str,
    source_url: str,
    lines: Sequence[str],
) -> List[DiscoveryRow]:
    """Parse generic pipeline cards grouped beneath source phase headings.

    Common public pipeline pages expose repeated labels such as Molecule Name,
    Therapeutic Area, Indication and Target, while phase is expressed once as a
    section heading. This parser uses only those source labels and ordering.
    """

    clean_lines = [clean(x) for x in lines if clean(x)]
    out: List[DiscoveryRow] = []
    current_phase = ""
    i = 0

    while i < len(clean_lines):
        line = clean_lines[i]
        section_phase = _section_phase(line)
        if section_phase:
            current_phase = section_phase
            i += 1
            continue

        label = _sectioned_label(line)
        if label not in SECTIONED_CARD_ASSET_LABELS:
            i += 1
            continue

        asset, after_asset = _next_sectioned_value(
            clean_lines,
            i + 1,
            max_lines=1,
        )
        if not asset or not is_identity_candidate(asset):
            i += 1
            continue

        indication = ""
        explicit_phase = ""
        study = ""
        ta = ""
        partner_values: List[str] = []

        j = after_asset
        while j < len(clean_lines):
            next_line = clean_lines[j]

            if _section_phase(next_line):
                break

            next_label = _sectioned_label(next_line)
            if next_label in SECTIONED_CARD_ASSET_LABELS:
                break

            if next_label in SECTIONED_CARD_INDICATION_LABELS:
                value, after = _next_sectioned_value(
                    clean_lines,
                    j + 1,
                    max_lines=2,
                )
                if value:
                    indication = value
                j = max(j + 1, after)
                continue

            if next_label in SECTIONED_CARD_PHASE_LABELS:
                value, after = _next_sectioned_value(
                    clean_lines,
                    j + 1,
                    max_lines=1,
                )
                phase = phase_canonical(value)
                if phase:
                    explicit_phase = phase
                j = max(j + 1, after)
                continue

            if next_label in {"therapeutic area", "therapeutic areas", "therapeutic area s", "therapy area"}:
                value, after = _next_sectioned_value(
                    clean_lines,
                    j + 1,
                    max_lines=1,
                )
                if value:
                    ta = value
                j = max(j + 1, after)
                continue

            if next_label in {"study", "clinical study"}:
                value, after = _next_sectioned_value(
                    clean_lines,
                    j + 1,
                    max_lines=1,
                )
                if value and len(value) <= 120:
                    study = value
                j = max(j + 1, after)
                continue

            if next_label in {"partner", "partners", "collaboration"}:
                value, after = _next_sectioned_value(
                    clean_lines,
                    j + 1,
                    max_lines=1,
                )
                if value:
                    partner_values.append(value)
                j = max(j + 1, after)
                continue

            j += 1

        phase = explicit_phase or current_phase
        if asset and indication and phase:
            out.append(
                DiscoveryRow(
                    company=company,
                    sourceFamily="Company Pipeline",
                    sourceRecordId=f"sectioned:{len(out)+1}",
                    sourceUrl=source_url,
                    asset=asset,
                    molecule=asset,
                    indication=indication,
                    phase=phase,
                    phaseEvidence=(
                        "SOURCE_TEXT"
                        if explicit_phase
                        else "SOURCE_SECTION_HEADING"
                    ),
                    sponsorOwner=company,
                    partners=uniq(partner_values),
                    study=study,
                    trialIds=trial_ids(study),
                    therapeuticArea=ta,
                    sourceOrdinal=len(out) + 1,
                    parserMethod="SECTIONED_LABELLED_CARD",
                )
            )

        i = max(i + 1, j)

    return dedupe_rows(out)


def interpret_pipeline_structure(
    company: str,
    source_url: str,
    visible_lines: Sequence[str],
    tables: Sequence[Sequence[Sequence[str]]],
) -> Tuple[List[DiscoveryRow], Dict[str, Any]]:
    """Interpret an already-retrieved page shape.

    This lets the same company-agnostic parser consume either server HTML or a
    browser-rendered DOM without using existing Portfolio rows as a validation
    dependency. Retrieval and interpretation stay separate.
    """

    clean_lines = [clean(line) for line in visible_lines if clean(line)]

    table_rows = extract_rows_from_tables(
        company,
        source_url,
        tables,
    )

    labelled_rows = extract_rows_from_labelled_flow(
        company,
        source_url,
        clean_lines,
    )

    sectioned_rows = extract_rows_from_sectioned_cards(
        company,
        source_url,
        clean_lines,
    )

    # Reusable strategy selection: choose the structurally stronger extraction.
    # No company name or Portfolio state is used to choose a parser.
    candidates = [
        ("SEMANTIC_TABLE", table_rows),
        ("LABELLED_FLOW", labelled_rows),
        ("SECTIONED_LABELLED_CARD", sectioned_rows),
    ]
    method, selected = max(
        candidates,
        key=lambda item: len(item[1]),
    )

    selected = dedupe_rows(selected)

    diagnostics = {
        "version": VERSION,
        "company": company,
        "sourceUrl": source_url,
        "visibleLineCount": len(clean_lines),
        "tableCount": len(tables),
        "semanticTableRows": len(table_rows),
        "labelledFlowRows": len(labelled_rows),
        "sectionedCardRows": len(sectioned_rows),
        "selectedMethod": method,
        "selectedRows": len(selected),
        "coreCompleteRows": sum(
            1
            for row in selected
            if row.asset and row.indication and row.phase
        ),
        "ctgovPhaseFallbackRows": sum(
            1
            for row in selected
            if row.phaseEvidence == "CLINICALTRIALS_GOV_FALLBACK"
        ),
        "methodsEvaluated": [name for name, _ in candidates],
        "companySpecificParserBranch": False,
        "portfolioDependentValidation": False,
        "writes": 0,
    }

    return selected, diagnostics


def interpret_pipeline_html(
    company: str,
    source_url: str,
    raw_html: str,
) -> Tuple[List[DiscoveryRow], Dict[str, Any]]:
    parser = PageShapeParser()
    parser.feed(raw_html)

    return interpret_pipeline_structure(
        company,
        source_url,
        parser.visible_lines,
        parser.tables,
    )

def validate_source(
    company: str,
    rows: Sequence[DiscoveryRow],
    diagnostics: Dict[str, Any],
) -> Dict[str, Any]:
    issues: List[str] = []

    if len(rows) < MIN_ROWS_PER_SOURCE:
        issues.append(
            f"too few structured rows: {len(rows)} < {MIN_ROWS_PER_SOURCE}"
        )

    incomplete = [
        row.sourceRecordId
        for row in rows
        if not (row.asset and row.indication and row.phase)
    ]
    if incomplete:
        issues.append(
            f"{len(incomplete)} rows missing core asset/indication/phase"
        )

    bad_phase = [
        row.sourceRecordId
        for row in rows
        if row.phase
        not in {
            "Preclinical",
            "Phase 1",
            "Phase 2",
            "Phase 3",
            "Phase 4",
            "Filed / Registration",
        }
    ]
    if bad_phase:
        issues.append(
            f"{len(bad_phase)} rows have unsupported phase values"
        )

    return {
        "company": company,
        "pass": len(issues) == 0,
        "rowCount": len(rows),
        "selectedMethod": diagnostics["selectedMethod"],
        "issues": issues,
        "sampleRows": [
            row.as_discovery_contract()
            for row in list(rows)[:5]
        ],
    }


def run() -> Dict[str, Any]:
    source_results: List[Dict[str, Any]] = []
    all_pass = True

    for source in SOURCES:
        company = source["company"]
        url = source["url"]

        try:
            raw_html = fetch_html(url)
            rows, diagnostics = interpret_pipeline_html(
                company,
                url,
                raw_html,
            )
            validation = validate_source(
                company,
                rows,
                diagnostics,
            )
        except Exception as exc:
            diagnostics = {
                "version": VERSION,
                "company": company,
                "sourceUrl": url,
                "selectedRows": 0,
                "writes": 0,
                "companySpecificParserBranch": False,
            }
            validation = {
                "company": company,
                "pass": False,
                "rowCount": 0,
                "selectedMethod": None,
                "issues": [f"{type(exc).__name__}: {exc}"],
                "sampleRows": [],
            }

        all_pass = all_pass and bool(validation["pass"])

        source_results.append(
            {
                "company": company,
                "url": url,
                "diagnostics": diagnostics,
                "validation": validation,
            }
        )

    result = {
        "version": VERSION,
        "readOnly": True,
        "sourceCount": len(SOURCES),
        "allSourcesPass": all_pass,
        "companySpecificParserBranches": 0,
        "airtableWrites": 0,
        "renderConfigWrites": 0,
        "masterDataWrites": 0,
        "sources": source_results,
    }

    return result


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(0 if result["allSourcesPass"] else 1)
