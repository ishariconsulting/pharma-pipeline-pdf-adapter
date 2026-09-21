"""Read-only dependency diagnostics for unresolved pipeline pages."""
import asyncio, json, re
from urllib.parse import urljoin
from generic_pipeline_extension import _fetch_raw_public_html

SOURCES=[
 ("Gilead Sciences","https://www.gilead.com/science/pipeline"),
 ("Amgen","https://www.amgen.com/science/clinical-trials"),
 ("Ionis Pharmaceuticals","https://ionis.com/science-and-innovation/pipeline"),
]

ATTR_RE=re.compile(r'''(?:href|src|data-[a-z0-9_-]+)\s*=\s*["']([^"'<>]+)["']''',re.I)
QUOTED_URL_RE=re.compile(r'''["']((?:https?:)?//[^"'\s<>]+|/[^"'<>]{3,220})["']''',re.I)
KEYWORDS=("pipeline","api","json","graphql","content","clinical","trial","program","phase","ajax","search","sitecore","aem","endpoint")

def compact(s): return re.sub(r"\s+"," ",s or "").strip()

async def one(company,url):
    try:
        html,final=await _fetch_raw_public_html(url,28.0)
        found=[]
        seen=set()
        for raw in ATTR_RE.findall(html)+QUOTED_URL_RE.findall(html):
            raw=raw.replace("&amp;","&")
            full=urljoin(final,raw)
            low=full.lower()
            if any(k in low for k in KEYWORDS) and full not in seen:
                seen.add(full); found.append(full)
        snippets=[]
        lower=html.lower()
        for key in ["phase 1","phase 2","phase 3","pipeline","program count","clinical stage","owned pipeline","partnered pipeline"]:
            pos=0
            for _ in range(3):
                i=lower.find(key,pos)
                if i<0: break
                snippets.append({"key":key,"text":compact(html[max(0,i-220):i+500])[:900]})
                pos=i+len(key)
        print("PIPELINE_DEPENDENCY_DIAGNOSTIC "+json.dumps({
          "company":company,"finalUrl":final,"htmlChars":len(html),
          "candidateUrls":found[:120],"snippets":snippets[:30]
        },ensure_ascii=False),flush=True)
    except Exception as exc:
        print("PIPELINE_DEPENDENCY_DIAGNOSTIC "+json.dumps({"company":company,"error":f"{type(exc).__name__}: {exc}"},ensure_ascii=False),flush=True)

async def main():
    for company,url in SOURCES:
        await one(company,url)

if __name__=="__main__":
    asyncio.run(main())
