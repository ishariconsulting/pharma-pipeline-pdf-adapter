"""Read-only BioNTech official AEM GraphQL pipeline adapter.

Reads the React pipeline configuration embedded in BioNTech's official pipeline
page, then queries the same first-party AEM GraphQL endpoint used by the site.
No Airtable or master-data writes.
"""
from __future__ import annotations

import html as html_lib
import json
import re
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlparse

import httpx
from fastapi import Header, HTTPException, Query
from pydantic import BaseModel

from main import _auth, app
from html_fetch_extension import _assert_public_http_url
from generic_pipeline_interpreter_canary import phase_canonical


ADAPTER_PROFILE="PIPELINE_BIONTECH_AEM_GRAPHQL_V1"
ROUTE_VERSION="BIONTECH_AEM_GRAPHQL_PIPELINE_V1.0_READ_ONLY"
MIN_ROWS=8
MAX_BYTES=8_000_000

DEFAULT_SOURCE_URL="https://www.biontech.com/int/en/home/pipeline-and-products/pipeline.html"

PIPELINE_QUERY=r"""
query GetPipelineContent($pipelinePath: String!, $directoryPath: ID!) {
  pipelineByPath(_path: $pipelinePath) {
    item {
      _path
      enableProductShare
      enableIndicationShare
      therapeuticAreaRef {
        _path
        name
        productCandidateRef {
          _path
          id
          candidateName
          created
          updated
          showAsCombination
          tag {
            id
            label
          }
          metaDataRef {
            _path
            name
            target
            rights
            collaboratorRef {
              _path
              name
            }
            drugClassRef {
              _path
              longName
              shortName
              abbreviation
            }
            drugSubClassRef {
              _path
              longName
              shortName
            }
            platformRef {
              _path
              platformName
              identifierId
            }
          }
          indicationRef {
            _path
            id
            name
            phase
            phaseStage
            diseaseRef {
              _path
              label
              type
            }
          }
        }
      }
    }
  }
  therapeuticAreaList(
    filter: {
      _path: {
        _expressions: [
          { value: $directoryPath, _operator: STARTS_WITH }
        ]
      }
    }
  ) {
    items { _path name }
  }
  diseaseList(
    filter: {
      _path: {
        _expressions: [
          { value: $directoryPath, _operator: STARTS_WITH }
        ]
      }
    }
  ) {
    items { _path label type }
  }
}
"""


class BioNTechPipelineResponse(BaseModel):
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


def uniq(values:Iterable[Any])->List[str]:
    out=[]; seen=set()
    for raw in values:
        value=clean(raw)
        key=value.lower()
        if value and key not in seen:
            seen.add(key); out.append(value)
    return out


def first_dict(value:Any)->Dict[str,Any]:
    if isinstance(value,dict):
        return value
    if isinstance(value,list):
        for item in value:
            if isinstance(item,dict):
                return item
    return {}


def canonical_stage(phase:Any, phase_stage:Any="")->str:
    raw=clean(phase)
    n=re.sub(r"[^a-z0-9]+","",raw.lower())

    if n in {"preclinical","preclinicalphase","discovery","research"}:
        return "Preclinical"
    if n in {"commercial","approved","approval","marketed"}:
        return "Approved"
    if n in {"registration","registrational","filed","regulatoryreview"}:
        return "Filed / Registration"
    if n in {"phase12","phase1to2","phase1and2"}:
        return "Phase 2"
    if n in {"phase23","phase2to3","phase2and3"}:
        return "Phase 3"

    normalized=raw.replace("_","/").replace("-","/")
    parsed=phase_canonical(normalized)
    if parsed:
        return parsed

    stage=clean(phase_stage)
    sn=re.sub(r"[^a-z0-9]+","",stage.lower())
    if sn in {"commercial","approved","approval","marketed"}:
        return "Approved"
    if sn in {"preclinical","discovery","research"}:
        return "Preclinical"
    if sn in {"registration","registrational","filed","regulatoryreview"}:
        return "Filed / Registration"
    parsed=phase_canonical(stage.replace("_","/"))
    return parsed


def development_code(candidate_name:Any, candidate_path:Any)->str:
    text=" ".join([clean(candidate_name),clean(candidate_path)])
    patterns=[
      r"\bBNT\s*[-/]?\s*\d{2,5}\b",
      r"\bGEN\s*[-/]?\s*\d{2,5}\b",
      r"\bDB\s*[-/]?\s*\d{2,5}\b",
      r"\bYL\s*[-/]?\s*\d{2,5}\b",
      r"\bONC\s*[-/]?\s*\d{2,5}\b",
    ]
    hits=[]
    for pat in patterns:
        hits.extend(re.findall(pat,text,flags=re.I))
    return " / ".join(uniq(x.upper().replace(" ","") for x in hits[:3]))


def _extract_config(page_html:str)->Dict[str,Any]:
    for raw in re.findall(
        r'<script[^>]+type=["\']application/json["\'][^>]*>([\s\S]*?)</script>',
        page_html,
        flags=re.I,
    ):
        text=html_lib.unescape(raw).strip()
        if "_pipelineCfRef" not in text:
            continue
        try:
            payload=json.loads(text)
        except Exception:
            continue
        if isinstance(payload,dict) and payload.get("_pipelineCfRef") and payload.get("_pipelineDirectoryRef"):
            return payload
    return {}


async def extract_biontech_pipeline(
    company:str="BioNTech SE",
    source_url:str=DEFAULT_SOURCE_URL,
    timeout_seconds:float=35.0,
)->BioNTechPipelineResponse:
    await _assert_public_http_url(source_url)
    headers={
      "User-Agent":"Mozilla/5.0 BioNTechPipelineAdapter/1.0",
      "Accept":"text/html,application/json,*/*;q=0.8",
    }
    total_bytes=0

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds,connect=min(12.0,timeout_seconds)),
            follow_redirects=True,
            headers=headers,
        ) as client:
            page=await client.get(source_url)
            if page.status_code!=200:
                raise HTTPException(status_code=502,detail=f"BioNTech pipeline page returned HTTP {page.status_code}")
            total_bytes+=len(page.content)
            if total_bytes>MAX_BYTES:
                raise HTTPException(status_code=413,detail="BioNTech pipeline source exceeds size limit")
            final_url=str(page.url)
            await _assert_public_http_url(final_url)

            config=_extract_config(page.text)
            pipeline_path=clean(config.get("_pipelineCfRef"))
            directory_path=clean(config.get("_pipelineDirectoryRef"))
            if not pipeline_path or not directory_path:
                raise HTTPException(status_code=422,detail="BioNTech pipeline component refs not found")

            parsed=urlparse(final_url)
            endpoint=f"{parsed.scheme}://{parsed.netloc}/content/_cq_graphql/pipeline-v2/endpoint.json"
            await _assert_public_http_url(endpoint)

            response=await client.post(
                endpoint,
                json={
                  "query":PIPELINE_QUERY,
                  "variables":{
                    "pipelinePath":pipeline_path,
                    "directoryPath":directory_path,
                  },
                },
                headers={"Content-Type":"application/json","Accept":"application/json"},
            )
            if response.status_code!=200:
                raise HTTPException(status_code=502,detail=f"BioNTech GraphQL source returned HTTP {response.status_code}")
            total_bytes+=len(response.content)
            if total_bytes>MAX_BYTES:
                raise HTTPException(status_code=413,detail="BioNTech pipeline source exceeds size limit")
            try:
                payload=response.json()
            except Exception as exc:
                raise HTTPException(status_code=502,detail="BioNTech GraphQL source returned invalid JSON") from exc
            if payload.get("errors"):
                raise HTTPException(status_code=422,detail=f"BioNTech GraphQL query failed: {clean(payload.get('errors'))[:1000]}")
    except HTTPException:
        raise
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504,detail="BioNTech pipeline source timed out") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502,detail=f"BioNTech pipeline source fetch failed: {exc}") from exc

    data=payload.get("data") or {}
    pipeline=((data.get("pipelineByPath") or {}).get("item") or {})
    therapeutic_areas=pipeline.get("therapeuticAreaRef") or []
    if not isinstance(therapeutic_areas,list):
        raise HTTPException(status_code=422,detail="BioNTech GraphQL response missing therapeuticAreaRef[]")

    rows=[]
    rejected=[]
    candidate_count=0
    indication_count=0

    for ta in therapeutic_areas:
        if not isinstance(ta,dict):
            continue
        ta_name=clean(ta.get("name"))
        candidates=ta.get("productCandidateRef") or []
        if not isinstance(candidates,list):
            continue
        for candidate in candidates:
            if not isinstance(candidate,dict):
                continue
            candidate_count+=1
            asset=clean(candidate.get("candidateName"))
            candidate_path=clean(candidate.get("_path"))
            metadata=first_dict(candidate.get("metaDataRef"))
            collaborators=uniq(
                x.get("name") for x in (metadata.get("collaboratorRef") or []) if isinstance(x,dict)
            )
            drug_class=first_dict(metadata.get("drugClassRef"))
            drug_subclass=first_dict(metadata.get("drugSubClassRef"))
            platform=first_dict(metadata.get("platformRef"))
            tags=uniq(
                x.get("label") for x in (candidate.get("tag") or []) if isinstance(x,dict)
            )
            code=development_code(asset,candidate_path)

            indications=candidate.get("indicationRef") or []
            if not isinstance(indications,list):
                indications=[]
            for indication in indications:
                if not isinstance(indication,dict):
                    continue
                indication_count+=1
                disease_labels=uniq(
                    x.get("label") for x in (indication.get("diseaseRef") or []) if isinstance(x,dict)
                )
                indication_name=clean(indication.get("name")) or "; ".join(disease_labels)
                source_phase=clean(indication.get("phase"))
                source_phase_stage=clean(indication.get("phaseStage"))
                phase=canonical_stage(source_phase,source_phase_stage)

                if not asset or not indication_name or not phase:
                    rejected.append({
                      "candidate":asset,
                      "candidatePath":candidate_path,
                      "indication":indication_name,
                      "indicationPath":clean(indication.get("_path")),
                      "phase":source_phase,
                      "phaseStage":source_phase_stage,
                    })
                    continue

                indication_path=clean(indication.get("_path"))
                source_id=indication_path or f"{candidate_path}#{indication_count}"
                rows.append({
                  "company":company,
                  "sourceFamily":"Company Pipeline",
                  "sourceRecordId":source_id,
                  "sourceUrl":final_url,
                  "asset":asset,
                  "molecule":asset,
                  "developmentCode":code,
                  "brand":"",
                  "indication":indication_name,
                  "phase":phase,
                  "phaseEvidence":"SOURCE_GRAPHQL",
                  "programStatus":"Active",
                  "sponsorOwner":company,
                  "partners":collaborators,
                  "study":"",
                  "trialIds":[],
                  "therapeuticArea":ta_name,
                  "mechanismOfAction":clean(metadata.get("target")),
                  "drugClass":clean(drug_class.get("longName") or drug_class.get("shortName")),
                  "drugSubClass":clean(drug_subclass.get("longName") or drug_subclass.get("shortName")),
                  "platform":clean(platform.get("platformName")),
                  "rights":clean(metadata.get("rights")),
                  "sourceTags":tags,
                  "sourcePhaseText":source_phase,
                  "sourcePhaseStage":source_phase_stage,
                  "sourceCandidatePath":candidate_path,
                  "sourceIndicationPath":indication_path,
                  "sourceUpdated":clean(candidate.get("updated")),
                  "showAsCombination":bool(candidate.get("showAsCombination")),
                  "sourceOrdinal":len(rows)+1,
                  "parserMethod":"BIONTECH_AEM_GRAPHQL",
                  "sourceAdapter":ADAPTER_PROFILE,
                })

    dedup=[]
    seen=set()
    duplicates=0
    for row in rows:
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
    if not candidate_count:
        issues.append("no product candidates returned by first-party GraphQL source")
    if indication_count and len(rejected)>max(3,int(indication_count*0.15)):
        issues.append(f"too many indication rows missing core candidate/indication/stage: {len(rejected)} of {indication_count}")

    ready=not issues
    phase_counts={}
    ta_counts={}
    for row in dedup:
        phase_counts[row["phase"]]=phase_counts.get(row["phase"],0)+1
        ta_counts[row["therapeuticArea"]]=ta_counts.get(row["therapeuticArea"],0)+1

    return BioNTechPipelineResponse(
      version=ADAPTER_PROFILE,
      routeVersion=ROUTE_VERSION,
      company=company,
      sourceUrl=source_url,
      finalUrl=final_url,
      retrievalMode="EXTERNAL_HTTP",
      readOnly=True,
      readyForDiscovery=ready,
      rowCount=len(dedup),
      rows=dedup,
      summary={
        "structuralValidationPass":ready,
        "actual":{"Total":len(dedup)},
        "productionStatus":"READY FOR AIRTABLE DELTA COMPARISON" if ready else "FAIL CLOSED - PARSER/STRUCTURE REVIEW REQUIRED",
        "selectedMethod":"BIONTECH_AEM_GRAPHQL",
        "portfolioDependentValidation":False,
        "writeMode":"READ_ONLY",
      },
      issues=[{"issue":x} for x in issues],
      diagnostics={
        "pipelinePath":pipeline_path,
        "directoryPath":directory_path,
        "graphqlEndpoint":endpoint,
        "therapeuticAreaContainers":len(therapeutic_areas),
        "candidateCount":candidate_count,
        "sourceIndicationRows":indication_count,
        "parsedRowsBeforeDedup":len(rows),
        "parsedRows":len(dedup),
        "rejectedRows":len(rejected),
        "rejectedSamples":rejected[:15],
        "exactDuplicatesRemoved":duplicates,
        "phaseCounts":phase_counts,
        "therapeuticAreaCounts":ta_counts,
        "documentBytes":total_bytes,
        "companySpecificParserBranch":True,
        "portfolioDependentValidation":False,
        "writes":0,
      },
      guardrails={
        "airtableWrites":False,
        "portfolioWrites":False,
        "masterDataWrites":False,
        "companySpecificParserBranch":True,
        "portfolioDependentValidation":False,
        "publicHttpOnly":True,
        "fuzzyIdentityResolution":False,
      },
    )


@app.get("/extract/biontech/aem-graphql-pipeline/health")
async def biontech_health()->Dict[str,Any]:
    return {
      "ok":True,
      "version":ADAPTER_PROFILE,
      "routeVersion":ROUTE_VERSION,
      "readOnly":True,
    }


@app.get("/extract/biontech/aem-graphql-pipeline",response_model=BioNTechPipelineResponse)
async def biontech_route(
    company:str=Query(default="BioNTech SE",min_length=1,max_length=160),
    source_url:str=Query(default=DEFAULT_SOURCE_URL,min_length=8),
    timeout_seconds:float=Query(default=35.0,ge=5.0,le=35.0),
    x_adapter_key:Optional[str]=Header(default=None),
)->BioNTechPipelineResponse:
    _auth(x_adapter_key)
    return await extract_biontech_pipeline(company,source_url,timeout_seconds)
