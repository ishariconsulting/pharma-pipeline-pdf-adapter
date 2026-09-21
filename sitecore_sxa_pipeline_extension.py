"""Read-only Sitecore SXA search-result pipeline adapter.

Parses machine-readable Sitecore SXA search JSON where each result contains
semantic pipeline HTML. The source URL carries the Sitecore search parameters;
no company-specific endpoint constants or Portfolio state are used.
"""
from __future__ import annotations

import html as html_lib
import re
from typing import Any, Dict, List, Optional

import httpx
from fastapi import Header, HTTPException, Query
from pydantic import BaseModel

from main import _auth, app
from html_fetch_extension import _assert_public_http_url
from generic_pipeline_interpreter_canary import phase_canonical


ADAPTER_PROFILE="PIPELINE_SITECORE_SXA_JSON_V1"
ROUTE_VERSION="SITECORE_SXA_PIPELINE_V1.0_READ_ONLY"
MIN_ROWS=4
MAX_BYTES=5_000_000


class SitecorePipelineResponse(BaseModel):
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


def text_only(raw:str)->str:
    s=html_lib.unescape(raw or "")
    s=re.sub(r"<script\b[^>]*>[\s\S]*?</script>"," ",s,flags=re.I)
    s=re.sub(r"<style\b[^>]*>[\s\S]*?</style>"," ",s,flags=re.I)
    s=re.sub(r"<[^>]+>"," ",s)
    return clean(s)


def class_text(raw:str, class_name:str)->str:
    # Semantic Sitecore renderings commonly wrap each field in a class named
    # after the field. Keep this generic by taking field class names as the
    # source contract rather than company-specific labels.
    pattern=r'class=["\'][^"\']*\b'+re.escape(class_name)+r'\b[^"\']*["\'][^>]*>([\s\S]*?)</(?:div|span|p|h[1-6])>'
    m=re.search(pattern,raw,re.I)
    return text_only(m.group(1)) if m else ""


def identity_parts(raw_asset:str)->Dict[str,str]:
    asset=clean(raw_asset)
    brand=""
    molecule=""
    development=""
    # First code-like token containing digits is safe as a development-code
    # candidate without assuming a company prefix.
    m=re.search(r"\b([A-Z]{2,10}-?\d{2,7})\b",asset)
    if m:
        development=m.group(1)
    # Parenthetical lowercase/proper-name identity often carries INN; preserve
    # only when it is not the extracted code/study token.
    parens=re.findall(r"\(([^()]{2,80})\)",asset)
    for p in parens:
        p=clean(p)
        if p and p!=development and not re.search(r"\d",p):
            if len(p.split())<=5:
                molecule=p
                break
    if "®" in asset or "™" in asset:
        brand=clean(re.split(r"[®™]",asset,1)[0])
    return {"asset":asset,"brand":brand,"molecule":molecule,"developmentCode":development}


async def extract_sitecore_sxa(company:str, source_url:str, timeout_seconds:float=35.0)->SitecorePipelineResponse:
    await _assert_public_http_url(source_url)
    headers={
      "User-Agent":"Mozilla/5.0 SitecorePipelineAdapter/1.0",
      "Accept":"application/json,*/*;q=0.8",
    }
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds,follow_redirects=True,headers=headers) as client:
            resp=await client.get(source_url)
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504,detail="Sitecore pipeline source timed out") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502,detail=f"Sitecore pipeline source fetch failed: {exc}") from exc
    if resp.status_code!=200:
        raise HTTPException(status_code=502,detail=f"Sitecore pipeline source returned HTTP {resp.status_code}")
    if len(resp.content)>MAX_BYTES:
        raise HTTPException(status_code=413,detail="Sitecore pipeline JSON exceeds size limit")
    final_url=str(resp.url)
    await _assert_public_http_url(final_url)
    try:
        data=resp.json()
    except Exception as exc:
        raise HTTPException(status_code=502,detail="Sitecore pipeline source returned invalid JSON") from exc

    results=data.get("Results") if isinstance(data,dict) else None
    if not isinstance(results,list):
        raise HTTPException(status_code=422,detail="Sitecore JSON does not contain Results[]")

    rows=[]
    rejected=0
    for idx,item in enumerate(results,1):
        if not isinstance(item,dict):
            rejected+=1; continue
        raw=str(item.get("Html") or "")
        asset_raw=class_text(raw,"field-headbrandname")
        indication=class_text(raw,"field-potentialindication")
        phase_raw=class_text(raw,"phase-name")
        ta=class_text(raw,"field-therapeuticareaname")
        phase=phase_canonical(phase_raw)
        if phase_raw.strip().lower()=="approved":
            phase="Approved"
        identity=identity_parts(asset_raw)
        if not identity["asset"] or not indication or not phase:
            rejected+=1; continue
        row={
          "company":company,
          "sourceFamily":"Company Pipeline",
          "sourceRecordId":clean(item.get("Id")) or f"sxa:{idx}",
          "sourceUrl":final_url,
          **identity,
          "indication":indication,
          "phase":phase,
          "phaseEvidence":"SOURCE_JSON_HTML",
          "programStatus":"Active",
          "sponsorOwner":company,
          "partners":[],
          "study":"",
          "trialIds":[],
          "therapeuticArea":ta,
          "sourceOrdinal":len(rows)+1,
          "parserMethod":"SITECORE_SXA_SEMANTIC_FIELDS",
          "sourceAdapter":ADAPTER_PROFILE,
        }
        rows.append(row)

    # Exact source-grain duplicate check.
    seen=set(); dedup=[]; dups=0
    for row in rows:
        key=(row["asset"].lower(),row["indication"].lower(),row["phase"].lower())
        if key in seen:
            dups+=1; continue
        seen.add(key); row["sourceOrdinal"]=len(dedup)+1; dedup.append(row)

    issues=[]
    if len(dedup)<MIN_ROWS: issues.append(f"too few structured rows: {len(dedup)} < {MIN_ROWS}")
    source_count=data.get("Count") if isinstance(data,dict) else None
    if isinstance(source_count,int) and source_count>0 and (len(dedup)+rejected)<min(source_count,100):
        issues.append("source result accounting mismatch")
    # Rejection is tolerated for non-program result cards only when enough core
    # rows survive; large rejection rates fail closed.
    if rejected>max(5,int(max(1,len(dedup))*0.25)):
        issues.append(f"too many source results rejected structurally: {rejected}")

    ready=not issues
    diagnostics={
      "sourceCount":source_count,
      "resultCount":len(results),
      "parsedRows":len(dedup),
      "rejectedResults":rejected,
      "exactDuplicatesRemoved":dups,
      "portfolioDependentValidation":False,
      "companySpecificParserBranch":False,
      "writes":0,
    }
    return SitecorePipelineResponse(
      version=ADAPTER_PROFILE,routeVersion=ROUTE_VERSION,company=company,
      sourceUrl=source_url,finalUrl=final_url,retrievalMode="EXTERNAL_HTTP",
      readOnly=True,readyForDiscovery=ready,rowCount=len(dedup),rows=dedup,
      summary={
        "structuralValidationPass":ready,
        "actual":{"Total":len(dedup)},
        "productionStatus":"READY FOR AIRTABLE DELTA COMPARISON" if ready else "FAIL CLOSED - PARSER/STRUCTURE REVIEW REQUIRED",
        "selectedMethod":"SITECORE_SXA_SEMANTIC_FIELDS",
        "portfolioDependentValidation":False,
        "writeMode":"READ_ONLY",
      },
      issues=[{"issue":x} for x in issues],
      diagnostics=diagnostics,
      guardrails={
        "airtableWrites":False,"portfolioWrites":False,"masterDataWrites":False,
        "companySpecificParserBranch":False,"portfolioDependentValidation":False,
        "publicHttpOnly":True,"fuzzyIdentityResolution":False,
      }
    )


@app.get("/extract/generic/sitecore-sxa-pipeline/health")
async def sitecore_health()->Dict[str,Any]:
    return {"ok":True,"version":ADAPTER_PROFILE,"routeVersion":ROUTE_VERSION,"readOnly":True}


@app.get("/extract/generic/sitecore-sxa-pipeline",response_model=SitecorePipelineResponse)
async def sitecore_route(
  company:str=Query(...,min_length=1,max_length=160),
  source_url:str=Query(...,min_length=8),
  timeout_seconds:float=Query(default=35.0,ge=5.0,le=35.0),
  x_adapter_key:Optional[str]=Header(default=None),
)->SitecorePipelineResponse:
    _auth(x_adapter_key)
    return await extract_sitecore_sxa(company,source_url,timeout_seconds)
