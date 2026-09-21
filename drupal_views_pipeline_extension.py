"""Reusable read-only Drupal Views pipeline adapter.

Parses server-rendered Drupal pipeline pages where an indication/condition
container owns repeated views rows with semantic medicine-name and phase
fields. No company-specific names, IDs, coordinates, or Portfolio state.
"""
from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional, Tuple

import httpx
from fastapi import Header, HTTPException, Query
from pydantic import BaseModel

from main import _auth, app
from html_fetch_extension import _assert_public_http_url
from generic_pipeline_interpreter_canary import phase_canonical


ADAPTER_PROFILE="PIPELINE_DRUPAL_VIEWS_V1"
ROUTE_VERSION="DRUPAL_VIEWS_PIPELINE_V1.0_READ_ONLY"
MIN_ROWS=4
MAX_BYTES=5_000_000


def clean(v:Any)->str:
    return re.sub(r"\s+"," ",str(v or "")).strip()


class DrupalPipelineResponse(BaseModel):
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


class DrupalViewsParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack: List[Dict[str,Any]]=[]
        self.condition_depth: Optional[int]=None
        self.condition=""
        self.condition_capture_depth: Optional[int]=None
        self.condition_parts: List[str]=[]
        self.row_depth: Optional[int]=None
        self.row_asset_depth: Optional[int]=None
        self.row_phase_depth: Optional[int]=None
        self.row_asset_parts: List[str]=[]
        self.row_phase_parts: List[str]=[]
        self.rows: List[Dict[str,str]]=[]
        self.condition_count=0
        self.raw_row_count=0

    @staticmethod
    def _classes(attrs)->set[str]:
        d=dict(attrs)
        return set(clean(d.get("class")).split())

    def handle_starttag(self,tag,attrs):
        classes=self._classes(attrs)
        self.stack.append({"tag":tag,"classes":classes})
        depth=len(self.stack)

        if tag=="div" and "overall-wrapper" in classes and self.condition_depth is None:
            self.condition_depth=depth
            self.condition=""
            self.condition_count+=1

        if self.condition_depth is not None and tag in {"h1","h2","h3","h4","h5","h6","div","span"} and "field-title" in classes:
            self.condition_capture_depth=depth
            self.condition_parts=[]

        if self.condition_depth is not None and tag=="div" and "views-row" in classes and "medicine" in classes:
            self.row_depth=depth
            self.raw_row_count+=1
            self.row_asset_parts=[]
            self.row_phase_parts=[]

        if self.row_depth is not None and tag=="div":
            if "views-field-field-medicine-name" in classes:
                self.row_asset_depth=depth
            if "views-field-field-phase" in classes:
                self.row_phase_depth=depth

    def handle_data(self,data):
        txt=clean(data)
        if not txt:
            return
        depth=len(self.stack)
        if self.condition_capture_depth is not None and depth>=self.condition_capture_depth:
            self.condition_parts.append(txt)
        if self.row_asset_depth is not None and depth>=self.row_asset_depth:
            self.row_asset_parts.append(txt)
        if self.row_phase_depth is not None and depth>=self.row_phase_depth:
            self.row_phase_parts.append(txt)

    def handle_endtag(self,tag):
        depth=len(self.stack)

        if self.condition_capture_depth is not None and depth==self.condition_capture_depth:
            value=clean(" ".join(self.condition_parts))
            if value:
                self.condition=value
            self.condition_capture_depth=None
            self.condition_parts=[]

        if self.row_asset_depth is not None and depth==self.row_asset_depth:
            self.row_asset_depth=None
        if self.row_phase_depth is not None and depth==self.row_phase_depth:
            self.row_phase_depth=None

        if self.row_depth is not None and depth==self.row_depth:
            asset=clean(" ".join(self.row_asset_parts))
            phase_text=clean(" ".join(self.row_phase_parts))
            self.rows.append({
                "asset":asset,
                "indication":self.condition,
                "phaseText":phase_text,
            })
            self.row_depth=None
            self.row_asset_depth=None
            self.row_phase_depth=None
            self.row_asset_parts=[]
            self.row_phase_parts=[]

        if self.condition_depth is not None and depth==self.condition_depth:
            self.condition_depth=None
            self.condition=""
            self.condition_capture_depth=None

        if self.stack:
            self.stack.pop()


def canonical_phase(raw:Any)->str:
    s=clean(raw)
    # Source often prints display label + machine class, e.g.
    # "Phase 2 phase_2". Prefer the display label.
    m=re.search(r"\bPhase\s*(1/2|2/3|1/2/3|[1-4])\b",s,re.I)
    if m:
        token=m.group(1)
        nums=[int(x) for x in token.split("/")]
        return f"Phase {max(nums)}"
    n=s.lower()
    if "approved" in n or "commercial" in n: return "Approved"
    if "registration" in n or "filed" in n: return "Filed / Registration"
    if "preclinical" in n or "pre-clinical" in n: return "Preclinical"
    return phase_canonical(s)


async def extract_drupal_views(company:str,source_url:str,timeout_seconds:float=35.0)->DrupalPipelineResponse:
    await _assert_public_http_url(source_url)
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds,connect=min(12.0,timeout_seconds)),
            follow_redirects=True,
            headers={"User-Agent":"Mozilla/5.0 DrupalPipelineAdapter/1.0","Accept":"text/html,*/*;q=0.8"},
        ) as client:
            resp=await client.get(source_url)
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504,detail="Drupal pipeline source timed out") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502,detail=f"Drupal pipeline source fetch failed: {exc}") from exc
    if resp.status_code!=200:
        raise HTTPException(status_code=502,detail=f"Drupal pipeline source returned HTTP {resp.status_code}")
    if len(resp.content)>MAX_BYTES:
        raise HTTPException(status_code=413,detail="Drupal pipeline source exceeds size limit")
    final_url=str(resp.url)
    await _assert_public_http_url(final_url)

    parser=DrupalViewsParser()
    parser.feed(resp.text)

    parsed=[]; rejected=[]
    for idx,item in enumerate(parser.rows,1):
        asset=clean(item.get("asset"))
        indication=clean(item.get("indication"))
        ph=canonical_phase(item.get("phaseText"))
        if not asset or not indication or not ph:
            rejected.append({"ordinal":idx,**item,"canonicalPhase":ph})
            continue
        parsed.append({
          "company":company,
          "sourceFamily":"Company Pipeline",
          "sourceRecordId":f"drupal:{idx}",
          "sourceUrl":final_url,
          "asset":asset,
          "molecule":asset,
          "developmentCode":"",
          "brand":"",
          "indication":indication,
          "phase":ph,
          "phaseEvidence":"SOURCE_HTML_SEMANTIC_FIELD",
          "programStatus":"Active",
          "sponsorOwner":company,
          "partners":[],
          "study":"",
          "trialIds":[],
          "therapeuticArea":"",
          "sourceOrdinal":len(parsed)+1,
          "parserMethod":"DRUPAL_VIEWS_SEMANTIC_FIELDS",
          "sourceAdapter":ADAPTER_PROFILE,
        })

    seen=set(); dedup=[]; dups=0
    for row in parsed:
        key=(row["asset"].lower(),row["indication"].lower(),row["phase"].lower())
        if key in seen:
            dups+=1; continue
        seen.add(key); row["sourceOrdinal"]=len(dedup)+1; dedup.append(row)

    issues=[]
    if len(dedup)<MIN_ROWS:
        issues.append(f"too few structured rows: {len(dedup)} < {MIN_ROWS}")
    # Research-only rows are expected on some pipeline pages; reject them from
    # the clinical stage output without failing the whole source. Missing asset
    # or indication is not expected and remains a structural warning.
    bad_rejections=[
      x for x in rejected
      if x.get("asset") and x.get("indication") and clean(x.get("phaseText")).lower().startswith("research") is False
    ]
    if bad_rejections:
        issues.append(f"{len(bad_rejections)} non-research source rows could not be normalized")

    ready=not issues
    return DrupalPipelineResponse(
      version=ADAPTER_PROFILE,routeVersion=ROUTE_VERSION,company=company,
      sourceUrl=source_url,finalUrl=final_url,retrievalMode="DIRECT",readOnly=True,
      readyForDiscovery=ready,rowCount=len(dedup),rows=dedup,
      summary={
        "structuralValidationPass":ready,"actual":{"Total":len(dedup)},
        "productionStatus":"READY FOR AIRTABLE DELTA COMPARISON" if ready else "FAIL CLOSED - PARSER/STRUCTURE REVIEW REQUIRED",
        "selectedMethod":"DRUPAL_VIEWS_SEMANTIC_FIELDS",
        "portfolioDependentValidation":False,"companySpecificParserBranch":False,"writeMode":"READ_ONLY",
      },
      issues=[{"issue":x} for x in issues],
      diagnostics={
        "conditionContainers":parser.condition_count,"sourceRows":parser.raw_row_count,
        "parsedRows":len(dedup),"rejectedRows":len(rejected),
        "nonResearchRejectedRows":len(bad_rejections),"exactDuplicatesRemoved":dups,
        "rejectedSamples":rejected[:12],"companySpecificParserBranch":False,
        "portfolioDependentValidation":False,"writes":0,
      },
      guardrails={
        "airtableWrites":False,"portfolioWrites":False,"masterDataWrites":False,
        "companySpecificParserBranch":False,"portfolioDependentValidation":False,
        "publicHttpOnly":True,"fuzzyIdentityResolution":False,
      }
    )


@app.get("/extract/generic/drupal-views-pipeline/health")
async def drupal_health()->Dict[str,Any]:
    return {"ok":True,"version":ADAPTER_PROFILE,"routeVersion":ROUTE_VERSION,"readOnly":True}


@app.get("/extract/generic/drupal-views-pipeline",response_model=DrupalPipelineResponse)
async def drupal_route(
  company:str=Query(...,min_length=1,max_length=160),
  source_url:str=Query(...,min_length=8),
  timeout_seconds:float=Query(default=35.0,ge=5.0,le=35.0),
  x_adapter_key:Optional[str]=Header(default=None),
)->DrupalPipelineResponse:
    _auth(x_adapter_key)
    return await extract_drupal_views(company,source_url,timeout_seconds)
