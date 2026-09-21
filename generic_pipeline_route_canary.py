"""Focused read-only source-contract discovery: Merck, BioNTech, Vertex."""
import asyncio, html as html_lib, json, re
import httpx
from urllib.parse import urljoin

HEADERS={"User-Agent":"Mozilla/5.0 SourceContractCanary/1.0","Accept":"text/html,*/*;q=0.8"}
URLS={
 "MERCK":"https://www.emdgroup.com/en/research/healthcare-pipeline.html",
 "BIONTECH":"https://www.biontech.com/int/en/home/pipeline-and-products/pipeline.html",
 "VERTEX":"https://www.vrtx.com/our-science/pipeline/",
}

def compact(v): return re.sub(r"\s+"," ",html_lib.unescape(str(v or ""))).strip()

async def main():
  async with httpx.AsyncClient(timeout=30,follow_redirects=True,headers=HEADERS) as c:
    for label,url in URLS.items():
      r=await c.get(url); body=r.text; low=body.lower()
      result={"label":label,"status":r.status_code,"finalUrl":str(r.url),"chars":len(body)}
      if label=="MERCK":
        snippets=[]
        for pat in [r'id=["\']contentdiv["\'][^>]*>[\s\S]{0,3000}',r'class=["\']filePath["\'][^>]*>[\s\S]{0,600}',r'filePath[\s\S]{0,900}']:
          m=re.search(pat,body,re.I)
          if m: snippets.append(compact(m.group(0))[:3000])
        result["snippets"]=snippets
      elif label=="BIONTECH":
        keys=["react-pipeline","pipelinev2","pipeline-data","clinical-pipeline","phase-1","phase 1","data-json","data-api","content-fragment","model.json"]
        hits=[]
        for k in keys:
          pos=0
          for _ in range(8):
            i=low.find(k,pos)
            if i<0: break
            hits.append({"key":k,"text":compact(body[max(0,i-500):i+1800])[:2300]})
            pos=i+len(k)
        scripts=[urljoin(str(r.url),html_lib.unescape(x)) for x in re.findall(r'<script[^>]+src=["\']([^"\']+)["\']',body,re.I)]
        result["hits"]=hits[:35]; result["scripts"]=list(dict.fromkeys(scripts))[-25:]
      elif label=="VERTEX":
        # Summarize repeated semantic class/id names and nearby source rows.
        class_names=[]
        for raw in re.findall(r'class=["\']([^"\']+)["\']',body,re.I):
          for cls in raw.split():
            if any(k in cls.lower() for k in ["pipeline","phase","indication","molecule","therapeutic","program","views-row","coh-"]):
              class_names.append(cls)
        counts={}
        for cls in class_names: counts[cls]=counts.get(cls,0)+1
        result["classCounts"]=dict(sorted(counts.items(),key=lambda x:-x[1])[:80])
        hits=[]
        for k in ["VX-993","VX-407","povetacicept","phase 2","views-row","pipeline-card","pipeline"]:
          pos=0
          for _ in range(10):
            i=low.find(k.lower(),pos)
            if i<0: break
            hits.append({"key":k,"text":compact(body[max(0,i-500):i+1700])[:2200]})
            pos=i+len(k)
        result["hits"]=hits[:45]
      print("SOURCE_CONTRACT "+json.dumps(result,ensure_ascii=False),flush=True)

if __name__=="__main__":
  asyncio.run(main())
