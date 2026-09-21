"""Read-only Ionis pipeline JSON adapter.

Uses Ionis' public owned and partnered pipeline JSON endpoints exposed by the
official pipeline page. No Airtable or master-data writes.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import httpx
from fastapi import Header, HTTPException, Query
from pydantic import BaseModel

from main import _auth, app
from html_fetch_extension import _assert_public_http_url


ADAPTER_PROFILE="PIPELINE_IONIS_JSON_V1"
ROUTE_VERSION="IONIS_PIPELINE_JSON_V1.0_READ_ONLY"
MIN_ROWS=4
MAX_BYTES=5_000_000


class IonisPipelineResponse(BaseModel):
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


def phase(v:Any)->str:
    n=clean(v).lower()
    if n in {"1","phase 1","phase i"}: return "Phase 1"
    if n in {"2","phase 2","phase ii"}: return "Phase 2"
    if n in {"3","phase 3","phase iii"}: return "Phase 3"
    if n in {"4","phase 4","phase iv"}: return "Phase 4"
    if "approved" in n: return "Approved"
    if "filed" in n or "registration" in n: return "Filed / Registration"
    return ""


def identity(raw:Any)->Dict[str,str]:
    value=clean(raw).rstrip("*").strip()
    brand=""; molecule=""; dev=""
    parens=re.findall(r"\(([^()]{2,80})\)",value)
    if "®" in value or "™" in value:
        brand=clean(re.split(r"[®™]",value,1)[0])
        if parens:
            molecule=clean(parens[0])
    code=re.match(r"^([A-Z]{2,10}-?\d{2,7})\b",value)
    if code:
        dev=code.group(1)
    if not molecule and not dev:
        molecule=value
    return {"asset":value,"brand":brand,"molecule":molecule,"developmentCode":dev}


async def extract_ionis_pipeline(company:str, source_url:str, timeout_seconds:float=35.0)->IonisPipelineResponse:
    await _assert_public_http_url(source_url)
    parsed=urlparse(source_url)
    base=f"{parsed.scheme}://{parsed.netloc}"
    endpoints=[
      ("Owned",base+"/pipeline/independent?_format=json"),
      ("Partnered",base+"/pipeline/partnered?_format=json"),
    ]
    headers={"User-Agent":"Mozilla/5.0 IonisPipelineAdapter/1.0","Accept":"application/json,*/*;q=0.8"}
    rows=[]; endpoint_counts={}; rejected=0; total_bytes=0
    final_url=source_url

    async with httpx.AsyncClient(timeout=timeout_seconds,follow_redirects=True,headers=headers) as client:
      for family,url in endpoints:
        await _assert_public_http_url(url)
        try:
          resp=await client.get(url)
        except httpx.TimeoutException as exc:
          raise HTTPException(status_code=504,detail=f"Ionis {family} endpoint timed out") from exc
        except httpx.HTTPError as exc:
          raise HTTPException(status_code=502,detail=f"Ionis {family} endpoint fetch failed: {exc}") from exc
        if resp.status_code!=200:
          raise HTTPException(status_code=502,detail=f"Ionis {family} endpoint returned HTTP {resp.status_code}")
        total_bytes+=len(resp.content)
        if total_bytes>MAX_BYTES:
          raise HTTPException(status_code=413,detail="Ionis pipeline JSON exceeds size limit")
        try:
          data=resp.json()
        except Exception as exc:
          raise HTTPException(status_code=502,detail=f"Ionis {family} endpoint returned invalid JSON") from exc
        if not isinstance(data,list):
          raise HTTPException(status_code=422,detail=f"Ionis {family} endpoint is not a JSON list")
        endpoint_counts[family]=len(data)
        final_url=str(resp.url)
        for item in data:
          if not isinstance(item,dict):
            rejected+=1; continue
          ident=identity(item.get("drug_name"))
          indication=clean(item.get("disease"))
          ph=phase(item.get("phase"))
          ta=clean(item.get("therapeutic_area"))
          partner=item.get("partner")
          if not ident["asset"] or not indication or not ph:
            rejected+=1; continue
          partners=[]
          if isinstance(partner,str) and clean(partner):
            partners=[clean(partner)]
          changed=clean(item.get("changed"))
          rows.append({
            "company":company,
            "sourceFamily":"Company Pipeline",
            "sourceRecordId":f"{family.lower()}:{clean(item.get('created')) or len(rows)+1}",
            "sourceUrl":str(resp.url),
            **ident,
            "indication":indication,
            "phase":ph,
            "phaseEvidence":"SOURCE_JSON",
            "programStatus":"Active",
            "sponsorOwner":company,
            "partners":partners,
            "study":"",
            "trialIds":[],
            "therapeuticArea":ta,
            "target":clean(item.get("generic")),
            "ownershipFamily":family,
            "sourceChanged":changed,
            "sourceOrdinal":len(rows)+1,
            "parserMethod":"IONIS_PUBLIC_PIPELINE_JSON",
            "sourceAdapter":ADAPTER_PROFILE,
          })

    seen=set(); dedup=[]; dups=0
    for row in rows:
      key=(row["asset"].lower(),row["indication"].lower(),row["phase"].lower(),row["ownershipFamily"].lower())
      if key in seen:
        dups+=1; continue
      seen.add(key); row["sourceOrdinal"]=len(dedup)+1; dedup.append(row)

    issues=[]
    if len(dedup)<MIN_ROWS: issues.append(f"too few structured rows: {len(dedup)} < {MIN_ROWS}")
    if rejected>0: issues.append(f"{rejected} endpoint rows missing core asset/indication/phase")
    ready=not issues
    return IonisPipelineResponse(
      version=ADAPTER_PROFILE,routeVersion=ROUTE_VERSION,company=company,
      sourceUrl=source_url,finalUrl=final_url,retrievalMode="EXTERNAL_HTTP",
      readOnly=True,readyForDiscovery=ready,rowCount=len(dedup),rows=dedup,
      summary={
        "structuralValidationPass":ready,"actual":{"Total":len(dedup)},
        "productionStatus":"READY FOR AIRTABLE DELTA COMPARISON" if ready else "FAIL CLOSED - PARSER/STRUCTURE REVIEW REQUIRED",
        "selectedMethod":"IONIS_PUBLIC_PIPELINE_JSON",
        "portfolioDependentValidation":False,"writeMode":"READ_ONLY",
      },
      issues=[{"issue":x} for x in issues],
      diagnostics={
        "endpointCounts":endpoint_counts,"parsedRows":len(dedup),"rejectedRows":rejected,
        "exactDuplicatesRemoved":dups,"documentBytes":total_bytes,
        "companySpecificParserBranch":True,"portfolioDependentValidation":False,"writes":0,
      },
      guardrails={
        "airtableWrites":False,"portfolioWrites":False,"masterDataWrites":False,
        "portfolioDependentValidation":False,"publicHttpOnly":True,
        "fuzzyIdentityResolution":False,
      }
    )


@app.get("/extract/ionis/json-pipeline/health")
async def ionis_health()->Dict[str,Any]:
    return {"ok":True,"version":ADAPTER_PROFILE,"routeVersion":ROUTE_VERSION,"readOnly":True}


@app.get("/extract/ionis/json-pipeline",response_model=IonisPipelineResponse)
async def ionis_route(
  company:str=Query(default="Ionis Pharmaceuticals",min_length=1,max_length=160),
  source_url:str=Query(default="https://ionis.com/science-and-innovation/pipeline",min_length=8),
  timeout_seconds:float=Query(default=35.0,ge=5.0,le=35.0),
  x_adapter_key:Optional[str]=Header(default=None),
)->IonisPipelineResponse:
    _auth(x_adapter_key)
    return await extract_ionis_pipeline(company,source_url,timeout_seconds)
