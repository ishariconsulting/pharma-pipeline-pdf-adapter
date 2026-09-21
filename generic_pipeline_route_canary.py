"""Read-only dependency discovery for unresolved official pipeline pages.

Inspects public page HTML + referenced JavaScript for machine-readable pipeline
sources (JSON, GraphQL, AEM, APIs, downloadable documents). No Airtable or
master-data writes.
"""
import asyncio, html as html_lib, json, re
from urllib.parse import urljoin
import httpx

HEADERS={
  "User-Agent":"Mozilla/5.0 PipelineDependencyDiscovery/1.0",
  "Accept":"text/html,application/json,*/*;q=0.8"
}
PAGES=[
 ("JNJ","https://www.investor.jnj.com/pipeline/development-pipeline/default.aspx"),
 ("MERCK_KGAA","https://www.emdgroup.com/en/research/healthcare-pipeline.html"),
 ("BIONTECH","https://www.biontech.com/int/en/home/pipeline-and-products/pipeline.html"),
 ("VERTEX","https://www.vrtx.com/our-science/pipeline/"),
 ("BOEHRINGER","https://www.boehringer-ingelheim.com/science-innovation/human-health-innovation/pipeline"),
 ("WAVE","https://wavelifesciences.com/pipeline/research-and-development/"),
 ("VERVE","https://www.vervetx.com/our-programs/our-pipeline"),
]
KEYWORDS=("pipeline","api","json","graphql","content-fragment","contentfragment","model.json","ajax","drug","molecule","program","programme","phase","trial")

def compact(v):
    return re.sub(r"\s+"," ",html_lib.unescape(str(v or ""))).strip()

def candidate_urls(base,text):
    out=[]
    pats=[
      r'''(?:src|href|data-[a-z0-9_-]+)=["']([^"'<>]+)["']''',
      r'''["']((?:https?:)?//[^"'\s<>]+|/[^"'<>]{3,500})["']''',
    ]
    for pat in pats:
      for raw in re.findall(pat,text,re.I):
        raw=html_lib.unescape(raw)
        full=urljoin(base,raw)
        low=full.lower()
        if any(k in low for k in KEYWORDS):
          if full not in out: out.append(full)
        if len(out)>=180: return out
    return out

async def inspect_script(c,label,url):
    try:
      r=await c.get(url)
      body=r.text
      low=body.lower()
      if not any(k in low for k in KEYWORDS):
        return None
      urls=candidate_urls(str(r.url),body)
      snippets=[]
      for k in ("graphql","model.json","content-fragment","fetch(","axios","ajax","pipeline","api/","json"):
        pos=0
        for _ in range(5):
          i=low.find(k,pos)
          if i<0: break
          snippets.append({"key":k,"text":compact(body[max(0,i-350):i+1100])[:1450]})
          pos=i+len(k)
      return {"url":url,"status":r.status_code,"chars":len(body),"urls":urls[:80],"snippets":snippets[:16]}
    except Exception as exc:
      return {"url":url,"error":f"{type(exc).__name__}: {exc}"}

async def one(c,label,url):
    try:
      r=await c.get(url)
      body=r.text
      scripts=[urljoin(str(r.url),html_lib.unescape(x)) for x in re.findall(r'<script[^>]+src=["\']([^"\']+)["\']',body,re.I)]
      scripts=list(dict.fromkeys(scripts))
      page_urls=candidate_urls(str(r.url),body)
      interesting_scripts=[]
      for script in scripts[:60]:
        item=await inspect_script(c,label,script)
        if item and (item.get("urls") or item.get("snippets")):
          interesting_scripts.append(item)
      text=compact(re.sub(r"<[^>]+>"," ",body))
      print("DEPENDENCY_DISCOVERY "+json.dumps({
        "label":label,"status":r.status_code,"finalUrl":str(r.url),
        "htmlChars":len(body),"visibleTextChars":len(text),
        "pageCandidateUrls":page_urls[:120],
        "scriptMatches":interesting_scripts[:12],
        "textHead":text[:2500],
      },ensure_ascii=False),flush=True)
    except Exception as exc:
      print("DEPENDENCY_DISCOVERY "+json.dumps({"label":label,"error":f"{type(exc).__name__}: {exc}"},ensure_ascii=False),flush=True)

async def main():
    async with httpx.AsyncClient(timeout=30.0,follow_redirects=True,headers=HEADERS) as c:
      for label,url in PAGES:
        await one(c,label,url)

if __name__=="__main__":
    asyncio.run(main())
