"""Focused machine-contract discovery for Merck, BioNTech, Vertex."""
import asyncio, html as html_lib, json, re
from urllib.parse import urljoin
import httpx

HEADERS={"User-Agent":"Mozilla/5.0 MachineContractCanary/1.0","Accept":"text/html,application/javascript,*/*;q=0.8"}
PAGES={
 "MERCK":"https://www.emdgroup.com/en/research/healthcare-pipeline.html",
 "BIONTECH":"https://www.biontech.com/int/en/home/pipeline-and-products/pipeline.html",
 "VERTEX":"https://www.vrtx.com/our-science/pipeline/",
}

def compact(v):
    return re.sub(r"\s+"," ",html_lib.unescape(str(v or ""))).strip()

def around(text,key,before=900,after=2200,limit=8):
    low=text.lower(); k=key.lower(); out=[]; pos=0
    for _ in range(limit):
      i=low.find(k,pos)
      if i<0: break
      out.append(compact(text[max(0,i-before):i+after])[:before+after])
      pos=i+len(k)
    return out

async def main():
  async with httpx.AsyncClient(timeout=35,follow_redirects=True,headers=HEADERS) as c:
    merck=await c.get(PAGES["MERCK"])
    print("MERCK_PATH_DISCOVERY "+json.dumps({
      "status":merck.status_code,
      "contentdiv":around(merck.text,"contentdiv",1200,2600,10),
      "filepath":around(merck.text,"filePath",1200,2600,10),
      "datajs":around(merck.text,"data.js",1200,2600,10),
    },ensure_ascii=False),flush=True)

    bio=await c.get(PAGES["BIONTECH"])
    scripts=[urljoin(str(bio.url),html_lib.unescape(x)) for x in re.findall(r'<script[^>]+src=["\']([^"\']+)["\']',bio.text,re.I)]
    js_hits=[]
    for s in list(dict.fromkeys(scripts)):
      try:
        r=await c.get(s)
        txt=r.text
        low=txt.lower()
        if any(k in low for k in ["pipelinecfref","pipelinedirectoryref","pipelinev2","contentfragment","content-fragment","graphql"]):
          snippets=[]
          for key in ["pipelineCfRef","pipelineDirectoryRef","pipelinev2","contentFragment","graphql",".model.json","assets.json"]:
            snippets += [{"key":key,"text":x} for x in around(txt,key,700,1900,8)]
          js_hits.append({"url":s,"status":r.status_code,"chars":len(txt),"snippets":snippets[:35]})
      except Exception as exc:
        pass
    print("BIONTECH_JS_CONTRACT "+json.dumps({"scripts":js_hits},ensure_ascii=False),flush=True)

    vx=await c.get(PAGES["VERTEX"])
    phase_hits=around(vx.text,"views-field-field-phase",1800,2600,12)
    asset_keys=[]
    for key in ["views-field-title","views-field-field-indication","views-field-field-therapeutic","views-field-field-program","views-field-field-molecule","VX-993","VX-407"]:
      vals=around(vx.text,key,1400,2200,6)
      if vals: asset_keys.append({"key":key,"hits":vals})
    print("VERTEX_ROW_CONTRACT "+json.dumps({
      "status":vx.status_code,"phaseHits":phase_hits[:12],"semanticHits":asset_keys
    },ensure_ascii=False),flush=True)

if __name__=="__main__":
  asyncio.run(main())
