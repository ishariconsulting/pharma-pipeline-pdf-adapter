"""Read-only Merck KGaA healthcare pipeline adapter.

Consumes the first-party static data.js used by the official Healthcare
Pipeline page. The data source is a JSON array assigned to pipelineData.
"""
from __future__ import annotations

import html as html_lib
import json
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import httpx
from fastapi import Header, HTTPException, Query
from pydantic import BaseModel

from main import _auth, app
from html_fetch_extension import _assert_public_http_url


ADAPTER_PROFILE="PIPELINE_MERCK_KGAA_JS_V1"
ROUTE_VERSION="MERCK_KGAA_PIPELINE_JS_V1.0_READ_ONLY"
DEFAULT_DATA_URL="https://www.emdgroup.com/content/dam/scripts/group/en/pipeline/data.js"
MIN_ROWS=4
MAX_BYTES=3_000_000


class MerckPipelineResponse(BaseModel):
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


def text_only(v:Any)->str:
    s=html_lib.unescape(str(v or ""))
    s=re.sub(r"<sup\b[^>]*>[\s\S]*?</sup>"," ",s,flags=re.I)
    s=re.sub(r"<[^>]+>"," ",s)
    return clean(s)


def phase_value(raw:Any,phase_text:Any="")->str:
    n=clean(raw).lower()
    label=clean(phase_text).lower()
    if n=="1": return "Phase 1"
    if n=="2": return "Phase 2"
    if n=="3": return "Phase 3"
    # The source UI contract explicitly labels value 4 as Registration.
    if n=="4": return "Filed / Registration"
    if "registration" in n or "filed" in n: return "Filed / Registration"
    if "phase 1" in n or label.startswith("1"): return "Phase 1"
    if "phase 2" in n or label.startswith("2"): return "Phase 2"
    if "phase 3" in n or label.startswith("3"): return "Phase 3"
    return ""


def parse_pipeline_data(script_text:str)->List[Dict[str,Any]]:
    m=re.search(r"\bpipelineData\s*=\s*(\[[\s\S]*\])\s*;?\s*$",script_text,re.I)
    if not m:
        raise HTTPException(status_code=422,detail="pipelineData JSON assignment not found")
    try:
        data=json.loads(m.group(1))
    except Exception as exc:
        raise HTTPException(status_code=422,detail=f"pipelineData payload is not valid JSON: {exc}") from exc
    if not isinstance(data,list):
        raise HTTPException(status_code=422,detail="pipelineData payload is not a list")
    return data


async def extract_merck_pipeline(
    company:str,
    source_url:str,
    timeout_seconds:float=35.0,
)->MerckPipelineResponse:
    # source_url may be the official pipeline page or the first-party data.js.
    data_url=source_url if source_url.lower().split("?")[0].endswith(".js") else DEFAULT_DATA_URL
    await _assert_public_http_url(data_url)
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds,connect=min(12.0,timeout_seconds)),
            follow_redirects=True,
            headers={"User-Agent":"Mozilla/5.0 MerckPipelineAdapter/1.0","Accept":"application/javascript,*/*;q=0.8"},
        ) as client:
            resp=await client.get(data_url)
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504,detail="Merck pipeline data source timed out") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502,detail=f"Merck pipeline data source fetch failed: {exc}") from exc
    if resp.status_code!=200:
        raise HTTPException(status_code=502,detail=f"Merck pipeline data source returned HTTP {resp.status_code}")
    if len(resp.content)>MAX_BYTES:
        raise HTTPException(status_code=413,detail="Merck pipeline data source exceeds size limit")
    final_url=str(resp.url)
    await _assert_public_http_url(final_url)

    groups=parse_pipeline_data(resp.text)
    rows=[]; rejected=[]; source_rows=0
    for group in groups:
        if not isinstance(group,dict):
            continue
        group_name=text_only(group.get("name"))
        data_rows=group.get("dataRows") or []
        if not isinstance(data_rows,list):
            continue
        for item in data_rows:
            source_rows+=1
            if not isinstance(item,dict):
                rejected.append({"ordinal":source_rows,"reason":"NON_OBJECT"}); continue
            asset=text_only(item.get("title1"))
            indication=text_only(item.get("title2"))
            ph=phase_value(item.get("phase"),item.get("phasetext"))
            ta=text_only(item.get("type")) or group_name
            if not asset or not indication or not ph:
                rejected.append({
                  "ordinal":source_rows,"asset":asset,"indication":indication,
                  "phaseRaw":clean(item.get("phase")),"phaseText":clean(item.get("phasetext")),
                })
                continue
            trial_links=[
              clean(item.get(k))
              for k in ["link1URL","link2URL","link3URL","link4URL","link5URL","link6URL"]
              if clean(item.get(k))
            ]
            rows.append({
              "company":company,
              "sourceFamily":"Company Pipeline",
              "sourceRecordId":f"merckjs:{source_rows}",
              "sourceUrl":final_url,
              "asset":asset,
              "molecule":asset,
              "developmentCode":"",
              "brand":"",
              "indication":indication,
              "phase":ph,
              "phaseEvidence":"SOURCE_JS_DATA",
              "programStatus":"Active",
              "sponsorOwner":company,
              "partners":[],
              "study":"",
              "trialIds":[],
              "therapeuticArea":ta,
              "sourceOwnership":clean(item.get("asset")),
              "compoundClass":clean(item.get("entity")) or clean(item.get("compound")),
              "sourcePhaseText":clean(item.get("phasetext")),
              "sourceLinks":trial_links,
              "sourceOrdinal":len(rows)+1,
              "parserMethod":"MERCK_STATIC_PIPELINE_DATA_JS",
              "sourceAdapter":ADAPTER_PROFILE,
            })

    seen=set(); dedup=[]; dups=0
    for row in rows:
        key=(row["asset"].lower(),row["indication"].lower(),row["phase"].lower())
        if key in seen:
            dups+=1; continue
        seen.add(key); row["sourceOrdinal"]=len(dedup)+1; dedup.append(row)

    issues=[]
    if len(dedup)<MIN_ROWS: issues.append(f"too few structured rows: {len(dedup)} < {MIN_ROWS}")
    if rejected: issues.append(f"{len(rejected)} source rows missing core asset/indication/phase")
    ready=not issues
    return MerckPipelineResponse(
      version=ADAPTER_PROFILE,routeVersion=ROUTE_VERSION,company=company,
      sourceUrl=source_url,finalUrl=final_url,retrievalMode="EXTERNAL_HTTP",
      readOnly=True,readyForDiscovery=ready,rowCount=len(dedup),rows=dedup,
      summary={
        "structuralValidationPass":ready,"actual":{"Total":len(dedup)},
        "productionStatus":"READY FOR AIRTABLE DELTA COMPARISON" if ready else "FAIL CLOSED - PARSER/STRUCTURE REVIEW REQUIRED",
        "selectedMethod":"MERCK_STATIC_PIPELINE_DATA_JS",
        "portfolioDependentValidation":False,"writeMode":"READ_ONLY",
      },
      issues=[{"issue":x} for x in issues],
      diagnostics={
        "groupCount":len(groups),"sourceRows":source_rows,"parsedRows":len(dedup),
        "rejectedRows":len(rejected),"rejectedSamples":rejected[:12],
        "exactDuplicatesRemoved":dups,"companySpecificParserBranch":True,
        "portfolioDependentValidation":False,"writes":0,"documentBytes":len(resp.content),
      },
      guardrails={
        "airtableWrites":False,"portfolioWrites":False,"masterDataWrites":False,
        "portfolioDependentValidation":False,"publicHttpOnly":True,
        "fuzzyIdentityResolution":False,
      }
    )


@app.get("/extract/merck-kgaa/js-pipeline/health")
async def merck_health()->Dict[str,Any]:
    return {"ok":True,"version":ADAPTER_PROFILE,"routeVersion":ROUTE_VERSION,"readOnly":True}


@app.get("/extract/merck-kgaa/js-pipeline",response_model=MerckPipelineResponse)
async def merck_route(
  company:str=Query(default="Merck KGaA",min_length=1,max_length=160),
  source_url:str=Query(default=DEFAULT_DATA_URL,min_length=8),
  timeout_seconds:float=Query(default=35.0,ge=5.0,le=35.0),
  x_adapter_key:Optional[str]=Header(default=None),
)->MerckPipelineResponse:
    _auth(x_adapter_key)
    return await extract_merck_pipeline(company,source_url,timeout_seconds)
