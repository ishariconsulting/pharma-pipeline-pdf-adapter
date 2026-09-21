"""Read-only focused source diagnostics for remaining company pipelines.

Goals:
- identify BioNTech's AEM GraphQL contract and component refs;
- expose Wave's rendered DOM line structure for parser-family selection;
- identify Boehringer first-party embedded/script data candidates.

No Airtable or master-data writes.
"""
import asyncio, html as html_lib, json, os, re
from urllib.parse import urljoin
import httpx

BIO_PAGE="https://www.biontech.com/int/en/home/pipeline-and-products/pipeline.html"
BIO_CHUNK="https://www.biontech.com/etc.clientlibs/biontech-xp-nova/clientlibs/clientlib-site-main/resources/chunks/463-3ed4eb7b5b7fb87822ef.chunk.js"
BIO_GQL="https://www.biontech.com/content/_cq_graphql/pipeline-v2/endpoint.json"
WAVE="https://wavelifesciences.com/pipeline/research-and-development/"
BOE="https://www.boehringer-ingelheim.com/science-innovation/human-health-innovation/pipeline"

BROWSER_BASE=os.getenv("BROWSER_FETCH_BASE_URL","").strip().rstrip("/")
BROWSER_KEY=os.getenv("BROWSER_FETCH_KEY","").strip()
HEADERS={"User-Agent":"Mozilla/5.0 PipelineFocusedDiagnostic/1.0","Accept":"text/html,application/json,application/javascript,*/*;q=0.8"}

def compact(v):
    return re.sub(r"\s+"," ",html_lib.unescape(str(v or ""))).strip()

def snippets(text, keys, before=700, after=1800, each=4):
    low=text.lower(); out=[]
    for key in keys:
        pos=0
        for _ in range(each):
            i=low.find(key.lower(),pos)
            if i<0: break
            out.append({"key":key,"text":compact(text[max(0,i-before):i+after])[:before+after]})
            pos=i+len(key)
    return out

def interesting_urls(base, text, keys):
    out=[]; seen=set()
    patterns=[
      r'''(?:src|href|data-[a-z0-9_:-]+)=["']([^"']+)["']''',
      r'''["']((?:https?:)?//[^"'\s<>]+|/[^"'<>\s]{3,500})["']''',
    ]
    for pat in patterns:
        for raw in re.findall(pat,text,re.I):
            full=urljoin(base,html_lib.unescape(raw))
            low=full.lower()
            if any(k in low for k in keys) and full not in seen:
                seen.add(full); out.append(full)
            if len(out)>=120: return out
    return out

async def biontech(c):
    page=await c.get(BIO_PAGE)
    html=page.text
    attrs=[]
    for m in re.finditer(r'''([a-zA-Z_:][\w:.-]*)=["']([^"']{0,700})["']''',html):
        name=m.group(1); val=html_lib.unescape(m.group(2))
        n=name.lower(); v=val.lower()
        if any(k in n or k in v for k in ["pipelinecf","pipelinedirectory","translationcf","react-pipeline","pipeline-v2","content-fragment"]):
            item={"name":name,"value":val[:700]}
            if item not in attrs: attrs.append(item)
    print("BIONTECH_COMPONENT_REFS "+json.dumps({
      "status":page.status_code,"finalUrl":str(page.url),"htmlChars":len(html),
      "attrs":attrs[:80],
      "snippets":snippets(html,["react-pipeline","pipelinecfref","pipelinedirectoryref","translationcfref","pipeline-v2"],900,2600,5)[:30]
    },ensure_ascii=False),flush=True)

    chunk=await c.get(BIO_CHUNK)
    js=chunk.text
    # Extract compact operation/query evidence without dumping the whole bundle.
    gql_evidence=[]
    for key in ["pipelineCfRef","pipelineDirectoryRef","pipeline-v2/endpoint.json","therapeuticAreaList","diseaseList","pipelineData","fragment ","query "]:
        for s in snippets(js,[key],500,1800,6):
            txt=s["text"]
            if txt not in [x["text"] for x in gql_evidence]:
                gql_evidence.append(s)
    print("BIONTECH_GQL_BUNDLE "+json.dumps({
      "status":chunk.status_code,"chars":len(js),"evidence":gql_evidence[:35]
    },ensure_ascii=False),flush=True)

    introspection={"query":"query PipelineDiag { __schema { queryType { fields { name args { name } } } } }"}
    try:
        rr=await c.post(BIO_GQL,json=introspection,headers={"Content-Type":"application/json","Accept":"application/json"})
        parsed=None
        try: parsed=rr.json()
        except Exception: pass
        body=parsed if parsed is not None else compact(rr.text[:3000])
        print("BIONTECH_GQL_INTROSPECTION "+json.dumps({
          "status":rr.status_code,"contentType":rr.headers.get("content-type"),
          "body":body
        },ensure_ascii=False),flush=True)
    except Exception as exc:
        print("BIONTECH_GQL_INTROSPECTION "+json.dumps({"error":f"{type(exc).__name__}: {exc}"}),flush=True)

async def wave(c):
    if not BROWSER_BASE or not BROWSER_KEY:
        print("WAVE_RENDERED_LINES "+json.dumps({"configured":False}),flush=True); return
    r=await c.get(
      BROWSER_BASE+"/fetch/browser",
      params={"url":WAVE,"timeout_seconds":35.0},
      headers={"X-Browser-Key":BROWSER_KEY,"Accept":"application/json"},
    )
    try: p=r.json()
    except Exception: p={}
    print("WAVE_RENDERED_LINES "+json.dumps({
      "status":r.status_code,"version":p.get("version"),"finalUrl":p.get("finalUrl"),
      "visibleLineCount":len(p.get("visibleLines") or []),
      "visibleLines":(p.get("visibleLines") or [])[:140],
      "tables":(p.get("tables") or [])[:8],
      "headings":(p.get("headings") or [])[:40],
      "anchors":[a for a in (p.get("anchors") or []) if any(k in str(a).lower() for k in ["pipeline","clinical","trial","program"])][:50],
    },ensure_ascii=False),flush=True)

async def boehringer(c):
    r=await c.get(BOE)
    body=r.text
    urls=interesting_urls(str(r.url),body,["pipeline","api","json","graphql","drug","asset","phase","program","clinical","content"])
    print("BOEHRINGER_SOURCE_DISCOVERY "+json.dumps({
      "status":r.status_code,"finalUrl":str(r.url),"contentType":r.headers.get("content-type"),"chars":len(body),
      "candidateUrls":urls,
      "snippets":snippets(body,["pipeline","phase 1","phase 2","phase 3","graphql","application/json","__next_data__","drupalsettings","api/"],700,1800,4)[:40]
    },ensure_ascii=False),flush=True)

async def main():
    async with httpx.AsyncClient(timeout=45.0,follow_redirects=True,headers=HEADERS) as c:
        await biontech(c)
        await wave(c)
        await boehringer(c)

if __name__=="__main__":
    asyncio.run(main())
