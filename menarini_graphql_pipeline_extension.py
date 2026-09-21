"""Read-only Menarini official AEM GraphQL pipeline adapter.

Discovers pipeline content-fragment paths from the official page and reads the
same persisted GraphQL query used by the page client. Duplicate presentation
views (focus by compound vs indication) are collapsed at source grain.
No Airtable or master-data writes.
"""
from __future__ import annotations

import html as html_lib
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

import httpx
from fastapi import Header, HTTPException, Query
from pydantic import BaseModel

from main import _auth, app
from html_fetch_extension import _assert_public_http_url

ADAPTER_PROFILE="PIPELINE_MENARINI_GRAPHQL_V1"
ROUTE_VERSION="MENARINI_AEM_GRAPHQL_PIPELINE_V1.0_READ_ONLY"
MIN_ROWS=4
MAX_BYTES=8_000_000


class MenariniPipelineResponse(BaseModel):
    version:str
    routeVersion:str
    company:str
    sourceUrl:str
    finalUrl:str
    retrievalMode:str
    readOnly:bool
    readyForDiscovery:bool
    rowCount:int
    rows:List[Dict[str,Any]]
    summary:Dict[str,Any]
    issues:List[Dict[str,Any]]
    diagnostics:Dict[str,Any]
    guardrails:Dict[str,Any]


def clean(v:Any)->str:
    return re.sub(r"\s+"," ",str(v or "")).strip()


def canonical_stage(v:Any)->str:
    s=clean(v)
    n=re.sub(r"[^a-z0-9]+","",s.lower())
    if n in {"p","preclinical","preclinicalstage"}: return "Preclinical"
    if n in {"ia","ib","i","1","1a","1b","phase1","phase1a","phase1b"}: return "Phase 1"
    if n in {"ii","2","phase2"}: return "Phase 2"
    if n in {"iii","3","phase3"}: return "Phase 3"
    if n in {"iv","4","phase4"}: return "Phase 4"
    if n in {"f","filed","filing","registration","regulatoryreview"}: return "Filed / Registration"
    if n in {"a","approved","approval"}: return "Approved"
    return ""


def identity(asset:Any)->Dict[str,str]:
    value=clean(asset)
    brand=""
    molecule=value
    development=""
    if "®" in value or "™" in value:
        brand=clean(re.split(r"[®™]",value,1)[0])
        m=re.search(r"\(([^()]{2,100})\)",value)
        if m: molecule=clean(m.group(1))
    code=re.search(r"\b([A-Z]{2,10}[- ]?\d{2,7})\b",value)
    if code:
        development=clean(code.group(1))
    return {"asset":value,"molecule":molecule,"brand":brand,"developmentCode":development}


async def extract_menarini_pipeline(company:str, source_url:str, timeout_seconds:float=35.0)->MenariniPipelineResponse:
    await _assert_public_http_url(source_url)
    parsed=urlparse(source_url)
    origin=f"{parsed.scheme}://{parsed.netloc}"
    headers={"User-Agent":"Mozilla/5.0 MenariniPipelineAdapter/1.0","Accept":"text/html,application/json,*/*;q=0.8"}
    total_bytes=0

    try:
        async with httpx.AsyncClient(timeout=timeout_seconds,follow_redirects=True,headers=headers) as client:
            page=await client.get(source_url)
            if page.status_code!=200:
                raise HTTPException(status_code=502,detail=f"Menarini pipeline page returned HTTP {page.status_code}")
            total_bytes+=len(page.content)
            final_url=str(page.url)
            await _assert_public_http_url(final_url)

            paths=re.findall(r'data-table-cf-path=["\']([^"\']+)["\']',page.text,re.I)
            paths=list(dict.fromkeys(html_lib.unescape(p) for p in paths))
            if not paths:
                raise HTTPException(status_code=422,detail="No pipeline content-fragment paths found")

            raw_rows=[]
            endpoint_counts={}
            for path in paths:
                endpoint=origin+"/graphql/execute.json/menarini-com/pipeline-table;path="+path
                await _assert_public_http_url(endpoint)
                response=await client.get(endpoint)
                if response.status_code!=200:
                    raise HTTPException(status_code=502,detail=f"Menarini GraphQL source returned HTTP {response.status_code}")
                total_bytes+=len(response.content)
                if total_bytes>MAX_BYTES:
                    raise HTTPException(status_code=413,detail="Menarini pipeline source exceeds size limit")
                try:
                    payload=response.json()
                except Exception as exc:
                    raise HTTPException(status_code=502,detail="Menarini GraphQL source returned invalid JSON") from exc
                item=(((payload or {}).get("data") or {}).get("pipelineTableByPath") or {}).get("item")
                items=(item or {}).get("pipelineItems") if isinstance(item,dict) else None
                if not isinstance(items,list):
                    raise HTTPException(status_code=422,detail="Menarini GraphQL response missing pipelineItems[]")
                endpoint_counts[path]=len(items)
                for row in items:
                    if isinstance(row,dict):
                        raw_rows.append((path,row))
    except HTTPException:
        raise
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504,detail="Menarini pipeline source timed out") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502,detail=f"Menarini pipeline source fetch failed: {exc}") from exc

    parsed_rows=[]
    rejected=0
    for source_path,row in raw_rows:
        ident=identity(row.get("compound"))
        indication=clean(row.get("indication") or row.get("medicalCondition"))
        source_stage=clean(row.get("developmentStage") or row.get("phase") or row.get("status"))
        phase=canonical_stage(source_stage)
        if not ident["asset"] or not indication or not phase:
            rejected+=1
            continue
        parsed_rows.append({
            "company":company,
            "sourceFamily":"Company Pipeline",
            "sourceRecordId":clean(row.get("_path")) or f"menarini:{len(parsed_rows)+1}",
            "sourceUrl":final_url,
            **ident,
            "indication":indication,
            "phase":phase,
            "phaseEvidence":"SOURCE_GRAPHQL",
            "programStatus":"Active",
            "sponsorOwner":company,
            "partners":[],
            "study":"",
            "trialIds":[],
            "therapeuticArea":"",
            "mechanismOfAction":clean(row.get("mechanismOfAction")),
            "sourceStageText":source_stage,
            "sourceContentFragmentPath":source_path,
            "sourceOrdinal":len(parsed_rows)+1,
            "parserMethod":"MENARINI_AEM_GRAPHQL",
            "sourceAdapter":ADAPTER_PROFILE,
        })

    # The site exposes duplicate presentation tables (focus on compound vs
    # indication). Collapse only exact source-grain duplicates.
    dedup=[]
    seen=set()
    duplicates=0
    for row in parsed_rows:
        key=(row["asset"].lower(),row["indication"].lower(),row["phase"].lower())
        if key in seen:
            duplicates+=1
            continue
        seen.add(key)
        row["sourceOrdinal"]=len(dedup)+1
        dedup.append(row)

    issues=[]
    if len(dedup)<MIN_ROWS:
        issues.append(f"too few structured rows: {len(dedup)} < {MIN_ROWS}")
    if rejected>max(3,int(max(1,len(dedup))*0.2)):
        issues.append(f"too many source rows missing core asset/indication/stage: {rejected}")
    ready=not issues

    return MenariniPipelineResponse(
        version=ADAPTER_PROFILE,routeVersion=ROUTE_VERSION,company=company,
        sourceUrl=source_url,finalUrl=final_url,retrievalMode="EXTERNAL_HTTP",
        readOnly=True,readyForDiscovery=ready,rowCount=len(dedup),rows=dedup,
        summary={
            "structuralValidationPass":ready,
            "actual":{"Total":len(dedup)},
            "productionStatus":"READY FOR AIRTABLE DELTA COMPARISON" if ready else "FAIL CLOSED - PARSER/STRUCTURE REVIEW REQUIRED",
            "selectedMethod":"MENARINI_AEM_GRAPHQL",
            "portfolioDependentValidation":False,
            "writeMode":"READ_ONLY",
        },
        issues=[{"issue":x} for x in issues],
        diagnostics={
            "contentFragmentPaths":len(paths),
            "endpointCounts":endpoint_counts,
            "rawRows":len(raw_rows),
            "parsedRowsBeforeDedup":len(parsed_rows),
            "dedupedRows":len(dedup),
            "rejectedRows":rejected,
            "exactDuplicatesRemoved":duplicates,
            "documentBytes":total_bytes,
            "portfolioDependentValidation":False,
            "writes":0,
        },
        guardrails={
            "airtableWrites":False,"portfolioWrites":False,"masterDataWrites":False,
            "portfolioDependentValidation":False,"publicHttpOnly":True,
            "fuzzyIdentityResolution":False,
        }
    )


@app.get("/extract/menarini/graphql-pipeline/health")
async def menarini_health()->Dict[str,Any]:
    return {"ok":True,"version":ADAPTER_PROFILE,"routeVersion":ROUTE_VERSION,"readOnly":True}


@app.get("/extract/menarini/graphql-pipeline",response_model=MenariniPipelineResponse)
async def menarini_route(
    company:str=Query(default="Menarini Group",min_length=1,max_length=160),
    source_url:str=Query(default="https://www.menarini.com/en-us/innovation-research/our-pipeline-and-products.html",min_length=8),
    timeout_seconds:float=Query(default=35.0,ge=5.0,le=35.0),
    x_adapter_key:Optional[str]=Header(default=None),
)->MenariniPipelineResponse:
    _auth(x_adapter_key)
    return await extract_menarini_pipeline(company,source_url,timeout_seconds)
