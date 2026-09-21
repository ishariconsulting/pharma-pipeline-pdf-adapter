"""Read-only Amgen pipeline JS/API dependency diagnostic."""
import asyncio, json, re, html as html_lib
from urllib.parse import urljoin
import httpx

BASE="https://www.amgenpipeline.com/"
JS=urljoin(BASE,"/-/media/Themes/Amgen/amgenpipeline-com/amgenpipeline-com/Scripts/pipeline-custom.js")
HEADERS={"User-Agent":"Mozilla/5.0 AmgenPipelineDiagnostic/1.0","Accept":"text/javascript,text/html,application/json,*/*;q=0.8"}

def compact(v): return re.sub(r"\s+"," ",str(v or "")).strip()

async def main():
  async with httpx.AsyncClient(timeout=35.0,follow_redirects=True,headers=HEADERS) as c:
    page=await c.get(BASE)
    js=await c.get(JS)
    body=js.text
    snippets=[]
    patterns=[
      r"\$\.ajax\s*\([\s\S]{0,1800}?\}\)",
      r"ajax\s*:\s*[^,;]{0,1000}",
      r"fetch\s*\([^\)]{0,1200}\)",
      r"url\s*:\s*[^,;\n]{0,700}",
      r'["\']([^"\']*(?:api|search|pipeline|molecule|filter|json|datasource)[^"\']*)["\']',
    ]
    for pat in patterns:
      for m in re.finditer(pat,body,re.I):
        s=compact(m.group(0))
        if s not in snippets: snippets.append(s[:1800])
        if len(snippets)>=120: break
      if len(snippets)>=120: break

    page_snips=[]
    for key in ["Showing 0","molecule","pipelineData","api","ajax","datasource","search-result","filter-result"]:
      pos=0
      for _ in range(5):
        i=page.text.lower().find(key.lower(),pos)
        if i<0: break
        page_snips.append({"key":key,"text":compact(page.text[max(0,i-500):i+1500])[:2200]})
        pos=i+len(key)

    print("AMGEN_JS_DEPENDENCY "+json.dumps({
      "pageStatus":page.status_code,"jsStatus":js.status_code,"jsChars":len(body),
      "snippets":snippets[:120],"pageSnippets":page_snips[:50],
      "jsHead":compact(body[:5000])[:5000]
    },ensure_ascii=False),flush=True)

if __name__=="__main__":
  asyncio.run(main())
