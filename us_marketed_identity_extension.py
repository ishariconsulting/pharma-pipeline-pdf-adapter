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
from typing import Any, Dict, List, Optional

import httpx
from fastapi import Header, HTTPException
from pydantic import BaseModel, Field

from main import _auth, app


VERSION = "US_MARKETED_IDENTITY_V1.0"
MAX_PRODUCTS = 30
OPENFDA_BASE = "https://api.fda.gov"
DAILYMED_SPLS = "https://dailymed.nlm.nih.gov/dailymed/services/v2/spls.json"
PURPLE_DOWNLOADS = "https://www.accessdata.fda.gov/scripts/purplebooksearch/index.cfm?event=downloads"
CACHE_TTL = 86400.0

_http_cache: Dict[str, tuple[float, Any]] = {}
_purple_cache: Dict[str, Any] = {"ts": 0.0, "rows": [], "sourceUrl": None, "error": None}
_sem = asyncio.Semaphore(10)


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

    # Preserve known dual-family wording as separate candidates below.
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

    # Trademark-bearing tokens often reveal each member of a family label.
    for match in re.finditer(r"([A-Za-z0-9][A-Za-z0-9-]{2,})\s*[®™]", str(raw or "")):
        values.append(match.group(1))

    # Useful family reductions such as NURTEC ODT -> NURTEC.
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


async def _json_get(url: str, params: Optional[Dict[str, Any]] = None, timeout_seconds: float = 18.0) -> Any:
    key = url + "?" + "&".join(f"{k}={params[k]}" for k in sorted(params or {}))
    now = time.time()
    cached = _http_cache.get(key)
    if cached and now - cached[0] < CACHE_TTL:
        return cached[1]

    headers = {
        "User-Agent": "PharmaCommercialIntelligence/1.0 (+read-only official-source identity)",
        "Accept": "application/json",
    }
    async with _sem:
        timeout = httpx.Timeout(timeout_seconds, connect=min(8.0, timeout_seconds))
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers=headers) as client:
            response = await client.get(url, params=params)
    if response.status_code == 404:
        payload = {"results": []}
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


async def _openfda(path: str, search: str, limit: int = 20) -> List[Dict[str, Any]]:
    params: Dict[str, Any] = {"search": search, "limit": limit}
    key = os.getenv("OPENFDA_API_KEY", "").strip()
    if key:
        params["api_key"] = key
    try:
        payload = await _json_get(f"{OPENFDA_BASE}{path}", params=params)
    except HTTPException as exc:
        # openFDA returns 404 when a query has no matches.
        if "404" in str(exc.detail):
            return []
        raise
    return list(payload.get("results") or [])


def _candidate_matches(value: Any, candidates: List[str]) -> bool:
    nv = _norm(value)
    if not nv:
        return False
    for c in candidates:
        nc = _norm(c)
        if nv == nc or nv.startswith(nc + " ") or nc.startswith(nv + " "):
            return True
    return False


async def _drugsfda(product: ProductInput, candidates: List[str]) -> Dict[str, Any]:
    results: List[Dict[str, Any]] = []
    seen_apps = set()

    # Try the most specific candidates first; stop after a useful exact family match.
    for candidate in candidates[:3]:
        q = f'products.brand_name:"{candidate.replace(chr(34), "")}"'
        rows = await _openfda("/drug/drugsfda.json", q, limit=20)
        useful = []
        for row in rows:
            matching_products = [
                p for p in (row.get("products") or [])
                if _candidate_matches(p.get("brand_name"), candidates)
            ]
            if not matching_products:
                continue
            app = str(row.get("application_number") or "")
            if app and app in seen_apps:
                continue
            if app:
                seen_apps.add(app)
            useful.append({**row, "_matching_products": matching_products})
        results.extend(useful)
        if useful:
            break

    applications = sorted({str(r.get("application_number") or "").strip() for r in results if r.get("application_number")})
    sponsors = sorted({str(r.get("sponsor_name") or "").strip() for r in results if r.get("sponsor_name")})
    brands = sorted({
        str(p.get("brand_name") or "").strip()
        for r in results for p in r.get("_matching_products", [])
        if p.get("brand_name")
    })
    ingredients = sorted({
        str(ai.get("name") or "").strip()
        for r in results for p in r.get("_matching_products", [])
        for ai in (p.get("active_ingredients") or [])
        if ai.get("name")
    })
    dosage_forms = sorted({
        str(p.get("dosage_form") or "").strip()
        for r in results for p in r.get("_matching_products", [])
        if p.get("dosage_form")
    })
    marketing = sorted({
        str(p.get("marketing_status") or "").strip()
        for r in results for p in r.get("_matching_products", [])
        if p.get("marketing_status")
    })
    product_types = sorted({
        str(r.get("openfda", {}).get("product_type", [""])[0] or "").strip()
        for r in results if r.get("openfda", {}).get("product_type")
    })

    return {
        "matched": bool(results),
        "applicationNumbers": applications,
        "sponsorNames": sponsors,
        "brandNames": brands,
        "activeIngredients": ingredients,
        "dosageForms": dosage_forms,
        "marketingStatuses": marketing,
        "productTypes": [x for x in product_types if x],
        "recordCount": len(results),
    }


async def _label(product: ProductInput, candidates: List[str]) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    seen = set()
    for candidate in candidates[:3]:
        q = f'openfda.brand_name:"{candidate.replace(chr(34), "")}"'
        found = await _openfda("/drug/label.json", q, limit=10)
        useful = []
        for row in found:
            ofda = row.get("openfda") or {}
            if not any(_candidate_matches(b, candidates) for b in (ofda.get("brand_name") or [])):
                continue
            rid = str(row.get("id") or "") + "|" + "|".join(ofda.get("spl_set_id") or [])
            if rid in seen:
                continue
            seen.add(rid)
            useful.append(row)
        rows.extend(useful)
        if useful:
            break

    def collect(field: str) -> List[str]:
        return sorted({
            str(v).strip()
            for row in rows for v in ((row.get("openfda") or {}).get(field) or [])
            if str(v).strip()
        })

    return {
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


async def _dailymed(product: ProductInput, candidates: List[str]) -> Dict[str, Any]:
    # Bounded fallback: only the most specific candidate, brand-name mode.
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
    useful = [
        r for r in rows
        if _candidate_matches(str(r.get("title") or "").split("(", 1)[0], candidates)
    ]
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
    if now - float(_purple_cache.get("ts") or 0) < CACHE_TTL and _purple_cache.get("rows"):
        return _purple_cache

    headers = {"User-Agent": "PharmaCommercialIntelligence/1.0 (+read-only official-source identity)"}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=8.0), follow_redirects=True, headers=headers) as client:
            page = await client.get(PURPLE_DOWNLOADS)
            page.raise_for_status()
            links = re.findall(
                r'href=["\']([^"\']+purplebook[^"\']+\.csv)["\']',
                page.text,
                flags=re.I,
            )
            if not links:
                raise RuntimeError("No Purple Book CSV links found")
            # The FDA page lists the current year in chronological order; choose the last current-year CSV.
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
        for idx, line in enumerate(lines[:80]):
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
        if "interchangeable" in blob and "351(k)" in blob:
            status = "Interchangeable Biosimilar"
        elif "351(k)" in blob or "biosimilar" in blob:
            status = "Biosimilar"
        elif any("reference" in str(_purple_row_value(r, "Reference Product")).lower() for r in matches):
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


async def _enrich_one(product: ProductInput, purple: Dict[str, Any]) -> Dict[str, Any]:
    candidates = _brand_candidates(product.name)
    drugs, label = await asyncio.gather(
        _drugsfda(product, candidates),
        _label(product, candidates),
    )

    daily = {"matched": False, "setIds": [], "titles": [], "recordCount": 0}
    if not label.get("matched"):
        daily = await _dailymed(product, candidates)

    purple_match = _purple_match(list(purple.get("rows") or []), candidates)

    evidence_sources = []
    if drugs.get("matched"):
        evidence_sources.append("DRUGSATFDA")
    if label.get("matched"):
        evidence_sources.append("OPENFDA_LABEL")
    if daily.get("matched"):
        evidence_sources.append("DAILYMED_SPL")
    if purple_match.get("matched"):
        evidence_sources.append("PURPLE_BOOK")

    matched = bool(evidence_sources)
    exact_support = bool(drugs.get("matched") or label.get("matched") or purple_match.get("matched"))
    status = "Matched" if exact_support else ("Partial" if daily.get("matched") else "Not Found")
    confidence = "High" if (drugs.get("matched") or purple_match.get("matched")) else ("Medium" if label.get("matched") or daily.get("matched") else "Low")

    ingredients = sorted(set(
        list(drugs.get("activeIngredients") or [])
        + list(label.get("genericNames") or [])
        + list(label.get("substanceNames") or [])
        + list(purple_match.get("properNames") or [])
    ))
    applications = sorted(set(
        list(drugs.get("applicationNumbers") or [])
        + list(label.get("applicationNumbers") or [])
        + list(purple_match.get("blaNumbers") or [])
    ))
    spls = sorted(set(list(label.get("splSetIds") or []) + list(daily.get("setIds") or [])))
    types = sorted(set(list(drugs.get("productTypes") or []) + list(label.get("productTypes") or [])))

    return {
        "recordId": product.recordId,
        "sourceName": product.name,
        "candidates": candidates,
        "matchStatus": status,
        "confidence": confidence,
        "applicationNumbers": applications,
        "activeIngredients": ingredients,
        "sponsorNames": sorted(set(list(drugs.get("sponsorNames") or []) + list(label.get("manufacturerNames") or []))),
        "marketingStatuses": list(drugs.get("marketingStatuses") or []),
        "productTypes": types,
        "dosageForms": list(drugs.get("dosageForms") or []),
        "splSetIds": spls,
        "purpleBookStatus": purple_match.get("status") or "Not Identified",
        "sources": evidence_sources,
        "diagnostics": {
            "drugsAtFda": drugs,
            "label": label,
            "dailyMed": daily,
            "purpleBook": purple_match,
        },
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
    purple = await _purple_rows()
    rows = await asyncio.gather(*[_enrich_one(p, purple) for p in payload.products])

    counts = {"Matched": 0, "Partial": 0, "Ambiguous": 0, "Not Found": 0}
    for row in rows:
        counts[row.get("matchStatus") or "Not Found"] = counts.get(row.get("matchStatus") or "Not Found", 0) + 1

    return {
        "version": VERSION,
        "companyName": payload.companyName,
        "rows": rows,
        "summary": {
            "inputCount": len(payload.products),
            "matchCounts": counts,
            "purpleBookSourceUrl": purple.get("sourceUrl"),
            "purpleBookAvailable": bool(purple.get("rows")),
            "openFdaApiKeyConfigured": bool(os.getenv("OPENFDA_API_KEY", "").strip()),
            "portfolioWrites": 0,
        },
    }
