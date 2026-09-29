"""Read-only U.S. marketed-product identity enrichment.

Batch-matches source-listed marketed products against:
- openFDA Drugs@FDA
- openFDA drug labeling / SPL harmonization
- DailyMed SPL REST service (bounded fallback)
- FDA Purple Book current monthly download (best-effort biologic identity)

No Airtable or master-data writes occur in this service.
"""

from __future__ import annotations

import asyncio
import csv
import hashlib
import io
import json
import os
import re
import time
import uuid
import threading
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional

import httpx
from fastapi import Header, HTTPException
from pydantic import BaseModel, Field

from main import _auth, app


VERSION = "US_MARKETED_IDENTITY_V1.12_COMPLETE_BRAND_FAMILY"
MAX_PRODUCTS = 400
OPENFDA_BASE = "https://api.fda.gov"
DAILYMED_SPLS = "https://dailymed.nlm.nih.gov/dailymed/services/v2/spls.json"
PURPLE_DOWNLOADS = "https://www.accessdata.fda.gov/scripts/purplebooksearch/index.cfm?event=downloads"
CACHE_TTL = 86400.0

_http_cache: Dict[str, tuple[float, Any]] = {}
_purple_cache: Dict[str, Any] = {"ts": 0.0, "rows": [], "sourceUrl": None, "error": None}
_loop_semaphores: Dict[int, asyncio.Semaphore] = {}

def _get_loop_semaphore() -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    key = id(loop)
    sem = _loop_semaphores.get(key)
    if sem is None:
        sem = asyncio.Semaphore(10)
        _loop_semaphores[key] = sem
    return sem
_jobs: Dict[str, Dict[str, Any]] = {}
_job_key_index: Dict[str, str] = {}
_jobs_lock = threading.Lock()
_job_tasks: set[asyncio.Task] = set()
JOB_TTL_SECONDS = 7200.0


class ProductInput(BaseModel):
    recordId: str = Field(min_length=3)
    name: str = Field(min_length=1, max_length=500)
    molecule: Optional[str] = Field(default=None, max_length=500)


class EnrichmentRequest(BaseModel):
    companyName: Optional[str] = Field(default=None, max_length=300)
    products: List[ProductInput] = Field(min_length=1, max_length=MAX_PRODUCTS)


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

    for match in re.finditer(r"([A-Za-z0-9][A-Za-z0-9-]{2,})\s*[®™]", str(raw or "")):
        values.append(match.group(1))

    if cleaned:
        first = cleaned.split()[0]
        if len(first) >= 4:
            values.append(first)

    out: List[str] = []
    seen = set()
    stop = {"for", "and", "the", "injection", "tablet", "tablets", "capsule", "capsules"}
    for value in values:
        n = _norm(value)
        if not n or n in stop or len(n) < 3 or n in seen:
            continue
        seen.add(n)
        out.append(value)
    return out[:5]


def _chunks(values: List[Any], size: int) -> Iterable[List[Any]]:
    for i in range(0, len(values), size):
        yield values[i:i + size]


def _candidate_matches(value: Any, candidates: List[str]) -> bool:
    nv = _norm(value)
    if not nv:
        return False
    for candidate in candidates:
        nc = _norm(candidate)
        if nv == nc or nv.startswith(nc + " ") or nc.startswith(nv + " "):
            return True
    return False


async def _json_get(url: str, params: Optional[Dict[str, Any]] = None, timeout_seconds: float = 20.0) -> Any:
    key = url + "?" + "&".join(f"{k}={params[k]}" for k in sorted(params or {}))
    now = time.time()
    cached = _http_cache.get(key)
    if cached and now - cached[0] < CACHE_TTL:
        return cached[1]

    headers = {
        "User-Agent": "PharmaCommercialIntelligence/1.2 (+read-only official-source identity)",
        "Accept": "application/json",
    }
    async with _get_loop_semaphore():
        timeout = httpx.Timeout(timeout_seconds, connect=min(8.0, timeout_seconds))
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers=headers) as client:
            response = await client.get(url, params=params)

    if response.status_code == 404:
        payload = {"results": [], "meta": {"results": {"total": 0}}}
        _http_cache[key] = (now, payload)
        return payload
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"Upstream GET failed {response.status_code}: {url}")

    try:
        payload = response.json()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Upstream returned invalid JSON: {url}") from exc

    _http_cache[key] = (now, payload)
    return payload


async def _openfda(path: str, search: str, limit: int) -> Dict[str, Any]:
    params: Dict[str, Any] = {"search": search, "limit": limit}
    key = os.getenv("OPENFDA_API_KEY", "").strip()
    if key:
        params["api_key"] = key
    return await _json_get(f"{OPENFDA_BASE}{path}", params=params)


def _query_terms(products: List[ProductInput], candidates: Dict[str, List[str]]) -> List[str]:
    terms: List[str] = []
    seen = set()
    for p in products:
        for candidate in candidates[p.recordId][:1]:
            n = _norm(candidate)
            if not n or n in seen:
                continue
            seen.add(n)
            terms.append(candidate.replace('"', "").strip())
    return terms



def _molecule_components(value: Any) -> List[str]:
    raw = str(value or "")
    parts = re.split(r"\s+\+\s+|[\n;]+", raw)
    out: List[str] = []
    seen = set()
    for part in parts:
        n = _norm(part)
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out


def _source_ingredient_set(values: Iterable[Any]) -> set[str]:
    return {
        _norm(v)
        for v in values
        if _norm(v)
    }


def _exact_ingredient_family_match(
    product_molecule: Any,
    source_values: Iterable[Any],
) -> bool:
    """
    Application-family guard.

    FDA applications under the same brand are treated as one marketed family
    only when the catalogue molecule components are present exactly in the
    source active-ingredient identity. This intentionally distinguishes, for
    example, methylprednisolone acetate from methylprednisolone and different
    CORTISPORIN formulations.
    """
    product_components = _molecule_components(product_molecule)
    if not product_components:
        return True

    source = _source_ingredient_set(source_values)
    if not source:
        return False

    return all(component in source for component in product_components)


def _compatible_family_row_indexes(
    product_molecule: Any,
    ingredient_rows: List[List[str]],
) -> tuple[List[int], str]:
    """
    Decide which exact-brand FDA application rows belong to one catalogue
    product family.

    1. Prefer strict fixed-combination identity: every catalogue molecule
       component appears in the same FDA product row.
    2. If no row contains all components, allow an alternate-formulation
       family only when the union of clean exact-brand rows covers every
       catalogue component and each accepted row contains no off-family active
       ingredient. This handles brands such as VIBRAMYCIN where catalogue
       identity spans calcium/hyclate formulations without weakening
       fixed-combination products such as CORTISPORIN.
    """
    components = set(_molecule_components(product_molecule))
    if not components:
        return list(range(len(ingredient_rows))), "NO_MOLECULE_GUARD"

    normalized_rows = [
        _source_ingredient_set(values)
        for values in ingredient_rows
    ]

    strict = [
        idx
        for idx, source in enumerate(normalized_rows)
        if source and components.issubset(source)
    ]
    if strict:
        return strict, "STRICT_ALL_COMPONENTS"

    if len(components) <= 1:
        return [], "NO_COMPATIBLE_ROW"

    clean_subset_indexes = [
        idx
        for idx, source in enumerate(normalized_rows)
        if source and source.issubset(components)
    ]
    clean_union: set[str] = set()
    for idx in clean_subset_indexes:
        clean_union.update(normalized_rows[idx])

    if components.issubset(clean_union):
        return clean_subset_indexes, "ALTERNATE_FORMULATION_COMPONENTS"

    return [], "NO_COMPATIBLE_ROW"


def _empty_drugs() -> Dict[str, Any]:
    return {
        "matched": False, "applicationNumbers": [], "sponsorNames": [],
        "brandNames": [], "activeIngredients": [], "dosageForms": [],
        "marketingStatuses": [], "productTypes": [], "recordCount": 0
    }


def _empty_label() -> Dict[str, Any]:
    return {
        "matched": False, "brandNames": [], "genericNames": [],
        "manufacturerNames": [], "applicationNumbers": [], "productTypes": [],
        "routes": [], "substanceNames": [], "splSetIds": [], "recordCount": 0
    }


async def _batch_drugsfda(products: List[ProductInput], candidates: Dict[str, List[str]]) -> Dict[str, Dict[str, Any]]:
    raw: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    terms = _query_terms(products, candidates)

    # Exact normalized candidate index keeps this pass high-precision and avoids
    # O(source_rows × catalogue_products) matching on the event loop.
    candidate_index: Dict[str, set[str]] = defaultdict(set)
    candidate_sets: Dict[str, set[str]] = {}
    for product in products:
        norms = {_norm(x) for x in candidates[product.recordId] if _norm(x)}
        candidate_sets[product.recordId] = norms
        for n in norms:
            candidate_index[n].add(product.recordId)

    groups = list(_chunks(terms, 25))
    payloads = await asyncio.gather(*[
        _openfda(
            "/drug/drugsfda.json",
            " OR ".join(f'products.brand_name:"{term}"' for term in group),
            limit=99,
        )
        for group in groups
    ])

    seen_by_product: Dict[str, set[str]] = defaultdict(set)

    for payload in payloads:
        for row in list(payload.get("results") or []):
            target_ids: set[str] = set()
            for p in (row.get("products") or []):
                bn = _norm(p.get("brand_name"))
                if bn:
                    target_ids.update(candidate_index.get(bn, set()))

            if not target_ids:
                continue

            row_identity = str(row.get("application_number") or "") + "|" + str(row.get("sponsor_name") or "")
            for record_id in target_ids:
                dedupe_key = row_identity + "|" + record_id
                if dedupe_key in seen_by_product[record_id]:
                    continue
                seen_by_product[record_id].add(dedupe_key)
                raw[record_id].append(row)

    # OR-batched Drugs@FDA queries can hit the endpoint result limit when a
    # group contains prolific brands. Retry only products with no exact-brand
    # source rows using one bounded exact-brand query each.
    missing_products = [
        product
        for product in products
        if not raw.get(product.recordId)
    ]

    if missing_products:
        retry_payloads = await asyncio.gather(*[
            _openfda(
                "/drug/drugsfda.json",
                f'products.brand_name:"{candidates[product.recordId][0].replace(chr(34), "").strip()}"',
                limit=99,
            )
            for product in missing_products
            if candidates.get(product.recordId)
            and candidates[product.recordId]
        ], return_exceptions=True)

        retry_products = [
            product
            for product in missing_products
            if candidates.get(product.recordId)
            and candidates[product.recordId]
        ]

        for product, payload in zip(retry_products, retry_payloads):
            if isinstance(payload, Exception):
                continue
            allowed = candidate_sets.get(product.recordId, set())
            seen = seen_by_product[product.recordId]
            for row in list((payload or {}).get("results") or []):
                if not any(
                    _norm(p.get("brand_name")) in allowed
                    for p in (row.get("products") or [])
                ):
                    continue
                row_identity = (
                    str(row.get("application_number") or "")
                    + "|"
                    + str(row.get("sponsor_name") or "")
                )
                dedupe_key = row_identity + "|" + product.recordId
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                raw[product.recordId].append(row)

    out: Dict[str, Dict[str, Any]] = {}
    for product in products:
        rows = raw.get(product.recordId, [])
        allowed = candidate_sets.get(product.recordId, set())

        row_parts = []
        ingredient_rows: List[List[str]] = []

        for row in rows:
            exact_brand_products = [
                p for p in (row.get("products") or [])
                if _norm(p.get("brand_name")) in allowed
            ]

            row_ingredients = [
                str(ai.get("name") or "").strip()
                for p in exact_brand_products
                for ai in (p.get("active_ingredients") or [])
                if str(ai.get("name") or "").strip()
            ]
            row_parts.append((row, exact_brand_products, row_ingredients))
            ingredient_rows.append(row_ingredients)

        compatible_indexes, family_mode = _compatible_family_row_indexes(
            product.molecule,
            ingredient_rows,
        )
        compatible_index_set = set(compatible_indexes)

        compatible_rows = []
        rejected_variants = []

        for idx, (row, exact_brand_products, row_ingredients) in enumerate(row_parts):
            compatible = idx in compatible_index_set

            variant = {
                "applicationNumber": str(row.get("application_number") or "").strip(),
                "sponsorName": str(row.get("sponsor_name") or "").strip(),
                "activeIngredients": sorted(set(row_ingredients)),
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
                "ingredientFamilyMode": family_mode,
            }

            if compatible:
                compatible_rows.append((row, exact_brand_products, variant))
            else:
                rejected_variants.append(variant)

        apps = set()
        sponsors = set()
        brands = set()
        ingredients = set()
        forms = set()
        marketing = set()
        product_types = set()
        application_variants = []

        for row, exact_brand_products, variant in compatible_rows:
            application_variants.append(variant)

            if row.get("application_number"):
                apps.add(str(row["application_number"]).strip())
            if row.get("sponsor_name"):
                sponsors.add(str(row["sponsor_name"]).strip())

            for p in exact_brand_products:
                if p.get("brand_name"):
                    brands.add(str(p["brand_name"]).strip())
                if p.get("dosage_form"):
                    forms.add(str(p["dosage_form"]).strip())
                if p.get("marketing_status"):
                    marketing.add(str(p["marketing_status"]).strip())
                for ai in (p.get("active_ingredients") or []):
                    if ai.get("name"):
                        ingredients.add(str(ai["name"]).strip())

            for value in ((row.get("openfda") or {}).get("product_type") or []):
                if value:
                    product_types.add(str(value).strip())

        out[product.recordId] = {
            "matched": bool(compatible_rows),
            "applicationNumbers": sorted(apps),
            "sponsorNames": sorted(sponsors),
            "brandNames": sorted(brands),
            "activeIngredients": sorted(ingredients),
            "dosageForms": sorted(forms),
            "marketingStatuses": sorted(marketing),
            "productTypes": sorted(product_types),
            "recordCount": len(compatible_rows),
            "applicationVariants": application_variants,
            "ingredientFamilyMode": (
                application_variants[0].get("ingredientFamilyMode")
                if application_variants
                else "NO_COMPATIBLE_ROW"
            ),
            "rejectedBrandVariants": rejected_variants[:20],
        }
    return out


async def _batch_label(products: List[ProductInput], candidates: Dict[str, List[str]]) -> Dict[str, Dict[str, Any]]:
    raw: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    terms = _query_terms(products, candidates)

    candidate_index: Dict[str, set[str]] = defaultdict(set)
    for product in products:
        for candidate in candidates[product.recordId]:
            n = _norm(candidate)
            if n:
                candidate_index[n].add(product.recordId)

    groups = list(_chunks(terms, 25))
    payloads = await asyncio.gather(*[
        _openfda(
            "/drug/label.json",
            " OR ".join(f'openfda.brand_name:"{term}"' for term in group),
            limit=1000,
        )
        for group in groups
    ])

    seen_by_product: Dict[str, set[str]] = defaultdict(set)

    for payload in payloads:
        for row in list(payload.get("results") or []):
            target_ids: set[str] = set()
            ofda = row.get("openfda") or {}
            for brand in (ofda.get("brand_name") or []):
                nb = _norm(brand)
                if nb:
                    target_ids.update(candidate_index.get(nb, set()))

            if not target_ids:
                continue

            row_identity = str(row.get("id") or "") + "|" + "|".join(ofda.get("spl_set_id") or [])
            for record_id in target_ids:
                dedupe_key = row_identity + "|" + record_id
                if dedupe_key in seen_by_product[record_id]:
                    continue
                seen_by_product[record_id].add(dedupe_key)
                raw[record_id].append(row)

    out: Dict[str, Dict[str, Any]] = {}
    for product in products:
        candidate_rows = raw.get(product.recordId, [])

        ingredient_rows = []
        for row in candidate_rows:
            ofda = row.get("openfda") or {}
            ingredient_rows.append([
                str(v).strip()
                for v in (
                    list(ofda.get("substance_name") or [])
                    + list(ofda.get("generic_name") or [])
                )
                if str(v).strip()
            ])

        compatible_indexes, family_mode = _compatible_family_row_indexes(
            product.molecule,
            ingredient_rows,
        )
        compatible_index_set = set(compatible_indexes)

        rows = []
        rejected = []

        for idx, row in enumerate(candidate_rows):
            ofda = row.get("openfda") or {}
            compatible = idx in compatible_index_set

            if compatible:
                rows.append(row)
            else:
                rejected.append({
                    "applicationNumbers": [
                        str(v).strip()
                        for v in (ofda.get("application_number") or [])
                        if str(v).strip()
                    ],
                    "genericNames": [
                        str(v).strip()
                        for v in (ofda.get("generic_name") or [])
                        if str(v).strip()
                    ],
                    "substanceNames": [
                        str(v).strip()
                        for v in (ofda.get("substance_name") or [])
                        if str(v).strip()
                    ],
                    "ingredientFamilyMode": family_mode,
                })

        def collect(field: str) -> List[str]:
            return sorted({
                str(v).strip()
                for row in rows
                for v in ((row.get("openfda") or {}).get(field) or [])
                if str(v).strip()
            })

        out[product.recordId] = {
            "matched": bool(rows),
            "brandNames": collect("brand_name"),
            "genericNames": collect("generic_name"),
            "manufacturerNames": collect("manufacturer_name"),
            "applicationNumbers": collect("application_number"),
            "productTypes": collect("product_type"),
            "routes": collect("route"),
            "substanceNames": collect("substance_name"),
            "splSetIds": collect("spl_set_id"),
            "recordCount": len(rows),
            "ingredientFamilyMode": family_mode,
            "rejectedBrandVariants": rejected[:20],
        }
    return out


async def _dailymed(product: ProductInput, candidates: List[str]) -> Dict[str, Any]:
    """Bounded DailyMed residual matcher.

    Try each useful brand candidate rather than only the combined catalogue label.
    DailyMed /spls is still treated as supporting label identity rather than a
    substitute for Drugs@FDA/Purple Book regulatory identity.
    """
    attempts: List[Dict[str, str]] = []
    useful_by_setid: Dict[str, Dict[str, Any]] = {}

    search_candidates = list(candidates[:3]) or [product.name]

    for candidate in search_candidates:
        try:
            payload = await _json_get(
                DAILYMED_SPLS,
                params={
                    "drug_name": candidate,
                    "name_type": "brand",
                    "pagesize": 25,
                    "page": 1,
                },
                timeout_seconds=15.0,
            )
            attempts.append({"candidate": candidate, "nameType": "brand", "status": "OK"})
        except Exception as exc:
            attempts.append({
                "candidate": candidate,
                "nameType": "brand",
                "status": type(exc).__name__,
            })
            continue

        for row in list(payload.get("data") or []):
            title = str(row.get("title") or "").strip()
            # DailyMed titles normally begin BRAND (GENERIC) FORM [LABELER].
            # Prefix matching against the full title is safer than assuming one
            # exact punctuation layout.
            if not _candidate_matches(title, [candidate]):
                continue
            setid = str(row.get("setid") or "").strip()
            marker = setid or title
            if marker:
                useful_by_setid[marker] = row

        if useful_by_setid:
            break

    useful = list(useful_by_setid.values())

    return {
        "matched": bool(useful),
        "setIds": sorted({
            str(r.get("setid") or "").strip()
            for r in useful
            if r.get("setid")
        }),
        "titles": [
            str(r.get("title") or "").strip()
            for r in useful[:10]
        ],
        "recordCount": len(useful),
        "attempts": attempts,
    }


def _purple_row_value(row: Dict[str, str], *names: str) -> str:
    normalized = {_norm(k): str(v or "").strip() for k, v in row.items()}
    for name in names:
        value = normalized.get(_norm(name))
        if value:
            return value
    return ""


async def _purple_rows() -> Dict[str, Any]:
    now = time.time()
    if now - float(_purple_cache.get("ts") or 0) < CACHE_TTL and (_purple_cache.get("rows") or _purple_cache.get("error")):
        return _purple_cache

    headers = {"User-Agent": "PharmaCommercialIntelligence/1.2 (+read-only official-source identity)"}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(25.0, connect=8.0), follow_redirects=True, headers=headers) as client:
            page = await client.get(PURPLE_DOWNLOADS)
            page.raise_for_status()
            links = re.findall(r'href=["\']([^"\']+purplebook[^"\']+\.csv)["\']', page.text, flags=re.I)
            if not links:
                raise RuntimeError("No Purple Book CSV links found")

            current_year = str(time.gmtime().tm_year)
            current = [x for x in links if f"/{current_year}/" in x]
            chosen = (current or links)[-1]
            if chosen.startswith("/"):
                chosen = "https://www.accessdata.fda.gov" + chosen
            elif not chosen.startswith("http"):
                chosen = "https://www.accessdata.fda.gov/" + chosen.lstrip("/")

            response = await client.get(chosen)
            response.raise_for_status()
            text = response.content.decode("utf-8-sig", errors="replace")

        lines = text.splitlines()
        header_idx = None
        for idx, line in enumerate(lines[:100]):
            low = line.lower()
            if "proprietary name" in low and ("bla" in low or "proper name" in low):
                header_idx = idx
                break
        if header_idx is None:
            raise RuntimeError("Purple Book header not found")

        reader = csv.DictReader(io.StringIO("\n".join(lines[header_idx:])))
        rows = [dict(r) for r in reader if any(str(v or "").strip() for v in r.values())]
        _purple_cache.update({"ts": now, "rows": rows, "sourceUrl": chosen, "error": None})
    except Exception as exc:
        _purple_cache.update({"ts": now, "rows": [], "sourceUrl": None, "error": type(exc).__name__})

    return _purple_cache


def _purple_match(
    rows: List[Dict[str, str]],
    candidates: List[str],
    reference_names: Optional[set[str]] = None,
) -> Dict[str, Any]:
    matches = []
    for row in rows:
        proprietary = _purple_row_value(row, "Proprietary Name")
        if proprietary and _candidate_matches(proprietary, candidates):
            matches.append(row)

    # IMPORTANT: "Licensure" in the monthly CSV can contain values such as
    # "Licensed".  The legal pathway is in "License Type" (e.g. 351(a),
    # 351(k) Biosimilar, 351(k) Interchangeable), so it must be read first.
    license_types = sorted({
        _purple_row_value(r, "License Type", "Submission Type")
        for r in matches
        if _purple_row_value(r, "License Type", "Submission Type")
    })
    licensures = sorted({
        _purple_row_value(r, "Licensure")
        for r in matches
        if _purple_row_value(r, "Licensure")
    })
    proper_names = sorted({
        _purple_row_value(r, "Proper Name")
        for r in matches if _purple_row_value(r, "Proper Name")
    })
    proprietary_names = sorted({
        _purple_row_value(r, "Proprietary Name")
        for r in matches if _purple_row_value(r, "Proprietary Name")
    })
    blas = sorted({
        _purple_row_value(r, "BLA Number", "BLA")
        for r in matches if _purple_row_value(r, "BLA Number", "BLA")
    })
    reference_flags = sorted({
        _purple_row_value(r, "Reference Product")
        for r in matches
        if _purple_row_value(r, "Reference Product")
    })
    ref_proper_names = sorted({
        _purple_row_value(
            r,
            "Reference Product Proper Name",
            "Ref. Product Proper Name",
            "Reference Proper Name",
        )
        for r in matches
        if _purple_row_value(
            r,
            "Reference Product Proper Name",
            "Ref. Product Proper Name",
            "Reference Proper Name",
        )
    })
    ref_proprietary_names = sorted({
        _purple_row_value(
            r,
            "Reference Product Proprietary Name",
            "Ref. Product Proprietary Name",
            "Reference Product Properietary Name",
        )
        for r in matches
        if _purple_row_value(
            r,
            "Reference Product Proprietary Name",
            "Ref. Product Proprietary Name",
            "Reference Product Properietary Name",
        )
    })

    pathway_blob = " | ".join(license_types).lower()
    ref_flag_blob = " | ".join(reference_flags).lower()
    reference_names = reference_names or set()

    is_reference_by_relation = any(
        _norm(name) in reference_names
        for name in (proprietary_names + proper_names)
        if _norm(name)
    )

    status = "Not Identified"
    if matches:
        if "351(k) interchangeable" in pathway_blob or (
            "interchangeable" in pathway_blob and "351(k)" in pathway_blob
        ):
            status = "Interchangeable Biosimilar"
        elif "351(k)" in pathway_blob or "biosimilar" in pathway_blob:
            status = "Biosimilar"
        elif (
            "yes" in ref_flag_blob
            or "reference" in ref_flag_blob
            or is_reference_by_relation
        ):
            status = "Reference Biologic"
        else:
            status = "Biologic"

    return {
        "matched": bool(matches),
        "status": status,
        "blaNumbers": blas,
        "properNames": proper_names,
        "proprietaryNames": proprietary_names,
        "licenseTypes": license_types,
        "licensures": licensures,
        "referenceFlags": reference_flags,
        "referenceProductProperNames": ref_proper_names,
        "referenceProductProprietaryNames": ref_proprietary_names,
        "recordCount": len(matches),
    }


async def _build_enrichment_result(payload: EnrichmentRequest) -> Dict[str, Any]:
    """Staged catalogue-wide identity pass.

    Large catalogue runs intentionally avoid fetching full openFDA label documents,
    which are much heavier than Drugs@FDA application records and can block a
    single-worker service. Label/DailyMed enrichment is deferred to the residual
    tail after this first identity pass.
    """
    products = payload.products
    candidates = {p.recordId: _brand_candidates(p.name) for p in products}

    purple, drugs = await asyncio.gather(
        _purple_rows(),
        _batch_drugsfda(products, candidates),
    )

    purple_rows = list(purple.get("rows") or [])
    purple_index: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    purple_reference_names: set[str] = set()

    for row in purple_rows:
        proprietary = _purple_row_value(row, "Proprietary Name")
        key = _norm(proprietary)
        if key:
            purple_index[key].append(row)

        # Cross-dataset relation: any name explicitly listed as the reference
        # product for a 351(k) row is a reference biologic identity.
        for ref_name in (
            _purple_row_value(
                row,
                "Reference Product Proprietary Name",
                "Ref. Product Proprietary Name",
                "Reference Product Properietary Name",
            ),
            _purple_row_value(
                row,
                "Reference Product Proper Name",
                "Ref. Product Proper Name",
                "Reference Proper Name",
            ),
        ):
            if _norm(ref_name):
                purple_reference_names.add(_norm(ref_name))

    purple_by_id: Dict[str, Dict[str, Any]] = {}
    for p in products:
        matched_rows: List[Dict[str, str]] = []
        seen_row_ids = set()
        for candidate in candidates[p.recordId]:
            for row in purple_index.get(_norm(candidate), []):
                marker = id(row)
                if marker in seen_row_ids:
                    continue
                seen_row_ids.add(marker)
                matched_rows.append(row)

        purple_by_id[p.recordId] = _purple_match(
            matched_rows,
            candidates[p.recordId],
            purple_reference_names,
        )

    # Run the heavier label search only for the residual that Drugs@FDA and
    # Purple Book did not identify. This keeps catalogue-scale payloads bounded
    # while still resolving obvious current brands through SPL identity.
    residual_for_label = [
        p for p in products
        if not drugs.get(p.recordId, _empty_drugs()).get("matched")
        and not purple_by_id.get(p.recordId, {}).get("matched")
    ]

    labels = {p.recordId: _empty_label() for p in products}
    label_deferred = False
    if residual_for_label:
        residual_labels = await _batch_label(residual_for_label, candidates)
        labels.update(residual_labels)

    unresolved = [
        p for p in residual_for_label
        if not labels.get(p.recordId, _empty_label()).get("matched")
    ]

    daily_results: Dict[str, Dict[str, Any]] = {}
    daily_deferred = False

    # The async job architecture can safely run the residual DailyMed tail.
    # The loop-aware semaphore in _json_get bounds concurrency, so catalogue
    # scale does not translate into unbounded outbound requests.
    if unresolved:
        group_results = await asyncio.gather(*[
            _dailymed(p, candidates[p.recordId]) for p in unresolved
        ])
        for p, result in zip(unresolved, group_results):
            daily_results[p.recordId] = result

    rows = []
    for product in products:
        d = drugs.get(product.recordId, _empty_drugs())
        l = labels.get(product.recordId, _empty_label())
        dm = daily_results.get(
            product.recordId,
            {"matched": False, "setIds": [], "titles": [], "recordCount": 0},
        )
        pb = purple_by_id.get(
            product.recordId,
            {
                "matched": False,
                "status": "Not Identified",
                "blaNumbers": [],
                "properNames": [],
                "proprietaryNames": [],
                "licenseTypes": [],
                "licensures": [],
                "referenceFlags": [],
                "referenceProductProperNames": [],
                "referenceProductProprietaryNames": [],
                "recordCount": 0,
            },
        )

        sources = []
        if d.get("matched"):
            sources.append("DRUGSATFDA")
        if l.get("matched"):
            sources.append("OPENFDA_LABEL")
        if dm.get("matched"):
            sources.append("DAILYMED_SPL")
        if pb.get("matched"):
            sources.append("PURPLE_BOOK")

        exact_support = bool(
            d.get("matched") or l.get("matched") or pb.get("matched")
        )
        match_status = (
            "Matched"
            if exact_support
            else ("Partial" if dm.get("matched") else "Not Found")
        )
        confidence = (
            "High"
            if (d.get("matched") or pb.get("matched"))
            else ("Medium" if l.get("matched") or dm.get("matched") else "Low")
        )

        ingredients = sorted(set(
            list(d.get("activeIngredients") or [])
            + list(l.get("genericNames") or [])
            + list(l.get("substanceNames") or [])
            + list(pb.get("properNames") or [])
        ))
        applications = sorted(set(
            list(d.get("applicationNumbers") or [])
            + list(l.get("applicationNumbers") or [])
            + list(pb.get("blaNumbers") or [])
        ))
        spls = sorted(set(
            list(l.get("splSetIds") or [])
            + list(dm.get("setIds") or [])
        ))
        types = sorted(set(
            list(d.get("productTypes") or [])
            + list(l.get("productTypes") or [])
        ))

        rows.append({
            "recordId": product.recordId,
            "sourceName": product.name,
            "candidates": candidates[product.recordId],
            "matchStatus": match_status,
            "confidence": confidence,
            "applicationNumbers": applications,
            "activeIngredients": ingredients,
            "sponsorNames": sorted(set(
                list(d.get("sponsorNames") or [])
                + list(l.get("manufacturerNames") or [])
            )),
            "marketingStatuses": list(d.get("marketingStatuses") or []),
            "productTypes": types,
            "dosageForms": list(d.get("dosageForms") or []),
            "splSetIds": spls,
            "purpleBookStatus": pb.get("status") or "Not Identified",
            "sources": sources,
            "diagnostics": {
                "drugsAtFda": d,
                "label": l,
                "dailyMed": dm,
                "purpleBook": pb,
            },
        })

    counts = {"Matched": 0, "Partial": 0, "Ambiguous": 0, "Not Found": 0}
    for row in rows:
        counts[row["matchStatus"]] = counts.get(row["matchStatus"], 0) + 1

    return {
        "version": VERSION,
        "companyName": payload.companyName,
        "rows": rows,
        "summary": {
            "inputCount": len(products),
            "matchCounts": counts,
            "purpleBookSourceUrl": purple.get("sourceUrl"),
            "purpleBookAvailable": bool(purple.get("rows")),
            "purpleBookError": purple.get("error"),
            "openFdaApiKeyConfigured": bool(os.getenv("OPENFDA_API_KEY", "").strip()),
            "labelDeferred": label_deferred,
            "dailyMedDeferred": daily_deferred,
            "unresolvedBeforeDailyMed": len(unresolved),
            "portfolioWrites": 0,
        },
    }


def _job_request_key(payload: EnrichmentRequest) -> str:
    """Deterministic identity for one company catalogue request.

    Re-submitting the same catalogue within the job TTL reuses the existing
    queued/running/complete job instead of starting duplicate FDA work.
    """
    normalized = {
        "companyName": str(payload.companyName or "").strip(),
        "products": sorted(
            [
                {
                    "recordId": p.recordId,
                    "name": str(p.name or "").strip(),
                    "molecule": str(p.molecule or "").strip(),
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
            request_key = str(job.get("requestKey") or "")
            if request_key and _job_key_index.get(request_key) == job_id:
                _job_key_index.pop(request_key, None)


async def _run_enrichment_job(job_id: str, payload: EnrichmentRequest) -> None:
    started = time.time()
    try:
        with _jobs_lock:
            if job_id not in _jobs:
                return
            _jobs[job_id].update({"status": "running", "updatedAt": time.time()})

        result = await _build_enrichment_result(payload)

        with _jobs_lock:
            if job_id not in _jobs:
                return
            _jobs[job_id].update({
                "status": "complete",
                "updatedAt": time.time(),
                "result": result,
            })

        print(
            "US_IDENTITY_JOB_COMPLETE "
            + json.dumps(
                {
                    "jobId": job_id,
                    "inputCount": len(payload.products),
                    "durationSeconds": round(time.time() - started, 2),
                    "matchCounts": (result.get("summary") or {}).get("matchCounts"),
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
            "US_IDENTITY_JOB_ERROR "
            + json.dumps(
                {
                    "jobId": job_id,
                    "inputCount": len(payload.products),
                    "durationSeconds": round(time.time() - started, 2),
                    "error": f"{type(exc).__name__}: {str(exc)[:500]}",
                },
                separators=(",", ":"),
            ),
            flush=True,
        )


def _run_enrichment_job_thread(job_id: str, payload_dict: Dict[str, Any]) -> None:
    """Run one enrichment job on a separate thread + event loop.

    This keeps the FastAPI/Uvicorn event loop responsive for /health and
    Airtable polling while large FDA responses are fetched and normalized.
    """
    payload = EnrichmentRequest(**payload_dict)
    asyncio.run(_run_enrichment_job(job_id, payload))


@app.post("/marketed/us-identity/jobs")
async def create_us_identity_job(
    payload: EnrichmentRequest,
    x_adapter_key: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    _auth(x_adapter_key)
    _prune_jobs()

    request_key = _job_request_key(payload)
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

        job_id = "usmi_" + uuid.uuid4().hex
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
        asyncio.to_thread(
            _run_enrichment_job_thread,
            job_id,
            payload.model_dump(),
        )
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


@app.get("/marketed/us-identity/jobs/{job_id}")
async def get_us_identity_job(
    job_id: str,
    x_adapter_key: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    _auth(x_adapter_key)
    _prune_jobs()

    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="U.S. identity enrichment job not found")

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


@app.get("/marketed/us-identity/jobs/{job_id}/result")
async def get_us_identity_job_result(
    job_id: str,
    offset: int = 0,
    limit: int = 50,
    x_adapter_key: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    """Return a bounded page of a completed job result.

    Large 290-product catalogues are paged so Airtable never receives the full
    enrichment payload in one HTTP response.
    """
    _auth(x_adapter_key)
    _prune_jobs()

    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="U.S. identity enrichment job not found")
    if job.get("status") != "complete":
        raise HTTPException(status_code=409, detail="U.S. identity enrichment job is not complete")
    if offset < 0 or limit < 1 or limit > 50:
        raise HTTPException(status_code=400, detail="offset must be >=0 and limit must be 1..50")

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


@app.get("/marketed/us-identity/jobs/{job_id}/wait")
async def wait_us_identity_job(
    job_id: str,
    x_adapter_key: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    """Long-poll one job for up to ~6s.

    Airtable automation scripts do not provide a dependable timer primitive.
    Keeping the wait on the adapter side lets Airtable make a bounded fetch
    while the background enrichment continues.
    """
    _auth(x_adapter_key)
    _prune_jobs()

    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="U.S. identity enrichment job not found")

    deadline = time.monotonic() + 6.0
    while job.get("status") in {"queued", "running"} and time.monotonic() < deadline:
        await asyncio.sleep(0.5)
        job = _jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="U.S. identity enrichment job not found")

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

@app.get("/marketed/us-identity/health")
async def us_identity_health() -> Dict[str, Any]:
    purple = await _purple_rows()
    return {
        "ok": True,
        "version": VERSION,
        "writeMode": "READ_ONLY",
        "openFdaApiKeyConfigured": bool(os.getenv("OPENFDA_API_KEY", "").strip()),
        "purpleBookRowsLoaded": len(purple.get("rows") or []),
        "purpleBookSourceUrl": purple.get("sourceUrl"),
        "purpleBookError": purple.get("error"),
        "maxProductsPerRequest": MAX_PRODUCTS,
    }


@app.post("/marketed/us-identity/enrich")
async def us_identity_enrich(
    payload: EnrichmentRequest,
    x_adapter_key: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    _auth(x_adapter_key)
    return await _build_enrichment_result(payload)
