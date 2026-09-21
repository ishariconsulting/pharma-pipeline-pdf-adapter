"""Read-only parser fit + Merck source-contract canary."""
import asyncio, json, re
import httpx
from generic_pipeline_extension import _extract_generic_pipeline

SOURCES=[
 ("Merck KGaA","https://www.emdgroup.com/en/research/healthcare-pipeline.html"),
 ("BioNTech SE","https://www.biontech.com/int/en/home/pipeline-and-products/pipeline.html"),
 ("Vertex Pharmaceuticals","https://www.vrtx.com/our-science/pipeline/"),
]
MERCK_SCRIPT="https://www.emdgroup.com/content/dam/scripts/group/en/pipeline/script.js"

def compact(s): return re.sub(r"\s+"," ",str(s or "")).strip()

async def parser_one(company,url):
    try:
      r=await _extract_generic_pipeline(company=company,source_url=url,timeout_seconds=30.0)
      print("PARSER_FIT "+json.dumps({
        "company":company,"readyForDiscovery":r.readyForDiscovery,"rowCount":r.rowCount,
        "retrievalMode":r.summary.get("retrievalMode"),
        "routingReason":r.summary.get("routingReason"),
        "selectedMethod":r.summary.get("selectedMethod"),
        "issues":[x.get("issue") for x in r.issues],
        "diagnostics":r.diagnostics,
        "sampleRows":r.rows[:12],
        "masterWrites":0,
      },ensure_ascii=False),flush=True)
    except Exception as exc:
      print("PARSER_FIT "+json.dumps({
        "company":company,"readyForDiscovery":False,
        "error":f"{type(exc).__name__}: {exc}","masterWrites":0
      },ensure_ascii=False),flush=True)

async def merck_script():
    async with httpx.AsyncClient(timeout=30.0,follow_redirects=True,headers={"User-Agent":"Mozilla/5.0 PipelineScriptCanary/1.0"}) as c:
      r=await c.get(MERCK_SCRIPT)
      body=r.text
    urls=[]
    for m in re.finditer(r'''["']([^"'\s]{3,600})["']''',body):
      v=m.group(1)
      lv=v.lower()
      if any(k in lv for k in ["json","pipeline","ajax","api","csv","xml",".jpg",".png"]):
        if v not in urls: urls.append(v)
    snippets=[]
    low=body.lower()
    for k in ["ajax","getjson","fetch(","pipeline","json","data-"]:
      pos=0
      for _ in range(12):
        i=low.find(k,pos)
        if i<0: break
        snippets.append({"key":k,"text":compact(body[max(0,i-450):i+1500])[:1950]})
        pos=i+len(k)
    print("MERCK_SCRIPT_CONTRACT "+json.dumps({
      "status":r.status_code,"chars":len(body),"candidateValues":urls[:120],
      "snippets":snippets[:40]
    },ensure_ascii=False),flush=True)

async def main():
    for c,u in SOURCES:
      await parser_one(c,u)
    await merck_script()

if __name__=="__main__":
    asyncio.run(main())
