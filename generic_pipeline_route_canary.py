"""Read-only canary for Drupal Views parser plus source endpoints."""
import asyncio, json, re, html as html_lib
from urllib.parse import urljoin
import httpx
from drupal_views_pipeline_extension import extract_drupal_views

VERTEX="https://www.vrtx.com/our-science/pipeline/"
MERCK_DATA_CANDIDATES=[
 "https://www.emdgroup.com/content/dam/scripts/group/en/pipeline/data.js",
 "https://www.emdgroup.com/content/dam/scripts/group/en/pipeline/data/data.js",
 "https://www.emdgroup.com/content/dam/web/corporate/scripts/group/en/pipeline/data.js",
]
BIONTECH_PAGE="https://www.biontech.com/int/en/home/pipeline-and-products/pipeline.html"

def compact(v): return re.sub(r"\s+"," ",html_lib.unescape(str(v or ""))).strip()

async def main():
  try:
    r=await extract_drupal_views("Vertex Pharmaceuticals",VERTEX,35.0)
    print("VERTEX_DRUPAL_CANARY "+json.dumps({
      "readyForDiscovery":r.readyForDiscovery,"rowCount":r.rowCount,
      "issues":[x.get("issue") for x in r.issues],"diagnostics":r.diagnostics,
      "phaseCounts":{p:sum(1 for x in r.rows if x["phase"]==p) for p in sorted(set(x["phase"] for x in r.rows))},
      "sample":r.rows[:15],"masterWrites":0
    },ensure_ascii=False),flush=True)
  except Exception as exc:
    print("VERTEX_DRUPAL_CANARY "+json.dumps({"readyForDiscovery":False,"error":f"{type(exc).__name__}: {exc}","masterWrites":0}),flush=True)

  async with httpx.AsyncClient(timeout=35,follow_redirects=True,headers={"User-Agent":"Mozilla/5.0 ContractCanary/1.0","Accept":"*/*"}) as c:
    merck=[]
    for url in MERCK_DATA_CANDIDATES:
      try:
        rr=await c.get(url)
        merck.append({"url":url,"status":rr.status_code,"contentType":rr.headers.get("content-type"),"chars":len(rr.text),"head":compact(rr.text[:3500])[:3500]})
      except Exception as exc:
        merck.append({"url":url,"error":f"{type(exc).__name__}: {exc}"})
    print("MERCK_DATA_PROBE "+json.dumps(merck,ensure_ascii=False),flush=True)

    bio=await c.get(BIONTECH_PAGE)
    scripts=[urljoin(str(bio.url),html_lib.unescape(x)) for x in re.findall(r'<script[^>]+src=["\']([^"\']+)["\']',bio.text,re.I)]
    mainjs=next((x for x in scripts if "clientlib-site-main" in x),None)
    result={"mainJs":mainjs}
    if mainjs:
      jr=await c.get(mainjs); txt=jr.text
      result["publicPathHits"]=[]
      for key in ["n.u=function","__webpack_require__.u","function(t){return","pipelinev2.2/index","957","463"]:
        low=txt.lower(); k=key.lower(); pos=0
        for _ in range(5):
          i=low.find(k,pos)
          if i<0: break
          result["publicPathHits"].append({"key":key,"text":compact(txt[max(0,i-900):i+2600])[:3500]})
          pos=i+len(k)
    print("BIONTECH_BUNDLE_DISCOVERY "+json.dumps(result,ensure_ascii=False),flush=True)

if __name__=="__main__":
  asyncio.run(main())
