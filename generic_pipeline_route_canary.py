"""Read-only source-endpoint diagnostics for unresolved pipeline sources."""
import asyncio, json, re
from urllib.parse import urlencode
import httpx
from generic_pipeline_extension import _extract_generic_pipeline

HEADERS={"User-Agent":"Mozilla/5.0 GenericPipelineEndpointDiagnostic/1.0","Accept":"text/html,application/json,*/*;q=0.8"}

async def amgen():
    url="https://www.amgenpipeline.com/"
    try:
        r=await _extract_generic_pipeline(company="Amgen",source_url=url,timeout_seconds=28.0)
        print("AMGEN_PIPELINE_CANARY "+json.dumps({
          "readyForDiscovery":r.readyForDiscovery,"rowCount":r.rowCount,
          "retrievalMode":r.summary.get("retrievalMode"),
          "selectedMethod":r.summary.get("selectedMethod"),
          "issues":[x.get("issue") for x in r.issues],
          "diagnostics":r.diagnostics,
          "sampleRows":r.rows[:8]
        },ensure_ascii=False),flush=True)
    except Exception as exc:
        print("AMGEN_PIPELINE_CANARY "+json.dumps({"error":f"{type(exc).__name__}: {exc}"},ensure_ascii=False),flush=True)

async def gilead():
    base="https://www.gilead.com/sxa/search/results/"
    params={
      "v":"{16E72BF3-7230-403E-BB34-EAE20C26BD0F}",
      "s":"{B5AA5689-719C-4965-8E20-4B67741FF639}",
      "l":"en","p":"100",
      "defaultSortOrder":"Pipeline Therapeutic Areas,Descending",
      "sig":"pipeline",
      "itemid":"{EFC74AF2-1C5C-4D7C-BACD-F20CD4FF35AA}",
      "autoFireSearch":"true"
    }
    try:
        async with httpx.AsyncClient(timeout=28.0,follow_redirects=True,headers=HEADERS) as c:
            r=await c.get(base,params=params)
        body=r.text
        try: parsed=r.json()
        except Exception: parsed=None
        print("GILEAD_SXA_PROBE "+json.dumps({
          "status":r.status_code,"finalUrl":str(r.url),
          "contentType":r.headers.get("content-type"),
          "chars":len(body),
          "jsonType":type(parsed).__name__ if parsed is not None else None,
          "jsonKeys":list(parsed.keys())[:30] if isinstance(parsed,dict) else None,
          "head":re.sub(r"\s+"," ",body[:5000])[:5000]
        },ensure_ascii=False),flush=True)
    except Exception as exc:
        print("GILEAD_SXA_PROBE "+json.dumps({"error":f"{type(exc).__name__}: {exc}"},ensure_ascii=False),flush=True)

async def ionis():
    urls=[
      "https://ionis.com/themes/custom/envivent/components/ionis-pipeline-block-v2/ionis-pipeline-block-v2.js?v=1",
      "https://ionis.com/science-and-innovation/drupal-settings-json",
    ]
    async with httpx.AsyncClient(timeout=28.0,follow_redirects=True,headers=HEADERS) as c:
      for url in urls:
        try:
          r=await c.get(url)
          body=r.text
          snippets=[]
          for pat in [r"fetch\s*\([^\)]{0,500}\)",r"ajax[^\n;]{0,500}",r"https?://[^\"'\s]+",r"/[^\"'\s]+\.pdf",r"/[^\"'\s]*(?:pipeline|api|ajax|download)[^\"'\s]*"]:
            for m in re.finditer(pat,body,re.I):
              s=re.sub(r"\s+"," ",m.group(0))
              if s not in snippets: snippets.append(s[:700])
              if len(snippets)>=80: break
            if len(snippets)>=80: break
          print("IONIS_ENDPOINT_PROBE "+json.dumps({
            "url":url,"status":r.status_code,"contentType":r.headers.get("content-type"),
            "chars":len(body),"snippets":snippets[:80],
            "head":re.sub(r"\s+"," ",body[:4000])[:4000]
          },ensure_ascii=False),flush=True)
        except Exception as exc:
          print("IONIS_ENDPOINT_PROBE "+json.dumps({"url":url,"error":f"{type(exc).__name__}: {exc}"},ensure_ascii=False),flush=True)

async def main():
    await amgen()
    await gilead()
    await ionis()

if __name__=="__main__":
    asyncio.run(main())
