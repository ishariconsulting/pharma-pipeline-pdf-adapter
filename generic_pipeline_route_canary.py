"""Read-only machine-source probes for Menarini, BioNTech and Biogen."""
import asyncio, json, re, html as html_lib
from urllib.parse import urljoin
import httpx

HEADERS={"User-Agent":"Mozilla/5.0 PipelineMachineSourceProbe/1.0","Accept":"application/json,text/html,*/*;q=0.8"}

MENARINI_BASE="https://www.menarini.com"
MENARINI_FRAGMENTS=[
 "/content/dam/menarini-com/content-fragments/en_us/pipeline-tables/pipeline-and-products/oncology-(focus-on-compound)",
 "/content/dam/menarini-com/content-fragments/en_us/pipeline-tables/pipeline-and-products/oncology-(focus-on-indication)",
 "/content/dam/menarini-com/content-fragments/en_us/pipeline-tables/pipeline-and-products/anti-infectives-table-1",
 "/content/dam/menarini-com/content-fragments/en_us/pipeline-tables/pipeline-and-products/anti-infectives-table-2",
 "/content/dam/menarini-com/content-fragments/en_us/pipeline-tables/pipeline-and-products/cardio-metabolic-table-focus-on-compound",
 "/content/dam/menarini-com/content-fragments/en_us/pipeline-tables/pipeline-and-products/cardio-metabolic-table-focus-on-indication",
]

BIONTECH="https://www.biontech.com/int/en/home/pipeline-and-products/pipeline.html"
BIOGEN="https://www.biogen.com/science-and-innovation/pipeline.html"

def compact(s): return re.sub(r"\s+"," ",str(s or "")).strip()

async def menarini(c):
    variants=[".model.json",".json",".infinity.json"]
    results=[]
    for frag in MENARINI_FRAGMENTS[:3]:
        for suffix in variants:
            url=MENARINI_BASE+frag+suffix
            try:
                r=await c.get(url)
                body=r.text
                parsed=None
                if "json" in (r.headers.get("content-type") or "").lower() or body.lstrip().startswith(("{","[")):
                    try: parsed=r.json()
                    except Exception: parsed=None
                results.append({
                  "url":url,"status":r.status_code,"contentType":r.headers.get("content-type"),
                  "chars":len(body),
                  "jsonType":type(parsed).__name__ if parsed is not None else None,
                  "keys":list(parsed.keys())[:40] if isinstance(parsed,dict) else None,
                  "sample":parsed if isinstance(parsed,(list,dict)) and len(str(parsed))<5000 else compact(body[:3000])
                })
            except Exception as exc:
                results.append({"url":url,"error":f"{type(exc).__name__}: {exc}"})
    print("MENARINI_MACHINE_PROBE "+json.dumps(results,ensure_ascii=False),flush=True)

async def discover_assets(c,label,url):
    r=await c.get(url)
    body=r.text
    candidates=[]
    for raw in re.findall(r'''(?:src|href|data-[a-z0-9_-]+)=["']([^"']+)["']''',body,re.I):
        full=urljoin(str(r.url),html_lib.unescape(raw))
        low=full.lower()
        if any(k in low for k in ["pipeline","json","api","graphql","react","content","data","model"]):
            if full not in candidates: candidates.append(full)
    quoted=[]
    for m in re.finditer(r'''["']([^"'<>\s]{4,400})["']''',body):
        raw=m.group(1)
        low=raw.lower()
        if any(k in low for k in ["pipeline","api/","json","graphql","endpoint"]):
            val=urljoin(str(r.url),html_lib.unescape(raw))
            if val not in quoted: quoted.append(val)
        if len(quoted)>=120: break
    snippets=[]
    low=body.lower()
    for key in ["react-pipeline","pipelinev2.2","row pipeline-list","row pipeline","data-pipeline","api", "graphql"]:
        pos=0
        for _ in range(8):
            i=low.find(key,pos)
            if i<0: break
            snippets.append({"key":key,"text":compact(body[max(0,i-700):i+1800])[:2500]})
            pos=i+len(key)
    print(label+" "+json.dumps({
      "status":r.status_code,"finalUrl":str(r.url),"chars":len(body),
      "candidateAssets":candidates[:120],"quotedCandidates":quoted[:120],"snippets":snippets[:50]
    },ensure_ascii=False),flush=True)

async def main():
    async with httpx.AsyncClient(timeout=35.0,follow_redirects=True,headers=HEADERS) as c:
        await menarini(c)
        await discover_assets(c,"BIONTECH_MACHINE_PROBE",BIONTECH)
        await discover_assets(c,"BIOGEN_MACHINE_PROBE",BIOGEN)

if __name__=="__main__":
    asyncio.run(main())
