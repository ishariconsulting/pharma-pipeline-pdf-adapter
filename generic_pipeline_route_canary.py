"""Read-only endpoint discovery and browser transport diagnostics.

Focused probes for:
- Menarini AEM pipeline table client code
- BioNTech current pipeline component client code
- J&J development-pipeline client code
- configured browser worker response contract

No Airtable or master-data writes.
"""
import asyncio, html as html_lib, json, os, re
from urllib.parse import urljoin
import httpx

HEADERS={"User-Agent":"Mozilla/5.0 PipelineEndpointDiscovery/1.0","Accept":"text/html,application/json,*/*;q=0.8"}
PAGES=[
 ("MENARINI","https://www.menarini.com/en-us/innovation-research/our-pipeline-and-products.html"),
 ("BIONTECH","https://www.biontech.com/int/en/home/pipeline-and-products/pipeline.html"),
 ("JNJ","https://www.investor.jnj.com/pipeline/development-pipeline/default.aspx"),
]
KEYS={
 "MENARINI":["pipelinetable","data-table-cf-path","fetch(","$.ajax","ajax(","/bin/",".model.json","content-fragment"],
 "BIONTECH":["react-pipeline","pipelinev2","pipeline","fetch(","axios","graphql","/bin/","api/","json"],
 "JNJ":["pipeline","development-pipeline","fetch(","ajax","api/","json","graphql","table"],
}

def compact(s): return re.sub(r"\s+"," ",str(s or "")).strip()

async def probe_page(c,label,page_url):
    p=await c.get(page_url)
    html=p.text
    scripts=[urljoin(str(p.url),html_lib.unescape(x)) for x in re.findall(r'<script[^>]+src=["\']([^"\']+)["\']',html,re.I)]
    scripts=list(dict.fromkeys(scripts))
    matches=[]
    for url in scripts[:50]:
        try:
            r=await c.get(url)
            text=r.text
            low=text.lower()
            if not any(k.lower() in low for k in KEYS[label]):
                continue
            snippets=[]
            urls=[]
            for key in KEYS[label]:
                pos=0
                for _ in range(8):
                    i=low.find(key.lower(),pos)
                    if i<0: break
                    snippets.append({"key":key,"text":compact(text[max(0,i-650):i+1700])[:2350]})
                    pos=i+len(key)
            for m in re.finditer(r'''["']([^"'\s]{4,600})["']''',text):
                v=html_lib.unescape(m.group(1))
                lv=v.lower()
                if any(k in lv for k in ["pipeline","api","json","graphql","/bin/","content-fragment","model.json"]):
                    full=urljoin(url,v)
                    if full not in urls: urls.append(full)
                if len(urls)>=100: break
            matches.append({"script":url,"status":r.status_code,"chars":len(text),"urls":urls[:100],"snippets":snippets[:30]})
        except Exception as exc:
            matches.append({"script":url,"error":f"{type(exc).__name__}: {exc}"})

    page_snippets=[]
    low=html.lower()
    for key in KEYS[label]:
        pos=0
        for _ in range(8):
            i=low.find(key.lower(),pos)
            if i<0: break
            page_snippets.append({"key":key,"text":compact(html[max(0,i-800):i+2200])[:3000]})
            pos=i+len(key)

    print(label+"_FOCUSED_DISCOVERY "+json.dumps({
      "status":p.status_code,"finalUrl":str(p.url),"htmlChars":len(html),
      "scripts":scripts,"pageSnippets":page_snippets[:30],"scriptMatches":matches[:20]
    },ensure_ascii=False),flush=True)

async def browser_diag(c):
    base=os.getenv("BROWSER_FETCH_BASE_URL","").strip().rstrip("/")
    key=os.getenv("BROWSER_FETCH_KEY","").strip()
    if not base or not key:
        print("BROWSER_CONTRACT_DIAG "+json.dumps({"configured":False}),flush=True)
        return
    url="https://www.vrtx.com/our-science/pipeline/"
    endpoint=base+"/fetch/browser"
    try:
        r=await c.get(endpoint,params={"url":url,"timeout_seconds":20},headers={"X-Browser-Key":key})
        head=compact(r.text[:1600])
        parsed=None
        try: parsed=r.json()
        except Exception: pass
        print("BROWSER_CONTRACT_DIAG "+json.dumps({
          "configured":True,"base":base,"status":r.status_code,
          "contentType":r.headers.get("content-type"),"chars":len(r.text),
          "jsonType":type(parsed).__name__ if parsed is not None else None,
          "jsonKeys":list(parsed.keys())[:30] if isinstance(parsed,dict) else None,
          "version":parsed.get("version") if isinstance(parsed,dict) else None,
          "visibleTextLength":parsed.get("visibleTextLength") if isinstance(parsed,dict) else None,
          "visibleLines":len(parsed.get("visibleLines") or []) if isinstance(parsed,dict) else None,
          "tables":len(parsed.get("tables") or []) if isinstance(parsed,dict) else None,
          "head":head if parsed is None else None,
        },ensure_ascii=False),flush=True)
    except Exception as exc:
        print("BROWSER_CONTRACT_DIAG "+json.dumps({"configured":True,"base":base,"error":f"{type(exc).__name__}: {exc}"}),flush=True)

async def main():
    async with httpx.AsyncClient(timeout=35.0,follow_redirects=True,headers=HEADERS) as c:
        for label,url in PAGES:
            await probe_page(c,label,url)
        await browser_diag(c)

if __name__=="__main__":
    asyncio.run(main())
