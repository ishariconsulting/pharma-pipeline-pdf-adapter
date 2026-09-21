"""Read-only machine-source schema probes for Biogen, BioNTech and Menarini."""
import asyncio, json, re, html as html_lib
from urllib.parse import urljoin, quote
import httpx

HEADERS={"User-Agent":"Mozilla/5.0 PipelineSchemaProbe/1.0","Accept":"application/json,text/html,*/*;q=0.8"}
BIOGEN_JSON="https://www.biogen.com/content/dam/corporate/international/global/en-US/global/json/pipeline-production.json"
BIONTECH_PAGE="https://www.biontech.com/int/en/home/pipeline-and-products/pipeline.html"
MENARINI_PAGE="https://www.menarini.com/en-us/innovation-research/our-pipeline-and-products.html"

def compact(s): return re.sub(r"\s+"," ",str(s or "")).strip()

async def biogen(c):
    r=await c.get(BIOGEN_JSON)
    body=r.text
    try: data=r.json()
    except Exception: data=None
    sample=None
    if isinstance(data,list): sample=data[:6]
    elif isinstance(data,dict):
        sample={k:data[k] for k in list(data)[:15]}
    print("BIOGEN_JSON_SCHEMA "+json.dumps({
      "status":r.status_code,"contentType":r.headers.get("content-type"),
      "chars":len(body),"jsonType":type(data).__name__ if data is not None else None,
      "sample":sample
    },ensure_ascii=False),flush=True)

async def biontech(c):
    page=await c.get(BIONTECH_PAGE); html=page.text
    scripts=[urljoin(str(page.url),html_lib.unescape(x)) for x in re.findall(r'<script[^>]+src=["\']([^"\']+)["\']',html,re.I)]
    scripts=list(dict.fromkeys(scripts))
    matches=[]
    for url in scripts[:35]:
        try:
            r=await c.get(url)
            text=r.text
            low=text.lower()
            if any(k in low for k in ["pipelinev2","react-pipeline","bnt327","pipeline"]) and len(text)<8_000_000:
                snippets=[]
                for key in ["pipelinev2","react-pipeline","bnt327","fetch(","axios","graphql","/bin/","json"]:
                    pos=0
                    for _ in range(8):
                        i=low.find(key.lower(),pos)
                        if i<0: break
                        snippets.append({"key":key,"text":compact(text[max(0,i-900):i+2200])[:3100]})
                        pos=i+len(key)
                urls=[]
                for m in re.finditer(r'''["']([^"'\s]{4,500})["']''',text):
                    v=m.group(1)
                    lv=v.lower()
                    if any(k in lv for k in ["pipeline","graphql","/bin/","api/","json"]):
                        full=urljoin(url,html_lib.unescape(v))
                        if full not in urls: urls.append(full)
                    if len(urls)>=120: break
                matches.append({"script":url,"chars":len(text),"urls":urls[:120],"snippets":snippets[:30]})
        except Exception as exc:
            matches.append({"script":url,"error":f"{type(exc).__name__}: {exc}"})
    # Also capture the exact react component markup.
    component=[]
    for key in ["react-pipeline","pipelinev2.2"]:
        low=html.lower(); pos=0
        for _ in range(6):
            i=low.find(key,pos)
            if i<0: break
            component.append({"key":key,"text":compact(html[max(0,i-1200):i+3500])[:4700]})
            pos=i+len(key)
    print("BIONTECH_SCRIPT_SCHEMA "+json.dumps({"scripts":scripts,"matches":matches,"component":component},ensure_ascii=False),flush=True)

async def menarini(c):
    page=await c.get(MENARINI_PAGE); html=page.text
    scripts=[urljoin(str(page.url),html_lib.unescape(x)) for x in re.findall(r'<script[^>]+src=["\']([^"\']+)["\']',html,re.I)]
    scripts=list(dict.fromkeys(scripts))
    component=[]
    low=html.lower()
    for key in ["cmp-pipelinetable","pipelinetable","content-fragments/en_us/pipeline-tables"]:
        pos=0
        for _ in range(10):
            i=low.find(key,pos)
            if i<0: break
            component.append({"key":key,"text":compact(html[max(0,i-1500):i+4500])[:6000]})
            pos=i+len(key)
    js=[]
    for url in scripts[:35]:
        try:
            r=await c.get(url); txt=r.text; l=txt.lower()
            if any(k in l for k in ["pipelinetable","content-fragment","pipeline-table"]):
                snippets=[]
                for key in ["pipelinetable","content-fragment",".model.json","graphql","fetch(","ajax"]:
                    pos=0
                    for _ in range(10):
                        i=l.find(key.lower(),pos)
                        if i<0: break
                        snippets.append({"key":key,"text":compact(txt[max(0,i-900):i+2400])[:3300]})
                        pos=i+len(key)
                js.append({"script":url,"chars":len(txt),"snippets":snippets[:40]})
        except Exception:
            pass
    # Retry first fragment with URL-encoded parentheses.
    frag="/content/dam/menarini-com/content-fragments/en_us/pipeline-tables/pipeline-and-products/oncology-%28focus-on-compound%29"
    variants=[]
    for suffix in [".model.json",".json",".infinity.json",".1.json"]:
        url="https://www.menarini.com"+frag+suffix
        r=await c.get(url)
        variants.append({"url":url,"status":r.status_code,"contentType":r.headers.get("content-type"),"chars":len(r.text),"head":compact(r.text[:2500])})
    print("MENARINI_COMPONENT_SCHEMA "+json.dumps({"scripts":scripts,"component":component[:30],"js":js,"variants":variants},ensure_ascii=False),flush=True)

async def main():
  async with httpx.AsyncClient(timeout=35.0,follow_redirects=True,headers=HEADERS) as c:
    await biogen(c)
    await biontech(c)
    await menarini(c)

if __name__=="__main__":
    asyncio.run(main())
