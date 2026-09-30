"""Read-only U.S. marketed-product baseline label evidence.

Purpose
-------
Resolve authoritative indication text for already-classified U.S. marketed-product
Portfolio gaps. Matching is application-number first and brand checked. The service
does not map to Airtable controlled indications and performs no master-data writes.

Sources
-------
- openFDA drug labeling API (FDA SPL harmonization)
- DailyMed label detail URL constructed from the returned SPL SET ID

Safety
------
- Exact application-number and source-brand checks.
- Conflicting indication texts are marked ambiguous.
- Results are exposed through asynchronous paged jobs for Airtable.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import os
import re
import threading
import time
import uuid
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime
from html import unescape
from urllib.parse import parse_qs, urlencode, urlparse
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional

import httpx
import fitz
from fastapi import Header, HTTPException
from pydantic import BaseModel, Field

from main import _auth, app
from routed_html_extension import _browser_payload


VERSION = "US_MARKETED_BASELINE_EVIDENCE_V1.14_NO_APPLICATION_SCOPE_BRIDGE"
OPENFDA_LABEL_URL = "https://api.fda.gov/drug/label.json"
OPENFDA_DRUGSFDA_URL = "https://api.fda.gov/drug/drugsfda.json"
DAILYMED_SPLS_URL = "https://dailymed.nlm.nih.gov/dailymed/services/v2/spls.json"
DAILYMED_APPLICATIONS_URL = "https://dailymed.nlm.nih.gov/dailymed/services/v2/applicationnumbers.json"
DAILYMED_SPL_XML_URL = "https://dailymed.nlm.nih.gov/dailymed/services/v2/spls/{setid}.xml"
PFIZER_PRODUCT_DETAIL_URL = "https://www.pfizer.com/products/product-detail/{slug}"
PFIZER_LABEL_BASE = "https://labeling.pfizer.com/ShowLabeling.aspx"
DAILYMED_SPL_ZIP_URL = "https://dailymed.nlm.nih.gov/dailymed/downloadzipfile.cfm"
FDA_APPLICATION_OVERVIEW_URL = "https://www.accessdata.fda.gov/scripts/cder/daf/index.cfm?event=overview.process&ApplNo={applno}"
MAX_PRODUCTS = 150
CACHE_TTL = 86400.0
JOB_TTL_SECONDS = 7200.0

_http_cache: Dict[str, tuple[float, Any]] = {}
_loop_semaphores: Dict[int, asyncio.Semaphore] = {}
_jobs: Dict[str, Dict[str, Any]] = {}
_job_key_index: Dict[str, str] = {}
_jobs_lock = threading.Lock()
_job_tasks: set[asyncio.Task] = set()


class BaselineProductInput(BaseModel):
    recordId: str = Field(min_length=3)
    name: str = Field(min_length=1, max_length=500)
    applicationNumbers: List[str] = Field(default_factory=list, max_length=20)
    sponsorNames: List[str] = Field(default_factory=list, max_length=30)
    activeIngredients: List[str] = Field(default_factory=list, max_length=30)
    dailyMedTitles: List[str] = Field(default_factory=list, max_length=30)
    dailyMedScopeCorroborated: bool = False


class BaselineEvidenceRequest(BaseModel):
    companyName: Optional[str] = Field(default=None, max_length=300)
    products: List[BaselineProductInput] = Field(min_length=1, max_length=MAX_PRODUCTS)


def _sem() -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    key = id(loop)
    if key not in _loop_semaphores:
        _loop_semaphores[key] = asyncio.Semaphore(8)
    return _loop_semaphores[key]


def _norm(value: Any) -> str:
    text = str(value or "")
    text = text.replace("®", "").replace("™", "").replace("©", "")
    text = text.replace("&", " and ")
    text = re.sub(r"[^A-Za-z0-9]+", " ", text).lower()
    return re.sub(r"\s+", " ", text).strip()


def _clean_brand(value: str) -> str:
    text = str(value or "").replace("®", "").replace("™", "").replace("©", "")
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s*\([^)]{1,120}\)\s*", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s*,?\s*for\s+intravenous\s+use\s*$", "", text, flags=re.I)
    text = re.sub(r"\s*,?\s*for\s+oral\s+use\s*$", "", text, flags=re.I)
    text = re.sub(r"\s*,?\s*for\s+injection\s*$", "", text, flags=re.I)
    text = re.sub(r"\s+(tablets?|capsules?|injection)\s*$", "", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip()


def _brand_candidates(raw: str) -> List[str]:
    values: List[str] = []
    cleaned = _clean_brand(raw)
    if cleaned:
        values.append(cleaned)

    cleaned_first = _norm(cleaned.split()[0]) if cleaned else ""
    cleaned_word_count = len(cleaned.split()) if cleaned else 0

    for m in re.finditer(r"([A-Za-z0-9][A-Za-z0-9-]{2,})\s*[®™]", str(raw or "")):
        token = m.group(1)
        # Prevent suffix-only candidates from multi-word brands such as
        # DAYPRO ALTA™ -> "ALTA".
        if cleaned_word_count <= 1 or _norm(token) == cleaned_first:
            values.append(token)

    if cleaned:
        first = cleaned.split()[0]
        if len(first) >= 4:
            values.append(first)

    out: List[str] = []
    seen = set()
    for value in values:
        n = _norm(value)
        if not n or n in seen:
            continue
        seen.add(n)
        out.append(value)
    return out[:5]


def _application_candidates(values: List[str]) -> List[str]:
    out: List[str] = []
    seen = set()

    for value in values:
        token = re.sub(r"\s+", "", str(value or "").upper()).strip()
        if not token:
            continue

        candidates = [token]

        if re.fullmatch(r"\d{5,6}", token):
            candidates.extend([f"BLA{token}", f"NDA{token}", f"ANDA{token}"])

        for candidate in candidates:
            if candidate not in seen:
                seen.add(candidate)
                out.append(candidate)

    return out[:30]


def _chunks(values: List[Any], size: int) -> Iterable[List[Any]]:
    for i in range(0, len(values), size):
        yield values[i:i + size]


def _brand_matches(value: Any, candidates: List[str]) -> bool:
    nv = _norm(value)
    if not nv:
        return False
    for candidate in candidates:
        nc = _norm(candidate)
        if nv == nc or nv.startswith(nc + " ") or nc.startswith(nv + " "):
            return True
    return False


def _application_matches(value: Any, candidates: List[str]) -> bool:
    nv = re.sub(r"\s+", "", str(value or "").upper())
    return bool(nv and nv in set(candidates))


def _sponsor_score(manufacturers: List[str], sponsors: List[str]) -> int:
    if not manufacturers or not sponsors:
        return 0

    mn = [_norm(x) for x in manufacturers if _norm(x)]
    sn = [_norm(x) for x in sponsors if _norm(x)]

    for m in mn:
        for s in sn:
            if m == s:
                return 3
            if len(m) >= 5 and len(s) >= 5 and (m in s or s in m):
                return 2
    return 0


def _canonical_indication_text(values: List[str]) -> str:
    cleaned = []
    seen = set()
    for value in values:
        text = re.sub(r"\s+", " ", str(value or "")).strip()
        if not text:
            continue
        n = _norm(text)
        if n in seen:
            continue
        seen.add(n)
        cleaned.append(text)
    return "\n\n".join(cleaned)


async def _json_get(params: Dict[str, Any], timeout_seconds: float = 25.0) -> Any:
    key = OPENFDA_LABEL_URL + "?" + "&".join(f"{k}={params[k]}" for k in sorted(params))
    now = time.time()
    cached = _http_cache.get(key)
    if cached and now - cached[0] < CACHE_TTL:
        return cached[1]

    headers = {
        "User-Agent": "PharmaCommercialIntelligence/1.0 (+official FDA label evidence)",
        "Accept": "application/json",
    }

    async with _sem():
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds, connect=8.0),
            follow_redirects=True,
            headers=headers,
        ) as client:
            response = await client.get(OPENFDA_LABEL_URL, params=params)

    if response.status_code == 404:
        payload = {"results": []}
        _http_cache[key] = (now, payload)
        return payload

    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"openFDA label request failed {response.status_code}",
        )

    try:
        payload = response.json()
    except Exception as exc:
        raise HTTPException(status_code=502, detail="openFDA returned invalid JSON") from exc

    _http_cache[key] = (now, payload)
    return payload



def _dailymed_application_candidates(values: List[str]) -> List[str]:
    """DailyMed can expose application numbers with or without NDA/ANDA/BLA prefixes."""
    out: List[str] = []
    seen = set()

    for value in values:
        token = re.sub(r"\s+", "", str(value or "").upper()).strip()
        if not token:
            continue

        candidates = [token]
        m = re.fullmatch(r"(?:NDA|ANDA|BLA)(\d{5,6})", token)
        if m:
            candidates.append(m.group(1))
        elif re.fullmatch(r"\d{5,6}", token):
            candidates.extend([f"BLA{token}", f"NDA{token}", f"ANDA{token}"])

        for candidate in candidates:
            if candidate not in seen:
                seen.add(candidate)
                out.append(candidate)

    return out[:30]


def _parse_daily_date(value: Any) -> float:
    text = str(value or "").strip()
    if not text:
        return 0.0
    for fmt in ("%b %d, %Y", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(text, fmt).timestamp()
        except Exception:
            pass
    return 0.0


def _xml_local(tag: Any) -> str:
    return str(tag or "").split("}")[-1]


def _extract_indications_from_spl_xml(xml_text: str) -> str:
    """
    Extract only the FDA/NLM INDICATIONS AND USAGE section (LOINC 34067-9).

    Prefer the section's own body text. If the coded parent section is only a
    container, collect text from descendant subsections inside that same
    indication section. This is required for labels such as immune globulins,
    whose indication content is split into nested subsections.
    """
    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return ""

    sections: List[str] = []

    def text_of(node: ET.Element) -> str:
        return re.sub(
            r"\s+",
            " ",
            " ".join(
                str(x).strip()
                for x in node.itertext()
                if str(x).strip()
            ),
        ).strip()

    for section in root.iter():
        if _xml_local(section.tag) != "section":
            continue

        code_match = False
        for node in section.iter():
            if (
                _xml_local(node.tag) == "code"
                and str(node.attrib.get("code") or "").strip() == "34067-9"
            ):
                code_match = True
                break

        if not code_match:
            continue

        title_text = ""
        direct_body: List[str] = []
        descendant_body: List[str] = []

        for child in list(section):
            local = _xml_local(child.tag)

            if local == "title" and not title_text:
                title_text = text_of(child)
                continue

            if local == "text":
                value = text_of(child)
                if value:
                    direct_body.append(value)

        if direct_body:
            body_text = _canonical_indication_text(direct_body)
        else:
            # The coded section is sometimes a container whose meaningful
            # content lives in nested child sections. Collect only descendant
            # <text> nodes under this coded indication section.
            for node in section.iter():
                if node is section or _xml_local(node.tag) != "text":
                    continue
                value = text_of(node)
                if value:
                    descendant_body.append(value)

            body_text = _canonical_indication_text(descendant_body)

        combined = re.sub(
            r"\s+",
            " ",
            " ".join(
                x for x in [title_text, body_text]
                if x
            ).strip(),
        ).strip()

        if combined:
            sections.append(combined)

    return _canonical_indication_text(sections)



def _extract_application_numbers_from_spl_xml(xml_text: str) -> List[str]:
    """
    Read NDA/ANDA/BLA identifiers directly from the official SPL XML.

    DailyMed's application-number index is useful but some biologic/vaccine
    labels are not consistently discoverable through that index. The SPL
    itself contains the marketing application identifier, so brand-search
    fallback verifies identity against the source document rather than
    trusting the search result alone.
    """
    found = set()
    pattern = re.compile(r"\b(?:NDA|ANDA|BLA)\s*[- ]?\s*\d{5,6}\b", re.I)

    try:
        root = ET.fromstring(xml_text)
    except Exception:
        root = None

    values: List[str] = []
    if root is not None:
        for node in root.iter():
            if node.text:
                values.append(str(node.text))
            for attr_value in node.attrib.values():
                values.append(str(attr_value))

    values.append(str(xml_text or ""))

    for value in values:
        for match in pattern.findall(value):
            token = re.sub(r"[^A-Za-z0-9]", "", match).upper()
            if token:
                found.add(token)

    return sorted(found)


async def _dailymed_json_get(
    url: str,
    params: Dict[str, Any],
    timeout_seconds: float = 25.0,
) -> Any:
    key = url + "?" + "&".join(f"{k}={params[k]}" for k in sorted(params))
    now = time.time()
    cached = _http_cache.get(key)
    if cached and now - cached[0] < CACHE_TTL:
        return cached[1]

    headers = {
        "User-Agent": "PharmaCommercialIntelligence/1.0 (+DailyMed official SPL fallback)",
        "Accept": "application/json",
    }

    async with _sem():
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds, connect=8.0),
            follow_redirects=True,
            headers=headers,
        ) as client:
            response = await client.get(url, params=params)

    if response.status_code == 404:
        payload = {"data": []}
        _http_cache[key] = (now, payload)
        return payload

    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"DailyMed request failed {response.status_code}",
        )

    try:
        payload = response.json()
    except Exception as exc:
        raise HTTPException(status_code=502, detail="DailyMed returned invalid JSON") from exc

    _http_cache[key] = (now, payload)
    return payload


async def _dailymed_xml_get(setid: str, timeout_seconds: float = 30.0) -> str:
    """
    Fetch the current SPL XML.

    DailyMed's REST /spls/{SETID}.xml endpoint can return an empty/404 response
    for labels that are nevertheless available in the official DailyMed ZIP
    download. Fall back to downloadzipfile.cfm and extract the SPL XML from
    that official package.
    """
    url = DAILYMED_SPL_XML_URL.format(setid=setid)
    cache_key = "SPLXML|" + setid
    now = time.time()
    cached = _http_cache.get(cache_key)
    if cached and now - cached[0] < CACHE_TTL:
        return str(cached[1] or "")

    headers = {
        "User-Agent": "PharmaCommercialIntelligence/1.0 (+DailyMed official SPL fallback)",
        "Accept": "application/xml,text/xml,*/*",
    }

    rest_text = ""
    rest_status = None

    try:
        async with _sem():
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(timeout_seconds, connect=8.0),
                follow_redirects=True,
                headers=headers,
            ) as client:
                response = await client.get(url)

        rest_status = response.status_code
        if response.status_code < 400:
            rest_text = response.text or ""
            if rest_text.strip():
                _http_cache[cache_key] = (now, rest_text)
                return rest_text
    except Exception:
        rest_status = None

    # Official ZIP fallback.
    zip_headers = {
        "User-Agent": "PharmaCommercialIntelligence/1.0 (+DailyMed official SPL ZIP fallback)",
        "Accept": "application/zip,application/octet-stream,*/*",
    }

    try:
        async with _sem():
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(timeout_seconds, connect=8.0),
                follow_redirects=True,
                headers=zip_headers,
            ) as client:
                zip_response = await client.get(
                    DAILYMED_SPL_ZIP_URL,
                    params={"setId": setid},
                )

        if zip_response.status_code >= 400:
            print(
                "US_BASELINE_DAILYMED_ZIP_HTTP_ERROR "
                + json.dumps(
                    {
                        "setid": setid,
                        "restStatus": rest_status,
                        "zipStatus": zip_response.status_code,
                    },
                    separators=(",", ":"),
                ),
                flush=True,
            )
            _http_cache[cache_key] = (now, "")
            return ""

        try:
            with zipfile.ZipFile(io.BytesIO(zip_response.content)) as zf:
                xml_names = [
                    name for name in zf.namelist()
                    if name.lower().endswith(".xml")
                    and not name.endswith("/")
                ]

                if not xml_names:
                    _http_cache[cache_key] = (now, "")
                    return ""

                # Main SPL XML is normally the largest XML document in the ZIP.
                ranked = sorted(
                    xml_names,
                    key=lambda name: zf.getinfo(name).file_size,
                    reverse=True,
                )

                xml_bytes = zf.read(ranked[0])
                xml_text = xml_bytes.decode("utf-8", errors="replace")

                print(
                    "US_BASELINE_DAILYMED_ZIP_USED "
                    + json.dumps(
                        {
                            "setid": setid,
                            "restStatus": rest_status,
                            "zipStatus": zip_response.status_code,
                            "xmlFile": ranked[0],
                            "xmlChars": len(xml_text),
                        },
                        separators=(",", ":"),
                    ),
                    flush=True,
                )

                _http_cache[cache_key] = (now, xml_text)
                return xml_text
        except Exception as exc:
            print(
                "US_BASELINE_DAILYMED_ZIP_PARSE_ERROR "
                + json.dumps(
                    {
                        "setid": setid,
                        "error": f"{type(exc).__name__}: {str(exc)[:500]}",
                    },
                    separators=(",", ":"),
                ),
                flush=True,
            )
            _http_cache[cache_key] = (now, "")
            return ""
    except Exception as exc:
        print(
            "US_BASELINE_DAILYMED_ZIP_FETCH_ERROR "
            + json.dumps(
                {
                    "setid": setid,
                    "restStatus": rest_status,
                    "error": f"{type(exc).__name__}: {str(exc)[:500]}",
                },
                separators=(",", ":"),
            ),
            flush=True,
        )
        _http_cache[cache_key] = (now, "")
        return ""


async def _daily_spls_by_application(app: str) -> List[Dict[str, Any]]:
    payload = await _dailymed_json_get(
        DAILYMED_SPLS_URL,
        {"application_number": app, "pagesize": 100, "page": 1},
    )
    return list(payload.get("data") or [])


async def _daily_spls_by_brand(brand: str) -> List[Dict[str, Any]]:
    payload = await _dailymed_json_get(
        DAILYMED_SPLS_URL,
        {"drug_name": brand, "name_type": "b", "pagesize": 100, "page": 1},
    )
    return list(payload.get("data") or [])


async def _daily_apps_for_setid(setid: str) -> List[str]:
    payload = await _dailymed_json_get(
        DAILYMED_APPLICATIONS_URL,
        {"setid": setid, "pagesize": 100, "page": 1},
    )
    values = []
    for row in list(payload.get("data") or []):
        value = re.sub(
            r"\s+",
            "",
            str(row.get("application_number") or "").upper(),
        ).strip()
        if value:
            values.append(value)
    return sorted(set(values))


async def _resolve_dailymed_product(
    product: BaselineProductInput,
    brand_candidates: List[str],
    openfda_apps: List[str],
) -> Dict[str, Any]:
    """
    Deterministic fallback when openFDA label harmonization has no exact row.

    Route A: DailyMed current SPLs filtered by application number + brand title.
    Route B: DailyMed current SPLs filtered by brand, then application-number
             overlap is re-verified through /applicationnumbers?setid=...
    Route C: for upstream scope-corroborated products only, accept an exact
             current DailyMed title already observed by the identity layer.
    """
    daily_apps = _dailymed_application_candidates(product.applicationNumbers)
    candidates_by_setid: Dict[str, Dict[str, Any]] = {}
    matched_route = None

    # Route A: application number first.
    for app in daily_apps:
        try:
            rows = await _daily_spls_by_application(app)
        except Exception:
            rows = []

        for row in rows:
            setid = str(row.get("setid") or "").strip()
            title = str(row.get("title") or "").strip()
            if not setid or not title:
                continue
            if not _brand_matches(title, brand_candidates):
                continue
            candidates_by_setid[setid] = row

    if candidates_by_setid:
        matched_route = "DAILYMED_APPLICATION_PLUS_BRAND"

    # Route B: brand search, then verify the application number directly
    # from the official SPL XML. This is more robust for BLAs/vaccines and
    # legacy labels that are not consistently indexed by /applicationnumbers.
    prefetched_xml: Dict[str, str] = {}

    if not candidates_by_setid:
        brand_rows: Dict[str, Dict[str, Any]] = {}

        for brand in brand_candidates[:3]:
            try:
                rows = await _daily_spls_by_brand(brand)
            except Exception:
                rows = []

            for row in rows:
                setid = str(row.get("setid") or "").strip()
                title = str(row.get("title") or "").strip()
                if not setid or not title:
                    continue
                if not _brand_matches(title, brand_candidates):
                    continue
                brand_rows[setid] = row

        ordered_brand_rows = sorted(
            brand_rows.values(),
            key=lambda x: _parse_daily_date(x.get("published_date")),
            reverse=True,
        )[:12]

        if ordered_brand_rows:
            xml_values = await asyncio.gather(
                *[
                    _dailymed_xml_get(str(row.get("setid") or "").strip())
                    for row in ordered_brand_rows
                ],
                return_exceptions=True,
            )

            input_apps = set(_dailymed_application_candidates(daily_apps))

            for row, xml_value in zip(ordered_brand_rows, xml_values):
                if isinstance(xml_value, Exception):
                    continue

                setid = str(row.get("setid") or "").strip()
                xml_text = str(xml_value or "")
                if not setid or not xml_text:
                    continue

                source_apps = set(
                    _dailymed_application_candidates(
                        _extract_application_numbers_from_spl_xml(xml_text)
                    )
                )

                if source_apps.intersection(input_apps):
                    candidates_by_setid[setid] = row
                    prefetched_xml[setid] = xml_text

        if candidates_by_setid:
            matched_route = "DAILYMED_BRAND_PLUS_SPL_XML_APPLICATION_VERIFY"

        # Route C: the upstream identity + scope layers may already have
        # observed an exact DailyMed family/presentation title even when the
        # SPL exposes no usable Drugs@FDA application number. Reuse that
        # evidence only when the request explicitly marks the product as
        # scope-corroborated and the current DailyMed search returns the exact
        # same title. This remains read-only label evidence retrieval; it does
        # not infer company ownership or broaden the product family.
        if not candidates_by_setid and brand_rows and not daily_apps:
            if product.dailyMedScopeCorroborated and product.dailyMedTitles:
                hinted_titles = {
                    _norm(x)
                    for x in product.dailyMedTitles
                    if _norm(x)
                }

                for setid, row in brand_rows.items():
                    title = str(row.get("title") or "").strip()
                    if _norm(title) in hinted_titles:
                        candidates_by_setid[setid] = row

                if candidates_by_setid:
                    matched_route = "DAILYMED_SCOPE_CORROBORATED_EXACT_TITLE"
            else:
                # The authenticated Airtable caller only submits application-
                # free products through its upstream exact DailyMed family /
                # presentation scope gate. Re-evaluate the current official
                # DailyMed brand family here and fail closed downstream if
                # multiple indication statements disagree.
                candidates_by_setid.update(brand_rows)
                matched_route = "DAILYMED_NO_APPLICATION_BRAND_FAMILY"

    if not candidates_by_setid:
        print(
            "US_BASELINE_DAILYMED_FALLBACK_NONE "
            + json.dumps(
                {
                    "recordId": product.recordId,
                    "name": product.name,
                    "brandCandidates": brand_candidates,
                    "applicationCandidates": daily_apps,
                },
                separators=(",", ":"),
            ),
            flush=True,
        )
        return {
            "recordId": product.recordId,
            "sourceName": product.name,
            "status": "Not Found",
            "confidence": "Low",
            "applicationNumbers": sorted(set(openfda_apps)),
            "splSetIds": [],
            "activeIngredients": product.activeIngredients,
            "indicationText": "",
            "sourceUrl": None,
            "authority": "DailyMed SPL API",
            "ambiguous": False,
            "diagnostics": {
                "fallbackRoute": "DAILYMED_NONE",
                "candidateBrands": brand_candidates,
                "applicationCandidates": daily_apps,
                "candidateSplCount": 0,
                "dailyMedScopeCorroborated": product.dailyMedScopeCorroborated,
                "dailyMedTitleHintCount": len(product.dailyMedTitles),
            },
        }

    # Fetch only a bounded number of current matching SPLs.
    selected = sorted(
        candidates_by_setid.values(),
        key=lambda x: _parse_daily_date(x.get("published_date")),
        reverse=True,
    )[:8]

    fetched = await asyncio.gather(
        *[
            (
                asyncio.sleep(
                    0,
                    result=prefetched_xml[
                        str(row.get("setid") or "").strip()
                    ],
                )
                if str(row.get("setid") or "").strip() in prefetched_xml
                else _dailymed_xml_get(
                    str(row.get("setid") or "").strip()
                )
            )
            for row in selected
        ],
        return_exceptions=True,
    )

    label_rows = []
    for row, xml_value in zip(selected, fetched):
        if isinstance(xml_value, Exception):
            continue

        setid = str(row.get("setid") or "").strip()
        indication_text = _extract_indications_from_spl_xml(str(xml_value or ""))
        if not indication_text:
            continue

        title = str(row.get("title") or "").strip()
        bracket = re.search(r"\[([^\]]+)\]\s*$", title)
        labeler = bracket.group(1).strip() if bracket else ""
        sponsor_score = _sponsor_score(
            [labeler] if labeler else [],
            product.sponsorNames,
        )

        label_rows.append({
            "setid": setid,
            "title": title,
            "publishedDate": str(row.get("published_date") or ""),
            "publishedTimestamp": _parse_daily_date(row.get("published_date")),
            "indicationText": indication_text,
            "normalizedIndicationText": _norm(indication_text),
            "sponsorScore": sponsor_score,
        })

    if not label_rows:
        diagnostic_xml = ""
        diagnostic_setid = ""
        if selected:
            diagnostic_setid = str(selected[0].get("setid") or "").strip()
            diagnostic_xml = str(
                prefetched_xml.get(diagnostic_setid) or ""
            )
            if not diagnostic_xml and fetched:
                first_xml = fetched[0]
                if not isinstance(first_xml, Exception):
                    diagnostic_xml = str(first_xml or "")

        code_index = diagnostic_xml.find("34067-9")
        code_snippet = (
            diagnostic_xml[
                max(0, code_index - 700):
                code_index + 2600
            ]
            if code_index >= 0
            else diagnostic_xml[:2600]
        )

        print(
            "US_BASELINE_DAILYMED_FALLBACK_NO_TEXT "
            + json.dumps(
                {
                    "recordId": product.recordId,
                    "name": product.name,
                    "route": matched_route,
                    "candidateSpls": [
                        {
                            "setid": str(x.get("setid") or ""),
                            "title": str(x.get("title") or ""),
                            "publishedDate": str(x.get("published_date") or ""),
                        }
                        for x in selected
                    ],
                    "diagnosticSetid": diagnostic_setid,
                    "xmlChars": len(diagnostic_xml),
                    "has34067": code_index >= 0,
                    "xmlSnippet": code_snippet,
                },
                separators=(",", ":"),
            ),
            flush=True,
        )
        return {
            "recordId": product.recordId,
            "sourceName": product.name,
            "status": "No Indication Text",
            "confidence": "Low",
            "applicationNumbers": sorted(set(openfda_apps)),
            "splSetIds": sorted(candidates_by_setid.keys()),
            "activeIngredients": product.activeIngredients,
            "indicationText": "",
            "sourceUrl": None,
            "authority": "DailyMed SPL API",
            "ambiguous": False,
            "diagnostics": {
                "fallbackRoute": matched_route,
                "candidateBrands": brand_candidates,
                "applicationCandidates": daily_apps,
                "candidateSplCount": len(candidates_by_setid),
                "splsWithIndicationText": 0,
            },
        }

    best_sponsor_score = max(x["sponsorScore"] for x in label_rows)
    sponsor_pool = (
        [x for x in label_rows if x["sponsorScore"] == best_sponsor_score]
        if best_sponsor_score > 0
        else label_rows
    )

    distinct_texts: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for item in sponsor_pool:
        if item["normalizedIndicationText"]:
            distinct_texts[item["normalizedIndicationText"]].append(item)

    ambiguous = len(distinct_texts) > 1
    chosen = sorted(
        sponsor_pool,
        key=lambda x: (x["sponsorScore"], x["publishedTimestamp"]),
        reverse=True,
    )[0]

    print(
        "US_BASELINE_DAILYMED_FALLBACK_MATCH "
        + json.dumps(
            {
                "recordId": product.recordId,
                "name": product.name,
                "route": matched_route,
                "chosenSetid": chosen["setid"],
                "ambiguous": ambiguous,
            },
            separators=(",", ":"),
        ),
        flush=True,
    )

    return {
        "recordId": product.recordId,
        "sourceName": product.name,
        "status": "Ambiguous" if ambiguous else "Matched",
        "confidence": "Medium" if ambiguous else "High",
        "applicationNumbers": sorted(set(openfda_apps)),
        "splSetIds": sorted({x["setid"] for x in sponsor_pool}),
        "activeIngredients": sorted({
            str(x).strip()
            for x in (
                list(product.activeIngredients or [])
                + list(chosen.get("activeIngredients") or [])
            )
            if str(x).strip()
        }),
        "indicationText": chosen["indicationText"],
        "sourceUrl": (
            "https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid="
            + chosen["setid"]
        ),
        "authority": "DailyMed SPL API",
        "effectiveTime": chosen["publishedDate"] or None,
        "ambiguous": ambiguous,
        "diagnostics": {
            "fallbackRoute": matched_route,
            "candidateBrands": brand_candidates,
            "applicationCandidates": daily_apps,
            "candidateSplCount": len(candidates_by_setid),
            "splsWithIndicationText": len(label_rows),
            "bestSponsorScore": best_sponsor_score,
            "distinctIndicationStatements": len(distinct_texts),
            "titles": sorted({x["title"] for x in sponsor_pool}),
        },
    }


def _pfizer_slug_candidates(raw_name: str) -> List[str]:
    cleaned = _clean_brand(raw_name)
    values = [cleaned]
    if cleaned:
        first = cleaned.split()[0]
        if len(first) >= 4:
            values.append(first)

    out: List[str] = []
    seen = set()
    for value in values:
        slug = re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-")
        if slug and slug not in seen:
            seen.add(slug)
            out.append(slug)
    return out[:3]


def _strip_html(value: str) -> str:
    text = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", str(value or ""))
    text = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


async def _text_get(url: str, timeout_seconds: float = 30.0) -> tuple[int, str, str]:
    now = time.time()
    cached = _http_cache.get(url)
    if cached and now - cached[0] < CACHE_TTL:
        payload = cached[1]
        if isinstance(payload, dict) and payload.get("__text_cache__"):
            return (
                int(payload.get("status") or 200),
                str(payload.get("contentType") or ""),
                str(payload.get("text") or ""),
            )

    headers = {
        "User-Agent": "PharmaCommercialIntelligence/1.0 (+current manufacturer label verification)",
        "Accept": "text/html,application/pdf,application/xhtml+xml,*/*",
    }

    async with _sem():
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds, connect=8.0),
            follow_redirects=True,
            headers=headers,
        ) as client:
            response = await client.get(url)

    value = {
        "__text_cache__": True,
        "status": response.status_code,
        "contentType": str(response.headers.get("content-type") or ""),
        "text": response.text if "pdf" not in str(response.headers.get("content-type") or "").lower() else "",
    }
    _http_cache[url] = (now, value)
    return response.status_code, value["contentType"], value["text"]


async def _bytes_get(url: str, timeout_seconds: float = 35.0) -> tuple[int, str, bytes]:
    headers = {
        "User-Agent": "PharmaCommercialIntelligence/1.0 (+current manufacturer label verification)",
        "Accept": "application/pdf,text/html,*/*",
    }
    async with _sem():
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds, connect=8.0),
            follow_redirects=True,
            headers=headers,
        ) as client:
            response = await client.get(url)
    return (
        response.status_code,
        str(response.headers.get("content-type") or ""),
        response.content,
    )


def _pfizer_label_pdf_url(url: str) -> Optional[str]:
    parsed = urlparse(str(url or ""))
    if "labeling.pfizer.com" not in parsed.netloc.lower():
        return None
    qs = parse_qs(parsed.query)
    label_ids = qs.get("id") or qs.get("ID") or []
    if not label_ids:
        return None
    label_id = str(label_ids[0]).strip()
    if not label_id:
        return None
    return PFIZER_LABEL_BASE + "?" + urlencode({"format": "PDF", "id": label_id})


def _extract_pdf_text(content: bytes) -> str:
    if not content or not content.startswith(b"%PDF"):
        return ""
    try:
        doc = fitz.open(stream=content, filetype="pdf")
        parts = []
        for page in doc:
            parts.append(page.get_text("text"))
        return "\n".join(parts)
    except Exception:
        return ""


def _extract_current_indications(text: str) -> str:
    raw = str(text or "").replace("\r", "\n")
    raw = re.sub(r"[ \t]+", " ", raw)
    raw = re.sub(r"\n{3,}", "\n\n", raw)

    start_patterns = [
        r"(?im)^\s*1\s+INDICATIONS\s+AND\s+USAGE\s*$",
        r"(?im)^\s*INDICATIONS\s+AND\s+USAGE\s*$",
        r"(?im)^\s*INDICATIONS\s*$",
    ]
    end_patterns = [
        r"(?im)^\s*2\s+DOSAGE\s+AND\s+ADMINISTRATION\b",
        r"(?im)^\s*DOSAGE\s+AND\s+ADMINISTRATION\b",
        r"(?im)^\s*4\s+CONTRAINDICATIONS\b",
        r"(?im)^\s*CONTRAINDICATIONS\b",
        r"(?im)^\s*WARNINGS\b",
    ]

    starts: List[int] = []
    for pattern in start_patterns:
        starts.extend(m.start() for m in re.finditer(pattern, raw))

    candidates: List[str] = []
    for start in sorted(set(starts)):
        tail = raw[start:]
        end_positions = []
        for pattern in end_patterns:
            m = re.search(pattern, tail[20:])
            if m:
                end_positions.append(20 + m.start())
        end = min(end_positions) if end_positions else min(len(tail), 16000)
        segment = tail[:end].strip()
        n = _norm(segment)
        if len(n) < 30:
            continue
        indication_signal = len(re.findall(r"\bindicat(?:ed|ion)\b", n))
        if indication_signal == 0:
            continue
        candidates.append(segment)

    if not candidates:
        return ""

    # Prefer the candidate with the richest actual indication wording, not a
    # table-of-contents line.
    chosen = max(
        candidates,
        key=lambda x: (
            len(re.findall(r"\bindicat(?:ed|ion)\b", _norm(x))),
            min(len(x), 12000),
        ),
    )
    return re.sub(r"\s+", " ", chosen).strip()



async def _pfizer_label_portal_search(
    product: BaselineProductInput,
) -> List[Dict[str, str]]:
    base = os.getenv("BROWSER_FETCH_BASE_URL", "").strip().rstrip("/")
    key = os.getenv("BROWSER_FETCH_KEY", "").strip()
    if not base or not key:
        return []

    brand = _clean_brand(product.name)
    if not brand:
        return []

    endpoint = f"{base}/pfizer/label-search"
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(45.0, connect=12.0),
            follow_redirects=False,
        ) as client:
            response = await client.get(
                endpoint,
                params={
                    "brand": brand,
                    "timeout_seconds": 35.0,
                },
                headers={"X-Browser-Key": key},
            )
    except Exception as exc:
        print(
            "US_BASELINE_PFIZER_LABEL_PORTAL_ERROR "
            + json.dumps(
                {
                    "recordId": product.recordId,
                    "name": product.name,
                    "error": f"{type(exc).__name__}: {str(exc)[:400]}",
                },
                separators=(",", ":"),
            ),
            flush=True,
        )
        return []

    if response.status_code >= 400:
        print(
            "US_BASELINE_PFIZER_LABEL_PORTAL_ERROR "
            + json.dumps(
                {
                    "recordId": product.recordId,
                    "name": product.name,
                    "status": response.status_code,
                    "body": response.text[:500],
                },
                separators=(",", ":"),
            ),
            flush=True,
        )
        return []

    try:
        payload = response.json()
    except Exception:
        return []

    results = []
    for item in list(payload.get("links") or []):
        href = str(item.get("href") or "").strip()
        anchor = re.sub(r"\s+", " ", str(item.get("text") or "")).strip()
        if "labeling.pfizer.com" not in href.lower():
            continue
        if "showlabeling.aspx" not in href.lower():
            continue
        results.append({
            "href": href,
            "anchor": anchor,
            "productDetailUrl": "https://labeling.pfizer.com/",
            "score": "9",
        })

    print(
        "US_BASELINE_PFIZER_LABEL_PORTAL_RESULT "
        + json.dumps(
            {
                "recordId": product.recordId,
                "name": product.name,
                "brand": brand,
                "linkCount": len(results),
                "links": [x["href"] for x in results[:10]],
            },
            separators=(",", ":"),
        ),
        flush=True,
    )

    return results[:12]

async def _pfizer_current_label_links(product: BaselineProductInput) -> List[Dict[str, str]]:
    candidates = _brand_candidates(product.name)
    links: List[Dict[str, str]] = []
    seen = set()

    # Prefer Pfizer's own labeling portal search. This bypasses Pfizer.com
    # product-detail pages, which currently return HTTP 403 to cloud/browser
    # workers even though the labeling portal itself is public.
    portal_links = await _pfizer_label_portal_search(product)
    for item in portal_links:
        href = str(item.get("href") or "").strip()
        if not href:
            continue
        key = href.lower()
        if key in seen:
            continue
        seen.add(key)
        links.append(item)

    if links:
        return links[:6]

    def add_link(href: str, anchor: str, product_url: str) -> None:
        href = str(href or "").strip()
        anchor = re.sub(r"\s+", " ", str(anchor or "")).strip()
        if "labeling.pfizer.com" not in href.lower():
            return

        na = _norm(anchor)
        if any(
            blocked in na
            for blocked in [
                "medication guide",
                "patient information",
                "patient leaflet",
                "instructions for use",
                "ifu",
            ]
        ):
            return

        score = 0
        if "prescribing information" in na:
            score += 5
        if "physician" in na:
            score += 2
        if any(_norm(c) in na for c in candidates):
            score += 2

        key = href.lower()
        if key in seen:
            return
        seen.add(key)
        links.append({
            "href": href,
            "anchor": anchor,
            "score": str(score),
            "productDetailUrl": product_url,
        })

    for slug in _pfizer_slug_candidates(product.name):
        url = PFIZER_PRODUCT_DETAIL_URL.format(slug=slug)
        status = None
        html = ""

        try:
            status, _ctype, html = await _text_get(url)
        except Exception:
            pass

        if status == 200 and html:
            page_text = _strip_html(html)
            if any(_norm(c) in _norm(page_text[:7000]) for c in candidates):
                for m in re.finditer(
                    r'(?is)<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
                    html,
                ):
                    add_link(
                        unescape(str(m.group(1) or "")),
                        _strip_html(str(m.group(2) or "")),
                        url,
                    )

        # Pfizer product-detail pages are JavaScript-rendered in production.
        # If static HTML did not expose a U.S. PI link, use the existing
        # read-only Playwright browser worker and consume its structured anchors.
        if not links:
            try:
                browser = await _browser_payload(
                    url=url,
                    timeout_seconds=35.0,
                    reason="PFIZER_PRODUCT_DETAIL_JS_RENDER",
                    direct_status=status,
                    direct_version=None,
                )
            except Exception as exc:
                print(
                    "US_BASELINE_PFIZER_BROWSER_ERROR "
                    + json.dumps(
                        {
                            "recordId": product.recordId,
                            "name": product.name,
                            "url": url,
                            "error": f"{type(exc).__name__}: {str(exc)[:400]}",
                        },
                        separators=(",", ":"),
                    ),
                    flush=True,
                )
                browser = None

            if browser:
                visible = _norm(browser.get("visibleText") or "")
                if any(_norm(c) in visible for c in candidates):
                    for item in list(browser.get("anchors") or []):
                        add_link(
                            str(item.get("url") or item.get("href") or ""),
                            str(item.get("text") or ""),
                            url,
                        )

        if links:
            break

    links.sort(key=lambda x: int(x.get("score") or 0), reverse=True)
    return links[:6]



def _extract_label_active_ingredients(
    label_text: str,
    brand_candidates: List[str],
) -> List[str]:
    """
    Recover the labelled active ingredient from the title/header of a current
    manufacturer PI, e.g. "MEDROL (methylprednisolone) Tablets".
    """
    raw = re.sub(r"\s+", " ", str(label_text or "")[:5000]).strip()
    if not raw:
        return []

    out: List[str] = []
    seen = set()

    for brand in brand_candidates:
        escaped = re.escape(_clean_brand(brand))
        if not escaped:
            continue

        patterns = [
            rf"(?i)\b{escaped}\b\s*[®™]?\s*\(([^)]{{2,180}})\)",
            rf"(?i)\b{escaped}\b\s*[®™]?\s+([a-z][a-z0-9 -]{{2,120}}?)\s+(?:tablets?|capsules?|injection|oral solution|cream|ointment)\b",
        ]

        for pattern in patterns:
            m = re.search(pattern, raw)
            if not m:
                continue

            value = re.sub(r"\s+", " ", str(m.group(1) or "")).strip(" ,;:-")
            n = _norm(value)
            if value and n and n not in seen:
                seen.add(n)
                out.append(value)

    return out[:10]



async def _resolve_pfizer_current_label(
    product: BaselineProductInput,
    openfda_apps: List[str],
) -> Dict[str, Any]:
    links = await _pfizer_current_label_links(product)
    brand_candidates = _brand_candidates(product.name)

    if not links:
        print(
            "US_BASELINE_PFIZER_CURRENT_LABEL_NONE "
            + json.dumps(
                {
                    "recordId": product.recordId,
                    "name": product.name,
                    "reason": "NO_PRODUCT_DETAIL_LABEL_LINK",
                },
                separators=(",", ":"),
            ),
            flush=True,
        )
        return {
            "recordId": product.recordId,
            "sourceName": product.name,
            "status": "Not Found",
            "confidence": "Low",
            "applicationNumbers": sorted(set(openfda_apps)),
            "splSetIds": [],
            "activeIngredients": product.activeIngredients,
            "indicationText": "",
            "sourceUrl": None,
            "authority": "Pfizer U.S. Prescribing Information",
            "ambiguous": False,
            "diagnostics": {
                "fallbackRoute": "PFIZER_PRODUCT_DETAIL_NONE",
            },
        }

    resolved = []
    for link in links:
        href = link["href"]
        pdf_url = _pfizer_label_pdf_url(href) or href
        try:
            status, content_type, content = await _bytes_get(pdf_url)
        except Exception:
            continue

        if status != 200 or not content:
            continue

        if content.startswith(b"%PDF") or "pdf" in content_type.lower():
            label_text = _extract_pdf_text(content)
        else:
            try:
                label_text = _strip_html(content.decode("utf-8", errors="ignore"))
            except Exception:
                label_text = ""

        if not label_text:
            continue

        top = _norm(label_text[:6000])
        if not any(_norm(c) in top for c in brand_candidates):
            continue

        indication_text = _extract_current_indications(label_text)
        if not indication_text:
            continue

        resolved.append({
            "sourceUrl": href,
            "pdfUrl": pdf_url,
            "productDetailUrl": link["productDetailUrl"],
            "anchor": link["anchor"],
            "score": int(link.get("score") or 0),
            "indicationText": indication_text,
            "normalizedIndicationText": _norm(indication_text),
            "activeIngredients": _extract_label_active_ingredients(
                label_text,
                brand_candidates,
            ),
        })

    if not resolved:
        print(
            "US_BASELINE_PFIZER_CURRENT_LABEL_NO_TEXT "
            + json.dumps(
                {
                    "recordId": product.recordId,
                    "name": product.name,
                    "linkCount": len(links),
                    "links": [x.get("href") for x in links],
                },
                separators=(",", ":"),
            ),
            flush=True,
        )
        return {
            "recordId": product.recordId,
            "sourceName": product.name,
            "status": "No Indication Text",
            "confidence": "Low",
            "applicationNumbers": sorted(set(openfda_apps)),
            "splSetIds": [],
            "activeIngredients": product.activeIngredients,
            "indicationText": "",
            "sourceUrl": None,
            "authority": "Pfizer U.S. Prescribing Information",
            "ambiguous": False,
            "diagnostics": {
                "fallbackRoute": "PFIZER_PRODUCT_DETAIL_LABEL_NO_TEXT",
                "linkCount": len(links),
            },
        }

    best_score = max(x["score"] for x in resolved)
    score_pool = [x for x in resolved if x["score"] == best_score]

    distinct: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for item in score_pool:
        distinct[item["normalizedIndicationText"]].append(item)

    ambiguous = len(distinct) > 1
    chosen = score_pool[0]

    print(
        "US_BASELINE_PFIZER_CURRENT_LABEL "
        + json.dumps(
            {
                "recordId": product.recordId,
                "name": product.name,
                "sourceUrl": chosen["sourceUrl"],
                "ambiguous": ambiguous,
                "candidateLabels": len(score_pool),
            },
            separators=(",", ":"),
        ),
        flush=True,
    )

    return {
        "recordId": product.recordId,
        "sourceName": product.name,
        "status": "Ambiguous" if ambiguous else "Matched",
        "confidence": "Medium" if ambiguous else "High",
        "applicationNumbers": sorted(set(openfda_apps)),
        "splSetIds": [],
        "activeIngredients": product.activeIngredients,
        "indicationText": chosen["indicationText"],
        "sourceUrl": chosen["sourceUrl"],
        "authority": "Pfizer U.S. Prescribing Information",
        "ambiguous": ambiguous,
        "diagnostics": {
            "fallbackRoute": "PFIZER_PRODUCT_DETAIL_CURRENT_US_PI",
            "productDetailUrl": chosen["productDetailUrl"],
            "candidateLabelCount": len(score_pool),
            "candidateAnchors": [x["anchor"] for x in score_pool],
            "activeIngredients": chosen.get("activeIngredients") or [],
            "distinctIndicationStatements": len(distinct),
        },
    }



async def _drugsfda_json_get(
    params: Dict[str, Any],
    timeout_seconds: float = 25.0,
) -> Any:
    key = OPENFDA_DRUGSFDA_URL + "?" + "&".join(
        f"{k}={params[k]}" for k in sorted(params)
    )
    now = time.time()
    cached = _http_cache.get(key)
    if cached and now - cached[0] < CACHE_TTL:
        return cached[1]

    headers = {
        "User-Agent": "PharmaCommercialIntelligence/1.0 (+FDA application-family reconciliation)",
        "Accept": "application/json",
    }

    async with _sem():
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds, connect=8.0),
            follow_redirects=True,
            headers=headers,
        ) as client:
            response = await client.get(
                OPENFDA_DRUGSFDA_URL,
                params=params,
            )

    if response.status_code == 404:
        payload = {"results": []}
        _http_cache[key] = (now, payload)
        return payload

    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"openFDA Drugs@FDA request failed {response.status_code}",
        )

    try:
        payload = response.json()
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="openFDA Drugs@FDA returned invalid JSON",
        ) from exc

    _http_cache[key] = (now, payload)
    return payload


def _strict_ingredient_family_match(
    product_ingredients: List[str],
    source_ingredients: List[str],
) -> bool:
    product_norm = {
        _norm(x)
        for x in product_ingredients
        if _norm(x)
    }
    source_norm = {
        _norm(x)
        for x in source_ingredients
        if _norm(x)
    }

    if not product_norm:
        return False
    if not source_norm:
        return False

    return product_norm.issubset(source_norm)


async def _drugsfda_application_family(
    product: BaselineProductInput,
) -> Dict[str, Any]:
    brands = _brand_candidates(product.name)
    applications = set()
    variants = []
    rejected = []

    for brand in brands[:3]:
        clean = _clean_brand(brand)
        if not clean:
            continue

        params: Dict[str, Any] = {
            "search": f'products.brand_name:"{clean}"',
            "limit": 99,
        }
        api_key = os.getenv("OPENFDA_API_KEY", "").strip()
        if api_key:
            params["api_key"] = api_key

        try:
            payload = await _drugsfda_json_get(params)
        except Exception:
            continue

        for row in list(payload.get("results") or []):
            app = str(row.get("application_number") or "").strip()
            sponsor = str(row.get("sponsor_name") or "").strip()

            exact_brand_products = [
                p
                for p in (row.get("products") or [])
                if any(
                    _brand_matches(
                        p.get("brand_name"),
                        brands,
                    )
                    for _ in [0]
                )
            ]

            if not exact_brand_products:
                continue

            ingredients = sorted({
                str(ai.get("name") or "").strip()
                for p in exact_brand_products
                for ai in (p.get("active_ingredients") or [])
                if str(ai.get("name") or "").strip()
            })

            compatible = _strict_ingredient_family_match(
                list(product.activeIngredients or []),
                ingredients,
            )

            variant = {
                "applicationNumber": app,
                "sponsorName": sponsor,
                "activeIngredients": ingredients,
                "dosageForms": sorted({
                    str(p.get("dosage_form") or "").strip()
                    for p in exact_brand_products
                    if str(p.get("dosage_form") or "").strip()
                }),
                "marketingStatuses": sorted({
                    str(p.get("marketing_status") or "").strip()
                    for p in exact_brand_products
                    if str(p.get("marketing_status") or "").strip()
                }),
                "ingredientFamilyCompatible": compatible,
            }

            if compatible:
                if app:
                    applications.add(app)
                variants.append(variant)
            else:
                rejected.append(variant)

    return {
        "applicationNumbers": sorted(applications),
        "variants": variants,
        "rejectedVariants": rejected[:20],
    }


def _application_family_reconciles(
    input_apps: List[str],
    source_apps: List[str],
    family_apps: List[str],
) -> bool:
    expanded_input = set(_application_candidates(input_apps))
    expanded_source = set(_application_candidates(source_apps))
    expanded_family = set(_application_candidates(family_apps))

    return bool(
        expanded_input
        and expanded_source
        and expanded_family
        and expanded_input.intersection(expanded_family)
        and expanded_source.intersection(expanded_family)
    )



def _ingredient_compatibility(
    product_ingredients: List[str],
    label_values: List[str],
) -> Dict[str, Any]:
    product_norm = [_norm(x) for x in product_ingredients if _norm(x)]
    label_norm = [_norm(x) for x in label_values if _norm(x)]
    label_joined = " | ".join(label_norm)

    matched = []
    unmatched = []

    for ingredient in product_norm:
        compatible = any(
            ingredient == label
            or ingredient in label
            or label in ingredient
            for label in label_norm
            if len(label) >= 4
        )
        if not compatible and ingredient:
            compatible = ingredient in label_joined
        (matched if compatible else unmatched).append(ingredient)

    return {
        "productCount": len(product_norm),
        "matchedCount": len(matched),
        "matched": matched,
        "unmatched": unmatched,
        "allMatched": bool(product_norm) and not unmatched,
        "anyMatched": bool(matched),
    }


async def _openfda_brand_rows(product: BaselineProductInput) -> List[Dict[str, Any]]:
    brands = _brand_candidates(product.name)
    rows: List[Dict[str, Any]] = []
    seen = set()

    for brand in brands[:3]:
        clean = _clean_brand(brand)
        if not clean:
            continue

        params: Dict[str, Any] = {
            "search": f'openfda.brand_name:"{clean}"',
            "limit": 100,
        }
        api_key = os.getenv("OPENFDA_API_KEY", "").strip()
        if api_key:
            params["api_key"] = api_key

        try:
            payload = await _json_get(params)
        except Exception:
            continue

        for row in list(payload.get("results") or []):
            ofda = row.get("openfda") or {}
            row_brands = [str(x) for x in (ofda.get("brand_name") or [])]
            if not any(_brand_matches(x, brands) for x in row_brands):
                continue

            marker = (
                str(row.get("id") or "")
                + "|"
                + "|".join(ofda.get("spl_set_id") or [])
                + "|"
                + str(row.get("effective_time") or "")
            )
            if marker in seen:
                continue
            seen.add(marker)
            rows.append(row)

    return rows


async def _resolve_openfda_brand_product(
    product: BaselineProductInput,
    input_apps: List[str],
) -> Dict[str, Any]:
    rows = await _openfda_brand_rows(product)
    brands = _brand_candidates(product.name)

    compatible = []
    diagnostics = []

    for row in rows:
        ofda = row.get("openfda") or {}
        label_ingredients = [
            str(x)
            for x in (
                list(ofda.get("generic_name") or [])
                + list(ofda.get("substance_name") or [])
            )
        ]
        compatibility = _ingredient_compatibility(
            list(product.activeIngredients or []),
            label_ingredients,
        )

        indication_text = _canonical_indication_text(
            [str(x) for x in (row.get("indications_and_usage") or [])]
        )

        diagnostics.append({
            "brands": [str(x) for x in (ofda.get("brand_name") or [])],
            "genericNames": [str(x) for x in (ofda.get("generic_name") or [])],
            "substanceNames": [str(x) for x in (ofda.get("substance_name") or [])],
            "manufacturers": [str(x) for x in (ofda.get("manufacturer_name") or [])],
            "applicationNumbers": [str(x) for x in (ofda.get("application_number") or [])],
            "splSetIds": [str(x) for x in (ofda.get("spl_set_id") or [])],
            "effectiveTime": str(row.get("effective_time") or ""),
            "ingredientCompatibility": compatibility,
            "hasIndicationText": bool(indication_text),
        })

        if not indication_text:
            continue

        # For a single-ingredient product, exact brand + one compatible active
        # ingredient is sufficient. For multi-ingredient families require at
        # least half of the source ingredients and never zero. This allows
        # formulation families such as VIBRAMYCIN while failing closed when
        # the brand name is reused for a materially different composition.
        product_count = int(compatibility["productCount"] or 0)
        matched_count = int(compatibility["matchedCount"] or 0)
        min_required = 1 if product_count <= 2 else max(2, (product_count + 1) // 2)

        if matched_count < min_required:
            continue

        sponsor_score = _sponsor_score(
            [str(x) for x in (ofda.get("manufacturer_name") or [])],
            product.sponsorNames,
        )

        compatible.append({
            "row": row,
            "indicationText": indication_text,
            "normalizedIndicationText": _norm(indication_text),
            "effectiveTime": str(row.get("effective_time") or ""),
            "sponsorScore": sponsor_score,
            "ingredientCompatibility": compatibility,
        })

    if not compatible:
        return {
            "recordId": product.recordId,
            "sourceName": product.name,
            "status": "Not Found",
            "confidence": "Low",
            "applicationNumbers": sorted(set(input_apps)),
            "splSetIds": [],
            "activeIngredients": product.activeIngredients,
            "indicationText": "",
            "sourceUrl": None,
            "authority": "FDA / DailyMed SPL",
            "ambiguous": False,
            "diagnostics": {
                "fallbackRoute": "OPENFDA_BRAND_INGREDIENT_NONE",
                "candidateBrands": brands,
                "inputApplicationNumbers": sorted(set(input_apps)),
                "brandRows": diagnostics[:20],
            },
        }

    # Prefer the latest exact-brand current SPL. Sponsor agreement is a
    # tiebreaker, not a hard requirement, because Pfizer catalogue families
    # include legacy holders and acquired products.
    latest_effective = max(x["effectiveTime"] for x in compatible)
    latest_pool = [
        x for x in compatible
        if x["effectiveTime"] == latest_effective
    ]

    best_sponsor_score = max(x["sponsorScore"] for x in latest_pool)
    sponsor_pool = (
        [x for x in latest_pool if x["sponsorScore"] == best_sponsor_score]
        if best_sponsor_score > 0
        else latest_pool
    )

    distinct: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for item in sponsor_pool:
        if item["normalizedIndicationText"]:
            distinct[item["normalizedIndicationText"]].append(item)

    ambiguous = len(distinct) > 1
    chosen = sorted(
        sponsor_pool,
        key=lambda x: (
            x["sponsorScore"],
            x["ingredientCompatibility"]["matchedCount"],
            x["effectiveTime"],
        ),
        reverse=True,
    )[0]

    ofda = chosen["row"].get("openfda") or {}
    source_apps = sorted({
        re.sub(r"\s+", "", str(x or "").upper())
        for x in (ofda.get("application_number") or [])
        if str(x or "").strip()
    })
    spl_ids = sorted({
        str(x).strip()
        for x in (ofda.get("spl_set_id") or [])
        if str(x).strip()
    })
    source_url = (
        "https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid="
        + spl_ids[0]
        if spl_ids
        else None
    )

    raw_application_mismatch = bool(
        source_apps
        and input_apps
        and not set(source_apps).intersection(set(input_apps))
    )

    application_family = await _drugsfda_application_family(product)
    family_apps = list(application_family.get("applicationNumbers") or [])

    family_reconciled = (
        raw_application_mismatch
        and _application_family_reconciles(
            list(input_apps),
            list(source_apps),
            family_apps,
        )
    )

    application_mismatch = (
        raw_application_mismatch
        and not family_reconciled
    )

    # Different FDA application numbers can legitimately belong to one exact
    # brand + active-ingredient family (e.g. SUTENT approvals submitted under
    # separate NDAs). Accept only when Drugs@FDA independently confirms both
    # the catalogue and label application inside that same strict ingredient
    # family. Otherwise fail closed.
    if application_mismatch:
        status = "Application Mismatch"
        confidence = "Low"
    else:
        status = "Ambiguous" if ambiguous else "Matched"
        confidence = "Medium" if ambiguous else "High"

    print(
        "US_BASELINE_OPENFDA_BRAND_MATCH "
        + json.dumps(
            {
                "recordId": product.recordId,
                "name": product.name,
                "status": status,
                "inputApps": sorted(set(input_apps)),
                "sourceApps": source_apps,
                "applicationMismatch": application_mismatch,
                "applicationFamilyReconciled": family_reconciled,
                "applicationFamily": family_apps,
                "splSetIds": spl_ids,
                "effectiveTime": chosen["effectiveTime"],
            },
            separators=(",", ":"),
        ),
        flush=True,
    )

    return {
        "recordId": product.recordId,
        "sourceName": product.name,
        "status": status,
        "confidence": confidence,
        "applicationNumbers": sorted(set(input_apps)),
        "splSetIds": spl_ids,
        "activeIngredients": sorted({
            str(x).strip()
            for x in (
                list(product.activeIngredients or [])
                + list(ofda.get("generic_name") or [])
                + list(ofda.get("substance_name") or [])
            )
            if str(x).strip()
        }),
        "indicationText": chosen["indicationText"],
        "sourceUrl": source_url,
        "authority": "FDA / DailyMed SPL",
        "effectiveTime": chosen["effectiveTime"] or None,
        "ambiguous": ambiguous,
        "diagnostics": {
            "fallbackRoute": "OPENFDA_BRAND_INGREDIENT_CURRENT",
            "candidateBrands": brands,
            "inputApplicationNumbers": sorted(set(input_apps)),
            "sourceApplicationNumbers": source_apps,
            "applicationMismatch": application_mismatch,
            "applicationFamilyReconciled": family_reconciled,
            "applicationFamily": family_apps,
            "applicationFamilyVariants": application_family.get("variants") or [],
            "applicationFamilyRejectedVariants": application_family.get("rejectedVariants") or [],
            "ingredientCompatibility": chosen["ingredientCompatibility"],
            "bestSponsorScore": best_sponsor_score,
            "distinctIndicationStatements": len(distinct),
            "brandRowsConsidered": len(rows),
        },
    }


def _extract_active_ingredients_from_spl_xml(xml_text: str) -> List[str]:
    try:
        root = ET.fromstring(str(xml_text or ""))
    except Exception:
        return []

    out: List[str] = []
    seen = set()

    for ingredient in root.iter():
        if _xml_local(ingredient.tag) != "ingredient":
            continue
        class_code = str(ingredient.attrib.get("classCode") or "").upper()
        if class_code and class_code != "ACTIB":
            continue

        for descendant in ingredient.iter():
            if _xml_local(descendant.tag) != "name":
                continue
            value = re.sub(
                r"\s+",
                " ",
                " ".join(
                    str(x).strip()
                    for x in descendant.itertext()
                    if str(x).strip()
                ),
            ).strip()
            n = _norm(value)
            if value and n and n not in seen:
                seen.add(n)
                out.append(value)

    return out


async def _resolve_dailymed_brand_product(
    product: BaselineProductInput,
    input_apps: List[str],
) -> Dict[str, Any]:
    brands = _brand_candidates(product.name)
    candidates_by_setid: Dict[str, Dict[str, Any]] = {}

    for brand in brands[:3]:
        try:
            rows = await _daily_spls_by_brand(brand)
        except Exception:
            continue

        for row in rows:
            setid = str(row.get("setid") or "").strip()
            title = str(row.get("title") or "").strip()
            if not setid or not title:
                continue
            if not _brand_matches(title, brands):
                continue
            candidates_by_setid[setid] = row

    if not candidates_by_setid:
        return {
            "recordId": product.recordId,
            "sourceName": product.name,
            "status": "Not Found",
            "confidence": "Low",
            "applicationNumbers": sorted(set(input_apps)),
            "splSetIds": [],
            "activeIngredients": product.activeIngredients,
            "indicationText": "",
            "sourceUrl": None,
            "authority": "DailyMed SPL API",
            "ambiguous": False,
            "diagnostics": {
                "fallbackRoute": "DAILYMED_BRAND_INGREDIENT_NONE",
                "candidateBrands": brands,
            },
        }

    selected = sorted(
        candidates_by_setid.values(),
        key=lambda x: _parse_daily_date(x.get("published_date")),
        reverse=True,
    )[:15]

    fetched = await asyncio.gather(
        *[
            _dailymed_xml_get(str(row.get("setid") or "").strip())
            for row in selected
        ],
        return_exceptions=True,
    )

    compatible = []
    diagnostic_rows = []

    for row, xml_value in zip(selected, fetched):
        if isinstance(xml_value, Exception):
            continue

        xml_text = str(xml_value or "")
        setid = str(row.get("setid") or "").strip()
        title = str(row.get("title") or "").strip()
        if not xml_text:
            continue

        label_ingredients = _extract_active_ingredients_from_spl_xml(xml_text)
        # Title is also a useful source for older SPLs where ACTIB markup is
        # incomplete.
        label_ingredients.append(title)

        compatibility = _ingredient_compatibility(
            list(product.activeIngredients or []),
            label_ingredients,
        )
        indication_text = _extract_indications_from_spl_xml(xml_text)
        source_apps = _dailymed_application_candidates(
            _extract_application_numbers_from_spl_xml(xml_text)
        )

        diagnostic_rows.append({
            "setid": setid,
            "title": title,
            "publishedDate": str(row.get("published_date") or ""),
            "sourceApplicationNumbers": source_apps,
            "activeIngredients": label_ingredients[:20],
            "ingredientCompatibility": compatibility,
            "hasIndicationText": bool(indication_text),
        })

        if not indication_text:
            continue

        product_count = int(compatibility["productCount"] or 0)
        matched_count = int(compatibility["matchedCount"] or 0)
        min_required = 1 if product_count <= 2 else max(2, (product_count + 1) // 2)
        if matched_count < min_required:
            continue

        compatible.append({
            "setid": setid,
            "title": title,
            "publishedDate": str(row.get("published_date") or ""),
            "publishedTimestamp": _parse_daily_date(row.get("published_date")),
            "indicationText": indication_text,
            "normalizedIndicationText": _norm(indication_text),
            "sourceApplicationNumbers": source_apps,
            "activeIngredients": label_ingredients,
            "ingredientCompatibility": compatibility,
        })

    if not compatible:
        return {
            "recordId": product.recordId,
            "sourceName": product.name,
            "status": "Not Found",
            "confidence": "Low",
            "applicationNumbers": sorted(set(input_apps)),
            "splSetIds": [],
            "activeIngredients": product.activeIngredients,
            "indicationText": "",
            "sourceUrl": None,
            "authority": "DailyMed SPL API",
            "ambiguous": False,
            "diagnostics": {
                "fallbackRoute": "DAILYMED_BRAND_INGREDIENT_NONE",
                "candidateBrands": brands,
                "candidateSplCount": len(candidates_by_setid),
                "rows": diagnostic_rows[:20],
            },
        }

    latest_timestamp = max(x["publishedTimestamp"] for x in compatible)
    latest_pool = [
        x for x in compatible
        if x["publishedTimestamp"] == latest_timestamp
    ]

    distinct: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for item in latest_pool:
        if item["normalizedIndicationText"]:
            distinct[item["normalizedIndicationText"]].append(item)

    ambiguous = len(distinct) > 1
    chosen = sorted(
        latest_pool,
        key=lambda x: (
            x["ingredientCompatibility"]["matchedCount"],
            x["publishedTimestamp"],
        ),
        reverse=True,
    )[0]

    source_apps = sorted(set(chosen["sourceApplicationNumbers"]))
    source_url = (
        "https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid="
        + chosen["setid"]
    )

    raw_application_mismatch = bool(
        source_apps
        and input_apps
        and not set(source_apps).intersection(set(input_apps))
    )

    application_family = await _drugsfda_application_family(product)
    family_apps = list(application_family.get("applicationNumbers") or [])

    family_reconciled = (
        raw_application_mismatch
        and _application_family_reconciles(
            list(input_apps),
            list(source_apps),
            family_apps,
        )
    )

    application_mismatch = (
        raw_application_mismatch
        and not family_reconciled
    )

    # Reconcile different application numbers only when Drugs@FDA confirms
    # the same strict brand + active-ingredient application family.
    if application_mismatch:
        status = "Application Mismatch"
        confidence = "Low"
    else:
        status = "Ambiguous" if ambiguous else "Matched"
        confidence = "Medium" if ambiguous else "High"

    print(
        "US_BASELINE_DAILYMED_BRAND_MATCH "
        + json.dumps(
            {
                "recordId": product.recordId,
                "name": product.name,
                "status": status,
                "inputApps": sorted(set(input_apps)),
                "sourceApps": source_apps,
                "applicationMismatch": application_mismatch,
                "applicationFamilyReconciled": family_reconciled,
                "applicationFamily": family_apps,
                "setid": chosen["setid"],
                "publishedDate": chosen["publishedDate"],
            },
            separators=(",", ":"),
        ),
        flush=True,
    )

    return {
        "recordId": product.recordId,
        "sourceName": product.name,
        "status": status,
        "confidence": confidence,
        "applicationNumbers": sorted(set(input_apps)),
        "splSetIds": [chosen["setid"]],
        "activeIngredients": sorted({
            str(x).strip()
            for x in (
                list(product.activeIngredients or [])
                + chosen["activeIngredients"]
            )
            if str(x).strip()
        }),
        "indicationText": chosen["indicationText"],
        "sourceUrl": source_url,
        "authority": "DailyMed SPL API",
        "effectiveTime": chosen["publishedDate"] or None,
        "ambiguous": ambiguous,
        "diagnostics": {
            "fallbackRoute": "DAILYMED_BRAND_INGREDIENT_CURRENT",
            "candidateBrands": brands,
            "inputApplicationNumbers": sorted(set(input_apps)),
            "sourceApplicationNumbers": source_apps,
            "applicationMismatch": application_mismatch,
            "applicationFamilyReconciled": family_reconciled,
            "applicationFamily": family_apps,
            "applicationFamilyVariants": application_family.get("variants") or [],
            "applicationFamilyRejectedVariants": application_family.get("rejectedVariants") or [],
            "ingredientCompatibility": chosen["ingredientCompatibility"],
            "candidateSplCount": len(candidates_by_setid),
            "distinctIndicationStatements": len(distinct),
        },
    }

async def _batch_label_rows(
    products: List[BaselineProductInput],
    app_candidates: Dict[str, List[str]],
) -> Dict[str, List[Dict[str, Any]]]:
    app_index: Dict[str, set[str]] = defaultdict(set)

    for product in products:
        for app in app_candidates[product.recordId]:
            app_index[app].add(product.recordId)

    unique_apps = sorted(app_index.keys())
    payloads = []

    for group in _chunks(unique_apps, 20):
        search = " OR ".join(f'openfda.application_number:"{app}"' for app in group)
        params: Dict[str, Any] = {"search": search, "limit": 1000}
        api_key = os.getenv("OPENFDA_API_KEY", "").strip()
        if api_key:
            params["api_key"] = api_key
        payloads.append(_json_get(params))

    resolved_payloads = await asyncio.gather(*payloads)
    raw: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    seen: Dict[str, set[str]] = defaultdict(set)

    for payload in resolved_payloads:
        for row in list(payload.get("results") or []):
            ofda = row.get("openfda") or {}
            row_apps = [
                re.sub(r"\s+", "", str(x or "").upper())
                for x in (ofda.get("application_number") or [])
            ]

            target_ids: set[str] = set()
            for app in row_apps:
                target_ids.update(app_index.get(app, set()))

            if not target_ids:
                continue

            marker = (
                str(row.get("id") or "")
                + "|"
                + "|".join(ofda.get("spl_set_id") or [])
                + "|"
                + str(row.get("effective_time") or "")
            )

            for record_id in target_ids:
                dedupe_key = marker + "|" + record_id
                if dedupe_key in seen[record_id]:
                    continue
                seen[record_id].add(dedupe_key)
                raw[record_id].append(row)

    return raw


def _resolve_product_label(
    product: BaselineProductInput,
    candidates: List[str],
    apps: List[str],
    rows: List[Dict[str, Any]],
) -> Dict[str, Any]:
    matched = []

    for row in rows:
        ofda = row.get("openfda") or {}
        brands = [str(x) for x in (ofda.get("brand_name") or [])]
        row_apps = [
            re.sub(r"\s+", "", str(x or "").upper())
            for x in (ofda.get("application_number") or [])
        ]

        brand_ok = any(_brand_matches(b, candidates) for b in brands)
        app_ok = any(a in set(apps) for a in row_apps)

        if brand_ok and app_ok:
            matched.append(row)

    if not matched:
        return {
            "recordId": product.recordId,
            "sourceName": product.name,
            "status": "Not Found",
            "confidence": "Low",
            "applicationNumbers": apps,
            "splSetIds": [],
            "activeIngredients": product.activeIngredients,
            "indicationText": "",
            "sourceUrl": None,
            "authority": "FDA / DailyMed SPL",
            "ambiguous": False,
            "diagnostics": {
                "candidateBrands": candidates,
                "applicationCandidates": apps,
                "sourceRowsByApplication": len(rows),
                "exactRows": 0,
            },
        }

    ranked = []
    for row in matched:
        ofda = row.get("openfda") or {}
        manufacturers = [str(x) for x in (ofda.get("manufacturer_name") or [])]
        indication_values = [str(x) for x in (row.get("indications_and_usage") or [])]
        indication_text = _canonical_indication_text(indication_values)
        effective = str(row.get("effective_time") or "")
        sponsor_score = _sponsor_score(manufacturers, product.sponsorNames)

        ranked.append({
            "row": row,
            "sponsorScore": sponsor_score,
            "effectiveTime": effective,
            "indicationText": indication_text,
            "normalizedIndicationText": _norm(indication_text),
        })

    with_text = [x for x in ranked if x["indicationText"]]
    if not with_text:
        return {
            "recordId": product.recordId,
            "sourceName": product.name,
            "status": "No Indication Text",
            "confidence": "Low",
            "applicationNumbers": apps,
            "splSetIds": sorted({
                str(v).strip()
                for x in ranked
                for v in ((x["row"].get("openfda") or {}).get("spl_set_id") or [])
                if str(v).strip()
            }),
            "activeIngredients": product.activeIngredients,
            "indicationText": "",
            "sourceUrl": None,
            "authority": "FDA / DailyMed SPL",
            "ambiguous": False,
            "diagnostics": {
                "candidateBrands": candidates,
                "applicationCandidates": apps,
                "sourceRowsByApplication": len(rows),
                "exactRows": len(matched),
                "rowsWithIndicationText": 0,
            },
        }

    best_sponsor_score = max(x["sponsorScore"] for x in with_text)
    sponsor_pool = (
        [x for x in with_text if x["sponsorScore"] == best_sponsor_score]
        if best_sponsor_score > 0
        else with_text
    )

    distinct_texts = {}
    for item in sponsor_pool:
        n = item["normalizedIndicationText"]
        if n:
            distinct_texts.setdefault(n, []).append(item)

    # A single normalized indication statement across exact application+brand rows
    # is deterministic even if multiple repackager/SPL rows exist.
    ambiguous = len(distinct_texts) > 1

    if ambiguous:
        # Select the most recent statement only for review context, but do not
        # mark it Verified.
        chosen = sorted(
            sponsor_pool,
            key=lambda x: (x["sponsorScore"], x["effectiveTime"]),
            reverse=True,
        )[0]
        status = "Ambiguous"
        confidence = "Medium"
    else:
        chosen = sorted(
            sponsor_pool,
            key=lambda x: (x["sponsorScore"], x["effectiveTime"]),
            reverse=True,
        )[0]
        status = "Matched"
        confidence = "High"

    ofda = chosen["row"].get("openfda") or {}
    spl_ids = [str(x).strip() for x in (ofda.get("spl_set_id") or []) if str(x).strip()]
    primary_spl = spl_ids[0] if spl_ids else None
    source_url = (
        f"https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid={primary_spl}"
        if primary_spl
        else None
    )

    active = sorted({
        str(x).strip()
        for x in (
            list(product.activeIngredients or [])
            + list(ofda.get("generic_name") or [])
            + list(ofda.get("substance_name") or [])
        )
        if str(x).strip()
    })

    return {
        "recordId": product.recordId,
        "sourceName": product.name,
        "status": status,
        "confidence": confidence,
        "applicationNumbers": sorted(set(apps)),
        "splSetIds": sorted(set(spl_ids)),
        "activeIngredients": active,
        "indicationText": chosen["indicationText"],
        "sourceUrl": source_url,
        "authority": "FDA / DailyMed SPL",
        "effectiveTime": chosen["effectiveTime"] or None,
        "ambiguous": ambiguous,
        "diagnostics": {
            "candidateBrands": candidates,
            "applicationCandidates": apps,
            "sourceRowsByApplication": len(rows),
            "exactRows": len(matched),
            "rowsWithIndicationText": len(with_text),
            "bestSponsorScore": best_sponsor_score,
            "distinctIndicationStatements": len(distinct_texts),
            "matchedBrandNames": sorted({
                str(v).strip()
                for x in matched
                for v in ((x.get("openfda") or {}).get("brand_name") or [])
                if str(v).strip()
            }),
            "manufacturers": sorted({
                str(v).strip()
                for x in matched
                for v in ((x.get("openfda") or {}).get("manufacturer_name") or [])
                if str(v).strip()
            }),
        },
    }



def _numeric_application_numbers(values: List[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for value in values:
        token = re.sub(r"\s+", "", str(value or "").upper()).strip()
        m = re.fullmatch(r"(?:NDA|ANDA|BLA)?(\d{5,6})", token)
        if not m:
            continue
        applno = m.group(1)
        if applno not in seen:
            seen.add(applno)
            out.append(applno)
    return out[:20]


def _fda_label_rank(url: str) -> tuple[int, int, str]:
    text = str(url or "")
    year_match = re.search(r"/label/(\d{4})/", text, flags=re.I)
    year = int(year_match.group(1)) if year_match else 0
    supp_match = re.search(r"s(\d+)[a-z]*lbl\.pdf", text, flags=re.I)
    supp = int(supp_match.group(1)) if supp_match else -1
    return (year, supp, text)


def _extract_fda_label_links(html: str) -> List[str]:
    raw = unescape(str(html or ""))
    found: List[str] = []
    seen = set()

    patterns = [
        r'https?://www\.accessdata\.fda\.gov/drugsatfda_docs/label/\d{4}/[^"\'<>\s]+?\.pdf',
        r'/drugsatfda_docs/label/\d{4}/[^"\'<>\s]+?\.pdf',
    ]

    for pattern in patterns:
        for match in re.finditer(pattern, raw, flags=re.I):
            url = match.group(0)
            if url.startswith("/"):
                url = "https://www.accessdata.fda.gov" + url
            url = url.replace("&amp;", "&")
            key = url.lower()
            if key in seen:
                continue
            seen.add(key)
            found.append(url)

    found.sort(key=_fda_label_rank, reverse=True)
    return found


async def _resolve_fda_application_label(
    product: BaselineProductInput,
    openfda_apps: List[str],
) -> Dict[str, Any]:
    """
    Official application-level fallback using Drugs@FDA.

    For every exact application captured upstream, fetch the Drugs@FDA
    application overview, verify brand + ingredient family on that page, then
    use the newest FDA-hosted label PDF listed for the application.

    If multiple current application labels produce materially different
    indication sections, fail closed as Ambiguous rather than merging them.
    """
    app_numbers = _numeric_application_numbers(
        list(product.applicationNumbers or []) + list(openfda_apps or [])
    )
    brand_candidates = _brand_candidates(product.name)
    ingredient_norms = {
        _norm(x)
        for x in (product.activeIngredients or [])
        if _norm(x)
    }

    resolved: List[Dict[str, Any]] = []
    overview_diagnostics: List[Dict[str, Any]] = []

    for applno in app_numbers:
        overview_url = FDA_APPLICATION_OVERVIEW_URL.format(applno=applno)

        try:
            status, _ctype, html = await _text_get(
                overview_url,
                timeout_seconds=30.0,
            )
        except Exception as exc:
            overview_diagnostics.append({
                "applicationNumber": applno,
                "status": "ERROR",
                "error": f"{type(exc).__name__}: {str(exc)[:300]}",
            })
            continue

        if status != 200 or not html:
            overview_diagnostics.append({
                "applicationNumber": applno,
                "status": f"HTTP_{status}",
            })
            continue

        page_text = _strip_html(html)
        page_norm = _norm(page_text)

        brand_ok = any(
            _norm(candidate) and _norm(candidate) in page_norm
            for candidate in brand_candidates
        )

        ingredient_ok = (
            not ingredient_norms
            or any(
                ingredient in page_norm
                for ingredient in ingredient_norms
            )
        )

        label_links = _extract_fda_label_links(html)

        overview_diagnostics.append({
            "applicationNumber": applno,
            "brandVerified": brand_ok,
            "ingredientVerified": ingredient_ok,
            "labelLinkCount": len(label_links),
            "newestLabel": label_links[0] if label_links else None,
        })

        if not brand_ok or not ingredient_ok or not label_links:
            continue

        # The Drugs@FDA page is newest-first; inspect a small bounded set in
        # case the newest link is a patient insert rather than full PI.
        for label_url in label_links[:3]:
            try:
                label_status, label_ctype, content = await _bytes_get(
                    label_url,
                    timeout_seconds=40.0,
                )
            except Exception:
                continue

            if label_status != 200 or not content:
                continue

            if content.startswith(b"%PDF") or "pdf" in label_ctype.lower():
                label_text = _extract_pdf_text(content)
            else:
                label_text = _strip_html(
                    content.decode("utf-8", errors="ignore")
                )

            if not label_text:
                continue

            head_norm = _norm(label_text[:9000])
            if not any(
                _norm(candidate) and _norm(candidate) in head_norm
                for candidate in brand_candidates
            ):
                continue

            indication_text = _extract_current_indications(label_text)
            if not indication_text:
                continue

            resolved.append({
                "applicationNumber": applno,
                "labelUrl": label_url,
                "indicationText": indication_text,
                "normalizedIndicationText": _norm(indication_text),
                "rank": _fda_label_rank(label_url),
            })
            break

    if not resolved:
        return {
            "recordId": product.recordId,
            "sourceName": product.name,
            "status": "Not Found",
            "confidence": "Low",
            "applicationNumbers": sorted(set(openfda_apps)),
            "splSetIds": [],
            "activeIngredients": product.activeIngredients,
            "indicationText": "",
            "sourceUrl": None,
            "authority": "FDA Drugs@FDA Current Label",
            "ambiguous": False,
            "diagnostics": {
                "fallbackRoute": "FDA_APPLICATION_LABEL_NONE",
                "applicationsChecked": app_numbers,
                "overviews": overview_diagnostics,
            },
        }

    # Keep the newest label per application first.
    by_app: Dict[str, Dict[str, Any]] = {}
    for item in sorted(
        resolved,
        key=lambda x: x["rank"],
        reverse=True,
    ):
        by_app.setdefault(item["applicationNumber"], item)

    current_rows = list(by_app.values())
    distinct: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for item in current_rows:
        distinct[item["normalizedIndicationText"]].append(item)

    ambiguous = len(distinct) > 1
    chosen = sorted(
        current_rows,
        key=lambda x: x["rank"],
        reverse=True,
    )[0]

    print(
        "US_BASELINE_FDA_APPLICATION_LABEL "
        + json.dumps(
            {
                "recordId": product.recordId,
                "name": product.name,
                "applications": sorted(by_app.keys()),
                "chosenLabel": chosen["labelUrl"],
                "ambiguous": ambiguous,
                "distinctIndicationStatements": len(distinct),
            },
            separators=(",", ":"),
        ),
        flush=True,
    )

    return {
        "recordId": product.recordId,
        "sourceName": product.name,
        "status": "Ambiguous" if ambiguous else "Matched",
        "confidence": "Medium" if ambiguous else "High",
        "applicationNumbers": sorted(by_app.keys()),
        "splSetIds": [],
        "activeIngredients": product.activeIngredients,
        "indicationText": chosen["indicationText"],
        "sourceUrl": chosen["labelUrl"],
        "authority": "FDA Drugs@FDA Current Label",
        "ambiguous": ambiguous,
        "diagnostics": {
            "fallbackRoute": "FDA_APPLICATION_CURRENT_LABEL",
            "applicationsChecked": app_numbers,
            "currentLabels": [
                {
                    "applicationNumber": x["applicationNumber"],
                    "labelUrl": x["labelUrl"],
                }
                for x in current_rows
            ],
            "distinctIndicationStatements": len(distinct),
            "overviews": overview_diagnostics,
        },
    }

async def _build_result(payload: BaselineEvidenceRequest) -> Dict[str, Any]:
    products = payload.products
    brand_candidates = {p.recordId: _brand_candidates(p.name) for p in products}
    app_candidates = {
        p.recordId: _application_candidates(p.applicationNumbers)
        for p in products
    }

    raw = await _batch_label_rows(products, app_candidates)

    rows = [
        _resolve_product_label(
            product,
            brand_candidates[product.recordId],
            app_candidates[product.recordId],
            raw.get(product.recordId, []),
        )
        for product in products
    ]

    # Current openFDA SPL fallback by exact brand + active ingredient.
    # This deliberately does not require the input application number because
    # one marketed brand can span multiple related NDA/BLA applications, while
    # the current SPL may expose only one of them (e.g. SUTENT).
    brand_fallback_indexes = [
        i for i, row in enumerate(rows)
        if row.get("status") in {"Not Found", "No Indication Text"}
    ]

    if brand_fallback_indexes:
        brand_fallback_results = await asyncio.gather(
            *[
                _resolve_openfda_brand_product(
                    products[i],
                    app_candidates[products[i].recordId],
                )
                for i in brand_fallback_indexes
            ],
            return_exceptions=True,
        )

        for i, fallback in zip(
            brand_fallback_indexes,
            brand_fallback_results,
        ):
            if isinstance(fallback, Exception):
                rows[i].setdefault("diagnostics", {})[
                    "openFdaBrandFallbackError"
                ] = f"{type(fallback).__name__}: {str(fallback)[:500]}"
                continue

            rows[i].setdefault("diagnostics", {})[
                "openFdaBrandFallback"
            ] = fallback.get("diagnostics") or {}

            if fallback.get("status") in {"Matched", "Ambiguous"}:
                rows[i] = fallback

    # Official DailyMed API fallback for products still absent from openFDA.
    fallback_indexes = [
        i for i, row in enumerate(rows)
        if row.get("status") in {"Not Found", "No Indication Text"}
    ]

    if fallback_indexes:
        fallback_results = await asyncio.gather(
            *[
                _resolve_dailymed_product(
                    products[i],
                    brand_candidates[products[i].recordId],
                    app_candidates[products[i].recordId],
                )
                for i in fallback_indexes
            ],
            return_exceptions=True,
        )

        for i, fallback in zip(fallback_indexes, fallback_results):
            if isinstance(fallback, Exception):
                rows[i].setdefault("diagnostics", {})["dailyMedFallbackError"] = (
                    f"{type(fallback).__name__}: {str(fallback)[:500]}"
                )
                continue

            rows[i].setdefault("diagnostics", {})["dailyMedFallback"] = (
                fallback.get("diagnostics") or {}
            )

            if fallback.get("status") in {"Matched", "Ambiguous"}:
                rows[i] = fallback

    # Current DailyMed brand + active-ingredient fallback. This is official,
    # company-agnostic, and handles brands whose current SPL exposes a related
    # application number rather than the application captured upstream.
    current_brand_indexes = [
        i for i, row in enumerate(rows)
        if row.get("status") in {"Not Found", "No Indication Text"}
    ]

    if current_brand_indexes:
        current_brand_results = await asyncio.gather(
            *[
                _resolve_dailymed_brand_product(
                    products[i],
                    app_candidates[products[i].recordId],
                )
                for i in current_brand_indexes
            ],
            return_exceptions=True,
        )

        for i, fallback in zip(
            current_brand_indexes,
            current_brand_results,
        ):
            if isinstance(fallback, Exception):
                rows[i].setdefault("diagnostics", {})[
                    "dailyMedBrandFallbackError"
                ] = f"{type(fallback).__name__}: {str(fallback)[:500]}"
                continue

            rows[i].setdefault("diagnostics", {})[
                "dailyMedBrandFallback"
            ] = fallback.get("diagnostics") or {}

            if fallback.get("status") in {"Matched", "Ambiguous"}:
                rows[i] = fallback

    # Official Drugs@FDA application-page fallback. This is company-agnostic
    # and resolves brands that have no usable openFDA/DailyMed SPL while FDA
    # still publishes a current application-level label PDF.
    application_fallback_indexes = [
        i for i, row in enumerate(rows)
        if row.get("status") in {"Not Found", "No Indication Text"}
    ]

    if application_fallback_indexes:
        application_fallback_results = await asyncio.gather(
            *[
                _resolve_fda_application_label(
                    products[i],
                    app_candidates[products[i].recordId],
                )
                for i in application_fallback_indexes
            ],
            return_exceptions=True,
        )

        for i, fallback in zip(
            application_fallback_indexes,
            application_fallback_results,
        ):
            if isinstance(fallback, Exception):
                rows[i].setdefault("diagnostics", {})[
                    "fdaApplicationLabelFallbackError"
                ] = f"{type(fallback).__name__}: {str(fallback)[:500]}"
                continue

            rows[i].setdefault("diagnostics", {})[
                "fdaApplicationLabelFallback"
            ] = fallback.get("diagnostics") or {}

            if fallback.get("status") in {"Matched", "Ambiguous"}:
                rows[i] = fallback

    # Pfizer portal fallback remains disabled for automated runs because the
    # public labeling portal does not currently expose a searchable form to
    # the browser worker. Drugs@FDA is now the scalable fallback instead.
    counts: Dict[str, int] = defaultdict(int)
    for row in rows:
        counts[row["status"]] += 1

    return {
        "version": VERSION,
        "companyName": payload.companyName,
        "rows": rows,
        "summary": {
            "inputCount": len(products),
            "statusCounts": dict(counts),
            "portfolioWrites": 0,
            "queueWrites": 0,
            "controlledIndicationWrites": 0,
        },
    }


def _request_key(payload: BaselineEvidenceRequest) -> str:
    normalized = {
        "companyName": str(payload.companyName or "").strip(),
        "products": sorted(
            [
                {
                    "recordId": p.recordId,
                    "name": p.name,
                    "applicationNumbers": sorted(p.applicationNumbers),
                    "sponsorNames": sorted(p.sponsorNames),
                    "activeIngredients": sorted(p.activeIngredients),
                }
                for p in payload.products
            ],
            key=lambda x: x["recordId"],
        ),
    }
    raw = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _prune_jobs() -> None:
    cutoff = time.time() - JOB_TTL_SECONDS
    with _jobs_lock:
        stale = [
            job_id
            for job_id, job in list(_jobs.items())
            if float(job.get("updatedAt") or job.get("createdAt") or 0) < cutoff
        ]
        for job_id in stale:
            job = _jobs.pop(job_id, None) or {}
            key = str(job.get("requestKey") or "")
            if key and _job_key_index.get(key) == job_id:
                _job_key_index.pop(key, None)


async def _run_job(job_id: str, payload: BaselineEvidenceRequest) -> None:
    started = time.time()
    try:
        with _jobs_lock:
            if job_id not in _jobs:
                return
            _jobs[job_id].update({"status": "running", "updatedAt": time.time()})

        result = await _build_result(payload)

        with _jobs_lock:
            if job_id not in _jobs:
                return
            _jobs[job_id].update({
                "status": "complete",
                "updatedAt": time.time(),
                "result": result,
            })

        print(
            "US_BASELINE_EVIDENCE_JOB_COMPLETE "
            + json.dumps(
                {
                    "jobId": job_id,
                    "inputCount": len(payload.products),
                    "durationSeconds": round(time.time() - started, 2),
                    "statusCounts": (result.get("summary") or {}).get("statusCounts"),
                },
                separators=(",", ":"),
            ),
            flush=True,
        )
    except Exception as exc:
        with _jobs_lock:
            if job_id in _jobs:
                _jobs[job_id].update({
                    "status": "error",
                    "updatedAt": time.time(),
                    "error": f"{type(exc).__name__}: {str(exc)[:1200]}",
                })
        print(
            "US_BASELINE_EVIDENCE_JOB_ERROR "
            + json.dumps(
                {
                    "jobId": job_id,
                    "error": f"{type(exc).__name__}: {str(exc)[:500]}",
                },
                separators=(",", ":"),
            ),
            flush=True,
        )


def _run_job_thread(job_id: str, payload_dict: Dict[str, Any]) -> None:
    payload = BaselineEvidenceRequest(**payload_dict)
    asyncio.run(_run_job(job_id, payload))


@app.post("/marketed/us-baseline-evidence/jobs")
async def create_baseline_evidence_job(
    payload: BaselineEvidenceRequest,
    x_adapter_key: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    _auth(x_adapter_key)
    _prune_jobs()

    request_key = _request_key(payload)
    now = time.time()

    with _jobs_lock:
        existing_id = _job_key_index.get(request_key)
        existing = _jobs.get(existing_id) if existing_id else None
        if existing and existing.get("status") in {"queued", "running", "complete"}:
            return {
                "version": VERSION,
                "jobId": existing_id,
                "status": existing.get("status"),
                "inputCount": existing.get("inputCount"),
                "writeMode": "READ_ONLY",
                "reused": True,
            }

        job_id = "usbe_" + uuid.uuid4().hex
        _jobs[job_id] = {
            "jobId": job_id,
            "requestKey": request_key,
            "status": "queued",
            "createdAt": now,
            "updatedAt": now,
            "inputCount": len(payload.products),
            "companyName": payload.companyName,
        }
        _job_key_index[request_key] = job_id

    task = asyncio.create_task(
        asyncio.to_thread(_run_job_thread, job_id, payload.model_dump())
    )
    _job_tasks.add(task)
    task.add_done_callback(_job_tasks.discard)

    return {
        "version": VERSION,
        "jobId": job_id,
        "status": "queued",
        "inputCount": len(payload.products),
        "writeMode": "READ_ONLY",
        "reused": False,
    }


@app.get("/marketed/us-baseline-evidence/jobs/{job_id}/wait")
async def wait_baseline_evidence_job(
    job_id: str,
    x_adapter_key: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    _auth(x_adapter_key)
    _prune_jobs()

    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Baseline evidence job not found")

    deadline = time.monotonic() + 6.0
    while job.get("status") in {"queued", "running"} and time.monotonic() < deadline:
        await asyncio.sleep(0.5)
        job = _jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Baseline evidence job not found")

    response = {
        "version": VERSION,
        "jobId": job_id,
        "status": job.get("status"),
        "inputCount": job.get("inputCount"),
        "companyName": job.get("companyName"),
    }

    if job.get("status") == "complete":
        result = job.get("result") or {}
        response["resultSummary"] = result.get("summary") or {}
        response["resultRowCount"] = len(result.get("rows") or [])
        response["resultVersion"] = result.get("version")

    if job.get("status") == "error":
        response["error"] = job.get("error")

    return response


@app.get("/marketed/us-baseline-evidence/jobs/{job_id}/result")
async def baseline_evidence_result(
    job_id: str,
    offset: int = 0,
    limit: int = 25,
    x_adapter_key: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    _auth(x_adapter_key)
    _prune_jobs()

    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Baseline evidence job not found")
    if job.get("status") != "complete":
        raise HTTPException(status_code=409, detail="Baseline evidence job is not complete")
    if offset < 0 or limit < 1 or limit > 25:
        raise HTTPException(status_code=400, detail="offset must be >=0 and limit must be 1..25")

    result = job.get("result") or {}
    rows = list(result.get("rows") or [])
    page = rows[offset:offset + limit]

    return {
        "version": VERSION,
        "jobId": job_id,
        "status": "complete",
        "resultVersion": result.get("version"),
        "summary": result.get("summary") or {},
        "offset": offset,
        "limit": limit,
        "totalRows": len(rows),
        "rows": page,
        "nextOffset": (offset + limit) if (offset + limit) < len(rows) else None,
    }


@app.get("/marketed/us-baseline-evidence/health")
async def baseline_evidence_health() -> Dict[str, Any]:
    return {
        "ok": True,
        "version": VERSION,
        "writeMode": "READ_ONLY",
        "source": "openFDA application + current brand/ingredient SPL + DailyMed current-brand fallback",
        "maxProductsPerRequest": MAX_PRODUCTS,
    }
