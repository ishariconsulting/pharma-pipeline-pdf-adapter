"""Read-only Wave Life Sciences pipeline DOM/source diagnostic."""
import asyncio, html as html_lib, json, re
import httpx

URL="https://wavelifesciences.com/pipeline/research-and-development/"
ASSETS=["WVE-007","WVE-006","WVE-008","WVE-N531","WVE-003"]
HEADERS={"User-Agent":"Mozilla/5.0 WavePipelineDiagnostic/1.0","Accept":"text/html,*/*;q=0.8"}

def compact(v):
    return re.sub(r"\s+"," ",html_lib.unescape(str(v or ""))).strip()

def around(text,key,before=3500,after=6500):
    i=text.lower().find(key.lower())
    if i<0: return ""
    return compact(text[max(0,i-before):i+after])[:before+after]

async def main():
    async with httpx.AsyncClient(timeout=45.0,follow_redirects=True,headers=HEADERS) as c:
        r=await c.get(URL)
        body=r.text
        snippets={a:around(body,a) for a in ASSETS}
        class_hits=[]
        for pat in [
          r'class=["\']([^"\']*(?:pipeline|progress|stage|clinical|discovery|ind|cta)[^"\']*)["\']',
          r'data-[a-z0-9_-]+=["\'][^"\']*(?:clinical|discovery|ind|cta|stage)[^"\']*["\']',
          r'style=["\'][^"\']*(?:width|left|right|grid-column)[^"\']*["\']',
        ]:
            for m in re.finditer(pat,body,re.I):
                hit=compact(m.group(0))
                if hit and hit not in class_hits:
                    class_hits.append(hit)
                if len(class_hits)>=120: break
            if len(class_hits)>=120: break
        print("WAVE_SOURCE_STRUCTURE "+json.dumps({
          "status":r.status_code,
          "finalUrl":str(r.url),
          "contentType":r.headers.get("content-type"),
          "chars":len(body),
          "assetSnippets":snippets,
          "structureHits":class_hits,
          "masterWrites":0
        },ensure_ascii=False),flush=True)

if __name__=="__main__":
    asyncio.run(main())
