"""Read-only canary for Merck JS adapter and BioNTech dynamic pipeline bundle."""
import asyncio, json, re
import httpx
from merck_kgaa_js_pipeline_extension import extract_merck_pipeline

MERCK="https://www.emdgroup.com/content/dam/scripts/group/en/pipeline/data.js"
BIO_CHUNKS=[
 "https://www.biontech.com/etc.clientlibs/biontech-xp-nova/clientlibs/clientlib-site-main/resources/chunks/463-3ed4eb7b5b7fb87822ef.chunk.js",
 "https://www.biontech.com/etc.clientlibs/biontech-xp-nova/clientlibs/clientlib-site-main/resources/chunks/957-4b96009fdf26cdb60ffc.chunk.js",
 "https://www.biontech.com/etc.clientlibs/biontech-xp-nova/clientlibs/clientlib-site-main/resources/chunks/961-920e1b859f8a47a1a73d.chunk.js",
 "https://www.biontech.com/etc.clientlibs/biontech-xp-nova/clientlibs/clientlib-site-main/resources/chunks/290-96863120dae45dad63fa.chunk.js",
]

def compact(v): return re.sub(r"\s+"," ",str(v or "")).strip()

async def main():
  try:
    r=await extract_merck_pipeline("Merck KGaA",MERCK,35.0)
    print("MERCK_JS_CANARY "+json.dumps({
      "readyForDiscovery":r.readyForDiscovery,"rowCount":r.rowCount,
      "issues":[x.get("issue") for x in r.issues],"diagnostics":r.diagnostics,
      "phaseCounts":{p:sum(1 for x in r.rows if x["phase"]==p) for p in sorted(set(x["phase"] for x in r.rows))},
      "taCounts":{p:sum(1 for x in r.rows if x["therapeuticArea"]==p) for p in sorted(set(x["therapeuticArea"] for x in r.rows))},
      "sample":r.rows[:12],"masterWrites":0
    },ensure_ascii=False),flush=True)
  except Exception as exc:
    print("MERCK_JS_CANARY "+json.dumps({"readyForDiscovery":False,"error":f"{type(exc).__name__}: {exc}","masterWrites":0}),flush=True)

  async with httpx.AsyncClient(timeout=35,follow_redirects=True,headers={"User-Agent":"Mozilla/5.0 BioNTechChunkCanary/1.0"}) as c:
    out=[]
    for url in BIO_CHUNKS:
      try:
        rr=await c.get(url); body=rr.text; low=body.lower()
        snippets=[]
        for key in ["pipelinecfref","pipelinedirectoryref","contentfragment","content-fragment","graphql","model.json","adobe","cfmodel","_url","fetch("]:
          pos=0
          for _ in range(10):
            i=low.find(key.lower(),pos)
            if i<0: break
            snippets.append({"key":key,"text":compact(body[max(0,i-800):i+2600])[:3400]})
            pos=i+len(key)
        out.append({"url":url,"status":rr.status_code,"chars":len(body),"snippets":snippets[:35]})
      except Exception as exc:
        out.append({"url":url,"error":f"{type(exc).__name__}: {exc}"})
    print("BIONTECH_CHUNK_CONTRACT "+json.dumps(out,ensure_ascii=False),flush=True)

if __name__=="__main__":
  asyncio.run(main())
