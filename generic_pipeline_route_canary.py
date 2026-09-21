"""Read-only Menarini adapter validation + browser structural probes."""
import asyncio, json, os, re
import httpx
from menarini_graphql_pipeline_extension import extract_menarini_pipeline

MENARINI="https://www.menarini.com/en-us/innovation-research/our-pipeline-and-products.html"
BROWSER_SOURCES=[
 ("BioNTech SE","https://www.biontech.com/int/en/home/pipeline-and-products/pipeline.html"),
 ("Menarini Group",MENARINI),
 ("Johnson & Johnson","https://www.investor.jnj.com/pipeline/development-pipeline/default.aspx"),
 ("Wave Life Sciences","https://wavelifesciences.com/pipeline/research-and-development/"),
 ("Vertex Pharmaceuticals","https://www.vrtx.com/our-science/pipeline/"),
]
SIG=re.compile(r"phase\s*[123]|registration|approved|pipeline|indication|oncology|program|programme",re.I)

def clean(x): return re.sub(r"\s+"," ",str(x or "")).strip()

async def menarini():
    try:
        r=await extract_menarini_pipeline("Menarini Group",MENARINI,35.0)
        print("MENARINI_ADAPTER_CANARY "+json.dumps({
          "readyForDiscovery":r.readyForDiscovery,"rowCount":r.rowCount,
          "issues":[x.get("issue") for x in r.issues],
          "summary":r.summary,"diagnostics":r.diagnostics,
          "sample":r.rows[:12],"masterWrites":0
        },ensure_ascii=False),flush=True)
    except Exception as exc:
        print("MENARINI_ADAPTER_CANARY "+json.dumps({"readyForDiscovery":False,"error":f"{type(exc).__name__}: {exc}","masterWrites":0},ensure_ascii=False),flush=True)

async def browser():
    base=os.getenv("BROWSER_FETCH_BASE_URL","").strip().rstrip("/")
    key=os.getenv("BROWSER_FETCH_KEY","").strip()
    if not base or not key:
        print("BROWSER_PIPELINE_PROBE "+json.dumps({"configured":False}),flush=True); return
    async with httpx.AsyncClient(timeout=50.0,follow_redirects=True) as c:
      for company,url in BROWSER_SOURCES:
        try:
          rr=await c.get(base+"/fetch/browser",params={"url":url,"timeout_seconds":28},headers={"X-Browser-Key":key})
          data=None
          try:data=rr.json()
          except Exception:pass
          if not isinstance(data,dict):
            print("BROWSER_PIPELINE_PROBE "+json.dumps({"company":company,"status":rr.status_code,"contentType":rr.headers.get("content-type"),"head":clean(rr.text[:800])},ensure_ascii=False),flush=True)
            continue
          lines=data.get("visibleLines") or []
          tables=data.get("tables") or []
          signal=[clean(x) for x in lines if SIG.search(str(x))][:35]
          table_samples=[]
          for ti,t in enumerate(tables[:8]):
            table_samples.append({"table":ti,"rows":[[clean(c) for c in row[:12]] for row in t[:8]]})
          print("BROWSER_PIPELINE_PROBE "+json.dumps({
            "company":company,"status":rr.status_code,"browserVersion":data.get("version"),
            "httpStatus":data.get("httpStatus"),"finalUrl":data.get("finalUrl"),
            "title":data.get("title"),"visibleTextLength":data.get("visibleTextLength"),
            "visibleLines":len(lines),"tables":len(tables),
            "signalLines":signal,"tableSamples":table_samples,
          },ensure_ascii=False),flush=True)
        except Exception as exc:
          print("BROWSER_PIPELINE_PROBE "+json.dumps({"company":company,"error":f"{type(exc).__name__}: {exc}"},ensure_ascii=False),flush=True)

async def main():
    await menarini()
    await browser()

if __name__=="__main__":
    asyncio.run(main())
