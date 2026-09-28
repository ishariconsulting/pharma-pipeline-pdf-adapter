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
import io
import os
import re
import time
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional

import httpx
from fastapi import Header, HTTPException
from pydantic import BaseModel, Field

from main import _auth, app


VERSION = "US_MARKETED_IDENTITY_V1.1_BATCHED"
MAX_PRODUCTS = 100
OPENFDA_BASE = "https://api.fda.gov"
DAILYMED_SPLS = "https://dailymed.nlm.nih.gov/dailymed/services/v2/spls.json"
PURPLE_DOWNLOADS = "https://www.accessdata.fda.gov/scripts/purplebooksearch/index.cfm?event=downloads"
CACHE_TTL = 86400.0

_http_cache: Dict[str, tuple[float, Any]] = {}
_purple_cache: Dict[str, Any] = {"ts": 0.0, "rows": [], "sourceUrl": None, "error": None}
_sem = asyncio.Semaphore(8)


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
        "User-Agent": "PharmaCommercialIntelligence/1.1 (+read-only official-source identity)",
        "Accept": "application/json",
    }
    async with _sem:
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
        for candidate in candidates[p.recordId][:2]:
            n = _norm(candidate)
            if not n or n in seen:
                continue
            seen.add(n)
            terms.append(candidate.replace('"', "").strip())
    return terms


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

    for group in _chunks(terms, 10):
        search = " OR ".join(f'products.brand_name:"{term}"' for term in group)
        payload = await _openfda("/drug/drugsfda.json", search, limit=99)
        rows = list(payload.get("results") or [])

        for row in rows:
            brands = [str(p.get("brand_name") or "") for p in (row.get("products") or [])]
            for product in products:
                if any(_candidate_matches(b, candidates[product.recordId]) for b in brands):
                    raw[product.recordId].append(row)

    out: Dict[str, Dict[str, Any]] = {}
    for product in products:
        rows = raw.get(product.recordId, [])
        apps = set()
        sponsors = set()
        brands = set()
        ingredients = set()
        forms = set()
        marketing = set()
        product_types = set()

        for row in rows:
            if row.get("application_number"):
                apps.add(str(row["application_number"]).strip())
            if row.get("sponsor_name"):
                sponsors.add(str(row["sponsor_name"]).strip())
            for p in (row.get("products") or []):
                if not _candidate_matches(p.get("brand_name"), candidates[product.recordId]):
                    continue
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
            "matched": bool(rows),
            "applicationNumbers": sorted(apps),
            "sponsorNames": sorted(sponsors),
            "brandNames": sorted(brands),
            "activeIngredients": sorted(ingredients),
            "dosageForms": sorted(forms),
            "marketingStatuses": sorted(marketing),
            "productTypes": sorted(product_types),
            "recordCount": len(rows),
        }
    return out


async def _batch_label(products: List[ProductInput], candidates: Dict[str, List[str]]) -> Dict[str, Dict[str, Any]]:
    raw: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    terms = _query_terms(products, candidates)

    for group in _chunks(terms, 10):
        search = " OR ".join(f'openfda.brand_name:"{term}"' for term in group)
        payload = await _openfda("/drug/label.json", search, limit=1000)
        rows = list(payload.get("results") or [])

        for row in rows:
            brands = [str(x) for x in ((row.get("openfda") or {}).get("brand_name") or [])]
            for product in products:
                if any(_candidate_matches(b, candidates[product.recordId]) for b in brands):
                    raw[product.recordId].append(row)

    out: Dict[str, Dict[str, Any]] = {}
    for product in products:
        rows = raw.get(product.recordId, [])

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
        }
    return out


async def _dailymed(product: ProductInput, candidates: List[str]) -> Dict[str, Any]:
    candidate = candidates[0] if candidates else product.name
    try:
        payload = await _json_get(
            DAILYMED_SPLS,
            params={"drug_name": candidate, "name_type": "brand", "pagesize": 10, "page": 1},
            timeout_seconds=15.0,
        )
    except Exception:
        return {"matched": False, "setIds": [], "titles": [], "recordCount": 0, "error": "DAILYMED_FETCH_FAILED"}

    rows = list(payload.get("data") or [])
    useful = []
    for row in rows:
        title_brand = str(row.get("title") or "").split("(", 1)[0].strip()
        if _candidate_matches(title_brand, candidates):
            useful.append(row)

    return {
        "matched": bool(useful),
        "setIds": sorted({str(r.get("setid") or "").strip() for r in useful if r.get("setid")}),
        "titles": [str(r.get("title") or "").strip() for r in useful[:10]],
        "recordCount": len(useful),
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

    headers = {"User-Agent": "PharmaCommercialIntelligence/1.1 (+read-only official-source identity)"}
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


def _purple_match(rows: List[Dict[str, str]], candidates: List[str]) -> Dict[str, Any]:
    matches = []
    for row in rows:
        proprietary = _purple_row_value(row, "Proprietary Name")
        if proprietary and _candidate_matches(proprietary, candidates):
            matches.append(row)

    license_types = sorted({
        _purple_row_value(r, "Licensure", "License Type", "Submission Type")
        for r in matches
        if _purple_row_value(r, "Licensure", "License Type", "Submission Type")
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

    blob = " | ".join(
        _purple_row_value(r, "Licensure", "License Type", "Submission Type", "Reference Product")
        for r in matches
    ).lower()

    status = "Not Identified"
    if matches:
        if "interchangeable" in blob and ("351(k)" in blob or "biosimilar" in blob):
            status = "Interchangeable Biosimilar"
        elif "351(k)" in blob or "biosimilar" in blob:
            status = "Biosimilar"
        elif any("reference" in _purple_row_value(r, "Reference Product").lower() for r in matches):
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
        "recordCount": len(matches),
    }


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

    products = payload.products
    candidates = {p.recordId: _brand_candidates(p.name) for p in products}
    purple, drugs, labels = await asyncio.gather(
        _purple_rows(),
        _batch_drugsfda(products, candidates),
        _batch_label(products, candidates),
    )

    unresolved = [
        p for p in products
        if not drugs.get(p.recordId, _empty_drugs()).get("matched")
        and not labels.get(p.recordId, _empty_label()).get("matched")
    ]

    # DailyMed is a bounded fallback rather than the primary transport.
    daily_results: Dict[str, Dict[str, Any]] = {}
    for group in _chunks(unresolved, 10):
        group_results = await asyncio.gather(*[_dailymed(p, candidates[p.recordId]) for p in group])
        for p, result in zip(group, group_results):
            daily_results[p.recordId] = result

    rows = []
    for product in products:
        d = drugs.get(product.recordId, _empty_drugs())
        l = labels.get(product.recordId, _empty_label())
        dm = daily_results.get(product.recordId, {"matched": False, "setIds": [], "titles": [], "recordCount": 0})
        pb = _purple_match(list(purple.get("rows") or []), candidates[product.recordId])

        sources = []
        if d.get("matched"):
            sources.append("DRUGSATFDA")
        if l.get("matched"):
            sources.append("OPENFDA_LABEL")
        if dm.get("matched"):
            sources.append("DAILYMED_SPL")
        if pb.get("matched"):
            sources.append("PURPLE_BOOK")

        exact_support = bool(d.get("matched") or l.get("matched") or pb.get("matched"))
        match_status = "Matched" if exact_support else ("Partial" if dm.get("matched") else "Not Found")
        confidence = "High" if (d.get("matched") or pb.get("matched")) else ("Medium" if l.get("matched") or dm.get("matched") else "Low")

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
        spls = sorted(set(list(l.get("splSetIds") or []) + list(dm.get("setIds") or [])))
        types = sorted(set(list(d.get("productTypes") or []) + list(l.get("productTypes") or [])))

        rows.append({
            "recordId": product.recordId,
            "sourceName": product.name,
            "candidates": candidates[product.recordId],
            "matchStatus": match_status,
            "confidence": confidence,
            "applicationNumbers": applications,
            "activeIngredients": ingredients,
            "sponsorNames": sorted(set(list(d.get("sponsorNames") or []) + list(l.get("manufacturerNames") or []))),
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
            "portfolioWrites": 0,
        },
    }
