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
import json
import os
import re
import threading
import time
import uuid
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional

import httpx
from fastapi import Header, HTTPException
from pydantic import BaseModel, Field

from main import _auth, app


VERSION = "US_MARKETED_BASELINE_EVIDENCE_V1.0"
OPENFDA_LABEL_URL = "https://api.fda.gov/drug/label.json"
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

    for m in re.finditer(r"([A-Za-z0-9][A-Za-z0-9-]{2,})\s*[®™]", str(raw or "")):
        values.append(m.group(1))

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
        "source": "openFDA drug labeling / DailyMed SPL",
        "maxProductsPerRequest": MAX_PRODUCTS,
    }
