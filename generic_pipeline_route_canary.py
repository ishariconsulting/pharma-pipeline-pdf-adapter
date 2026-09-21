"""Read-only BioNTech Webpack pipeline-module discovery.

Finds the runtime chunk URL builder in the current official site bundle,
resolves the chunks used by pipelinev2.2, and inspects only those JavaScript
chunks for first-party pipeline data endpoints/configuration. No writes.
"""
import asyncio, json, re
from urllib.parse import urljoin
import httpx

MAIN="https://www.biontech.com/etc.clientlibs/biontech-xp-nova/clientlibs/clientlib-site-main.lc-b59be832b3008ea78c75ca1f1589206c-lc.min.js"
CHUNK_IDS=[491,961,290,957,463]
HEADERS={"User-Agent":"Mozilla/5.0 BioNTechPipelineDiscovery/1.0","Accept":"application/javascript,text/javascript,*/*;q=0.8"}

def compact(s): return re.sub(r"\s+"," ",str(s or "")).strip()

async def main():
  async with httpx.AsyncClient(timeout=35.0,follow_redirects=True,headers=HEADERS) as c:
    r=await c.get(MAIN); r.raise_for_status(); text=r.text
    snippets=[]
    for pat in [r"\.u\s*=\s*function",r"\.u\s*=\s*\(",r"__webpack_require__\.u",r"chunkFilename",r"491",r"pipelinev2\.2"]:
      for m in re.finditer(pat,text,re.I):
        snippets.append({"pattern":pat,"offset":m.start(),"text":compact(text[max(0,m.start()-1500):m.start()+5500])[:7000]})
        if len(snippets)>=25: break
      if len(snippets)>=25: break
    print("BIONTECH_WEBPACK_RUNTIME "+json.dumps({"chars":len(text),"snippets":snippets},ensure_ascii=False),flush=True)

    # Collect any literal or templated script references around the pipeline map
    # and runtime. This intentionally does not guess a chunk URL.
    candidate_strings=[]
    for m in re.finditer(r'''["']([^"'\s]{2,500})["']''',text):
      v=m.group(1)
      low=v.lower()
      if any(k in low for k in ["pipelinev2","clientlib-site-main",".js","chunk"]):
        if v not in candidate_strings: candidate_strings.append(v)
      if len(candidate_strings)>=250: break
    print("BIONTECH_WEBPACK_STRINGS "+json.dumps({"strings":candidate_strings[:250]},ensure_ascii=False),flush=True)

if __name__=="__main__":
  asyncio.run(main())
