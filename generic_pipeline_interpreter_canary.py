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


VERSION = "GENERIC_PIPELINE_INTERPRETER_CANARY_V1.1_CONTEXT_AWARE_TRIPLETS_READ_ONLY"

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

    if n in {"in market", "marketed", "approved"}:
        return "Approved"

    if "registration" in n or "regulatory" in n or "filed" in n:
        return "Filed / Registration"

    if "pre clinical" in n or "preclinical" in n or n in {"phase 0", "0"}:
        return "Preclinical"

    # Prefer the highest explicit clinical phase when the source publishes a
    # range such as Phase 1/2 or Phase 2/3.
    phase_hits: List[int] = []
    roman = {"i": 1, "ii": 2, "iii": 3, "iv": 4}
    for match in re.finditer(
        r"\bphase\s*(i{1,3}|iv|[1-4])(?:\s*/\s*(i{1,3}|iv|[1-4]))?",
        text,
        flags=re.I,
    ):
        for token in match.groups():
            if not token:
                continue
            t = token.lower()
            phase_hits.append(int(t) if t.isdigit() else roman[t])
    if phase_hits:
        return f"Phase {max(phase_hits)}"

    # Some tables expose only numeric phase columns/cells.
    if re.fullmatch(r"[1-4]", n):
        return f"Phase {n}"

    return ""


def exact_phase_label(value: Any) -> str:
    """Return a phase only when the complete visible line is a stage label."""
    text = clean(value)
    n = norm(text)
    if not n:
        return ""
    if n in {"in market", "marketed", "approved"}:
        return "Approved"
    if n in {"registration", "registrational", "filed", "regulatory review"}:
        return "Filed / Registration"
    if n in {"preclinical", "pre clinical"}:
        return "Preclinical"
    if re.fullmatch(
        r"phase\s*(?:i{1,3}|iv|[1-4])(?:\s*/\s*(?:i{1,3}|iv|[1-4]))?",
        text,
        flags=re.I,
    ):
        return phase_canonical(text)
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


FLOW_STOP_TERMS = {
    "candidate", "about", "rights", "target", "indication", "indications",
    "clinical phase", "study", "share", "clinical trial information",
    "load more", "filter", "search", "program", "programme", "phase",
    "development pipeline", "pipeline",
}


def compact_flow_value(value: Any, *, max_words: int = 18, max_chars: int = 180) -> bool:
    s = clean(value)
    n = norm(s)
    if not s or not n or n in FLOW_STOP_TERMS:
        return False
    if exact_phase_label(s):
        return False
    if len(s) > max_chars or len(s.split()) > max_words:
        return False
    if re.fullmatch(r"[+\-–—]+", s):
        return False
    return True


PHASE_TRIPLET_CONTEXT_TERMS = {
    "liver",
    "muscle",
    "lung",
    "cns",
    "adipose",
    "brain",
    "kidney",
    "heart",
    "skin",
    "blood",
    "bone",
    "bone marrow",
    "retina",
    "eye",
    "skeletal muscle",
    "central nervous system",
}

PHASE_TRIPLET_STATUS_TERMS = {
    "in market",
    "marketed",
    "approved",
    "filed",
    "registration",
    "registrational",
    "preclinical",
    "pre clinical",
}


def normalize_phase_triplet_identity(value: Any) -> Tuple[str, str]:
    """Normalize a compact programme heading without using company-specific rules."""
    text = clean(value)
    if not text:
        return "", ""

    # Partnership/licensing text is commercial context, not part of the
    # asset identity.
    text = re.sub(
        r"\s+(?:partnered\s+with|licensed\s+to|licensed\s+from|in\s+collaboration\s+with)\b.*$",
        "",
        text,
        flags=re.I,
    ).strip()

    # Generic source headings often publish a canonical asset followed by a
    # development code in parentheses, e.g. Name (ABC-123). Preserve both.
    match = re.fullmatch(
        r"(.+?)\s*\(([^()]{2,60})\)\s*",
        text,
    )
    if match:
        asset = clean(match.group(1))
        code = clean(match.group(2))
        if asset and code and (re.search(r"\d", code) or "-" in code):
            return asset, code

    return text, ""


NON_ASSET_IDENTITY_RE = re.compile(
    r"\b(?:years?\s+old|all\s+sexes|healthy\s+volunteers?|eligibility\s+criteria|"
    r"participants?|locations?|start\s+date|end\s+date|study\s+first\s+posted|"
    r"estimated\s+completion|actual\s+completion|clinical\s+trials?)\b",
    flags=re.I,
)


def phase_triplet_identity_score(value: Any) -> int:
    """Score a compact source line as a plausible programme identity."""
    asset, development_code = normalize_phase_triplet_identity(value)
    n = norm(asset)

    if not asset or not n:
        return -100
    if n in PHASE_TRIPLET_CONTEXT_TERMS:
        return -100
    if n in PHASE_TRIPLET_STATUS_TERMS:
        return -100
    if exact_phase_label(asset):
        return -100
    if NON_ASSET_IDENTITY_RE.search(asset):
        return -100
    if not compact_flow_value(asset, max_words=14, max_chars=150):
        return -100

    words = asset.split()
    score = 0

    if development_code:
        score += 8

    if re.search(r"\b[A-Z0-9]{2,}-[A-Z0-9-]{2,}\b", asset):
        score += 7
    elif re.search(r"\b[A-Z]{2,}\d{2,}[A-Z0-9-]*\b", asset):
        score += 7
    elif len(words) <= 2:
        score += 5
    elif len(words) <= 4:
        score += 3
    else:
        score += 1

    if "," in asset:
        score -= 2

    return score


def recover_phase_triplet_identity(
    lines: Sequence[str],
    context_index: int,
) -> Tuple[str, str]:
    """Recover the nearest preceding programme heading when a row uses a
    tissue/compartment label immediately before indication and phase.

    This remains company-agnostic: the fallback is triggered only by a small
    semantic set of anatomical/compartment labels, never by company name.
    """
    lower_bound = max(0, context_index - 12)
    ranked: List[Tuple[int, int, str, str]] = []

    for j in range(context_index - 1, lower_bound - 1, -1):
        candidate = clean(lines[j])
        n = norm(candidate)

        if not candidate or not n:
            continue
        if n in PHASE_TRIPLET_CONTEXT_TERMS:
            continue
        if n in PHASE_TRIPLET_STATUS_TERMS:
            continue
        if exact_phase_label(candidate):
            continue

        # A compact line immediately following a tissue/compartment label is
        # much more likely to be an indication than a programme identity.
        if j > 0 and norm(lines[j - 1]) in PHASE_TRIPLET_CONTEXT_TERMS:
            continue

        score = phase_triplet_identity_score(candidate)
        if score <= 0:
            continue

        asset, development_code = normalize_phase_triplet_identity(candidate)
        if asset:
            distance = context_index - j
            ranked.append((score, -distance, asset, development_code))

    if not ranked:
        return "", ""

    ranked.sort(reverse=True)
    _, _, asset, development_code = ranked[0]
    return asset, development_code


def extract_rows_from_phase_triplets(
    company: str,
    source_url: str,
    lines: Sequence[str],
) -> List[DiscoveryRow]:
    """Parse repeated visible asset / indication / phase triples.

    This is useful for accessible/rendered pipeline grids where browser text
    already exposes each row sequentially. The parser does not rely on company
    names, CSS selectors, Portfolio identities, or disease dictionaries.
    """
    clean_lines = [clean(x) for x in lines if clean(x)]
    out: List[DiscoveryRow] = []

    for i, phase_line in enumerate(clean_lines):
        phase = exact_phase_label(phase_line)
        if not phase or i < 2:
            continue

        indication = clean_lines[i - 1]
        raw_asset = clean_lines[i - 2]
        development_code = ""

        if norm(raw_asset) in PHASE_TRIPLET_CONTEXT_TERMS:
            asset, development_code = recover_phase_triplet_identity(
                clean_lines,
                i - 2,
            )
        else:
            asset, development_code = normalize_phase_triplet_identity(
                raw_asset
            )

        if phase_triplet_identity_score(asset) <= 0:
            continue
        if not compact_flow_value(indication, max_words=24, max_chars=220):
            continue

        # Avoid treating neighbouring labels/navigation as programme rows.
        if norm(asset) in FLOW_STOP_TERMS or norm(indication) in FLOW_STOP_TERMS:
            continue

        out.append(
            DiscoveryRow(
                company=company,
                sourceFamily="Company Pipeline",
                sourceRecordId=f"triplet:{len(out)+1}",
                sourceUrl=source_url,
                asset=asset,
                molecule="",
                developmentCode=development_code,
                indication=indication,
                phase=phase,
                phaseEvidence="SOURCE_RENDERED_TEXT",
                sponsorOwner=company,
                partners=[],
                study="",
                trialIds=[],
                sourceOrdinal=len(out) + 1,
                parserMethod="PHASE_TRIPLET_FLOW",
            )
        )

    return out


def extract_rows_from_candidate_cards(
    company: str,
    source_url: str,
    lines: Sequence[str],
) -> List[DiscoveryRow]:
    """Parse labelled candidate cards from browser-visible text.

    A card starts with the literal semantic label Candidate. Within that card,
    each exact phase label is paired only with the compact visible line
    immediately above it as the indication. This supports multiple indications
    per candidate while failing closed on prose or unlabeled structures.
    """
    clean_lines = [clean(x) for x in lines if clean(x)]
    candidate_positions = [
        i for i, value in enumerate(clean_lines)
        if norm(value) == "candidate"
    ]
    if not candidate_positions:
        return []

    out: List[DiscoveryRow] = []
    for pos_index, pos in enumerate(candidate_positions):
        if pos + 1 >= len(clean_lines):
            continue
        asset = clean_lines[pos + 1]
        if not compact_flow_value(asset, max_words=14, max_chars=150):
            continue

        end = (
            candidate_positions[pos_index + 1]
            if pos_index + 1 < len(candidate_positions)
            else min(len(clean_lines), pos + 80)
        )
        block = clean_lines[pos + 2 : end]

        # Require the source's own Indications label before accepting phase
        # rows from this card.
        indication_label_positions = [
            j for j, value in enumerate(block)
            if norm(value) in {"indication", "indications"}
        ]
        if not indication_label_positions:
            continue
        first_indication_label = indication_label_positions[0]

        for j in range(first_indication_label + 1, len(block)):
            phase = exact_phase_label(block[j])
            if not phase or j < 1:
                continue
            indication = block[j - 1]
            if not compact_flow_value(indication, max_words=24, max_chars=220):
                continue

            out.append(
                DiscoveryRow(
                    company=company,
                    sourceFamily="Company Pipeline",
                    sourceRecordId=f"candidate:{len(out)+1}",
                    sourceUrl=source_url,
                    asset=asset,
                    molecule="",
                    indication=indication,
                    phase=phase,
                    phaseEvidence="SOURCE_RENDERED_TEXT",
                    sponsorOwner=company,
                    partners=[],
                    study="",
                    trialIds=[],
                    sourceOrdinal=len(out) + 1,
                    parserMethod="CANDIDATE_CARD_FLOW",
                )
            )

    return out


def source_declared_total_rows(lines: Sequence[str]) -> Optional[int]:
    joined = clean(" ".join(clean(x) for x in lines if clean(x)))
    patterns = [
        r"\b\d+\s+of\s+(\d+)\s+total\s+indications\b",
        r"\bof\s+(\d+)\s+total\s+indications\b",
        r"\b(\d+)\s+total\s+indications\b",
    ]
    for pattern in patterns:
        m = re.search(pattern, joined, flags=re.I)
        if m:
            value = int(m.group(1))
            if 1 <= value <= 2000:
                return value
    return None


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

    triplet_rows = extract_rows_from_phase_triplets(
        company,
        source_url,
        clean_lines,
    )

    candidate_card_rows = extract_rows_from_candidate_cards(
        company,
        source_url,
        clean_lines,
    )

    # Reusable strategy selection: choose the structurally stronger extraction.
    # No company name or Portfolio state is used to choose a parser.
    candidates = [
        ("SEMANTIC_TABLE", table_rows),
        ("LABELLED_FLOW", labelled_rows),
        ("PHASE_TRIPLET_FLOW", triplet_rows),
        ("CANDIDATE_CARD_FLOW", candidate_card_rows),
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
        "phaseTripletRows": len(triplet_rows),
        "candidateCardRows": len(candidate_card_rows),
        "declaredRowCount": source_declared_total_rows(clean_lines),
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

    declared_count = diagnostics.get("declaredRowCount")
    if isinstance(declared_count, int) and declared_count > 0 and len(rows) != declared_count:
        issues.append(
            f"source declares {declared_count} rows but parser recovered {len(rows)}"
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
            "Approved",
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
