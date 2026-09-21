"""Read-only focused JS endpoint extraction for Menarini and BioNTech."""
import asyncio, json, re
from urllib.parse import urljoin
import httpx

HEADERS={"User-Agent":"Mozilla/5.0 PipelineClientCodeProbe/1.0","Accept":"application/javascript,text/javascript,*/*;q=0.8"}
TARGETS=[
 ("MENARINI","https://www.menarini.com/etc.clientlibs/menarinimaster/clientlibs/clientlib-menarinicom.lc-8ec83e7087f5f427f9648d98b0a60c50-lc.min.js",
  ["pipelinetable","data-table-cf-path","content-fragment",".model.json","fetch(","ajax","/bin/"]),
 ("BIONTECH","https://www.biontech.com/etc.clientlibs/biontech-xp-nova/clientlibs/clientlib-site-main.lc-b59be832b3008ea78c75ca1f1589206c-lc.min.js",
  ["react-pipeline","pipelinev2","pipeline","fetch(","axios","graphql","/bin/","api/","json"]),
]

def compact(s): return re.sub(r"\s+"," ",str(s or "")).strip()

async def main():
  async with httpx.AsyncClient(timeout=35.0,follow_redirects=True,headers=HEADERS) as c:
    for label,url,keys in TARGETS:
      try:
        r=await c.get(url); txt=r.text; low=txt.lower()
        snippets=[]
        for key in keys:
          pos=0
          for _ in range(20):
            i=low.find(key.lower(),pos)
            if i<0: break
            snippets.append({"key":key,"offset":i,"text":compact(txt[max(0,i-1000):i+2500])[:3500]})
            pos=i+len(key)
        strings=[]
        for m in re.finditer(r'''["']([^"'\s]{3,800})["']''',txt):
          v=m.group(1); lv=v.lower()
          if any(k in lv for k in ["pipeline","content-fragment","model.json","/bin/","graphql","api/","json"]):
            if v not in strings: strings.append(v)
          if len(strings)>=200: break
        print(label+"_CLIENT_CODE "+json.dumps({
          "status":r.status_code,"chars":len(txt),"contentType":r.headers.get("content-type"),
          "strings":strings[:200],"snippets":snippets[:80]
        },ensure_ascii=False),flush=True)
      except Exception as exc:
        print(label+"_CLIENT_CODE "+json.dumps({"error":f"{type(exc).__name__}: {exc}"},ensure_ascii=False),flush=True)

if __name__=="__main__":
  asyncio.run(main())
