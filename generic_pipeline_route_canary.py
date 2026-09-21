"""Read-only dependency discovery for remaining pipeline sources."""
import asyncio, json, re, html as html_lib
from urllib.parse import urljoin
import httpx

SOURCES=[
 ("J&J Development","https://www.investor.jnj.com/pipeline/development-pipeline/default.aspx"),
 ("BioNTech","https://www.biontech.com/int/en/home/pipeline-and-products/pipeline.html"),
 ("Vertex","https://www.vrtx.com/our-science/pipeline/"),
 ("Boehringer","https://www.boehringer-ingelheim.com/science-innovation/human-health-innovation/pipeline"),
 ("Wave","https://wavelifesciences.com/pipeline/research-and-development/"),
 ("Verve","https://www.vervetx.com/our-programs/our-pipeline"),
 ("Merck KGaA","https://www.emdgroup.com/en/research/our-approach-to-research-and-development/healthcare.html"),
]
HEADERS={"User-Agent":"Mozilla/5.0 PipelineDependency/1.0","Accept":"text/html,application/json,*/*;q=0.8"}
ATTR=re.compile(r'(?:src|href|data-[a-z0-9_-]+)=["\']([^"\']+)["\']',re.I)
QUOTED=re.compile(r'["\']((?:https?:)?//[^"\'\s<>]+|/[^"\'<>]{3,240})["\']',re.I)
KEYS=("api","json","ajax","graphql","pipeline","development","drug","phase","asset","program","programme","search","q4cdn","static-files","pdf","xlsx","csv")

def compact(s): return re.sub(r"\s+"," ",html_lib.unescape(s or "")).strip()

async def one(c,label,url):
    try:
        r=await c.get(url)
        body=r.text
        found=[]; seen=set()
        for raw in ATTR.findall(body)+QUOTED.findall(body):
            full=urljoin(str(r.url),html_lib.unescape(raw))
            low=full.lower()
            if any(k in low for k in KEYS) and full not in seen:
                seen.add(full); found.append(full)
        snippets=[]
        for key in ["phase 1","phase 2","phase 3","registration","pipeline","total indications","drug name","development pipeline"]:
            start=0
            for _ in range(3):
                i=body.lower().find(key,start)
                if i<0: break
                snippets.append({"key":key,"text":compact(body[max(0,i-220):i+700])[:1000]})
                start=i+len(key)
        print("REMAINING_DEPENDENCY "+json.dumps({
          "label":label,"status":r.status_code,"finalUrl":str(r.url),
          "contentType":r.headers.get("content-type"),"chars":len(body),
          "candidateUrls":found[:120],"snippets":snippets[:30]
        },ensure_ascii=False),flush=True)
    except Exception as exc:
        print("REMAINING_DEPENDENCY "+json.dumps({"label":label,"error":f"{type(exc).__name__}: {exc}"},ensure_ascii=False),flush=True)

async def main():
    async with httpx.AsyncClient(timeout=30.0,follow_redirects=True,headers=HEADERS) as c:
        for label,url in SOURCES:
            await one(c,label,url)

if __name__=="__main__":
    asyncio.run(main())
