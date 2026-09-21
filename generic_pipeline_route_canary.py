"""Read-only Menarini AEM content-fragment endpoint probe."""
import asyncio, json, re, html as html_lib
from urllib.parse import urljoin, quote
import httpx

PAGE="https://www.menarini.com/en-us/innovation-research/our-pipeline-and-products.html"
HEADERS={"User-Agent":"Mozilla/5.0 MenariniPipelineProbe/1.0","Accept":"application/json,text/html,*/*;q=0.8"}

def compact(s): return re.sub(r"\s+"," ",str(s or "")).strip()

async def main():
    async with httpx.AsyncClient(timeout=30.0,follow_redirects=True,headers=HEADERS) as c:
        p=await c.get(PAGE); p.raise_for_status()
        html=p.text
        paths=re.findall(r'data-table-cf-path=["\']([^"\']+)["\']',html,re.I)
        paths=list(dict.fromkeys(html_lib.unescape(x) for x in paths))
        print("MENARINI_PATHS "+json.dumps({"count":len(paths),"paths":paths},ensure_ascii=False),flush=True)

        results=[]
        for path in paths[:20]:
            encoded=path.replace("(","%28").replace(")","%29")
            for suffix in [".model.json",".json",".infinity.json",".1.json"]:
                url="https://www.menarini.com"+encoded+suffix
                try:
                    r=await c.get(url)
                    item={"path":path,"suffix":suffix,"url":url,"status":r.status_code,"contentType":r.headers.get("content-type"),"chars":len(r.text)}
                    if r.status_code==200 and "json" in (r.headers.get("content-type") or "").lower():
                        try:
                            data=r.json()
                            item["jsonType"]=type(data).__name__
                            if isinstance(data,dict):
                                item["keys"]=list(data.keys())[:40]
                                item["sample"]=data
                            elif isinstance(data,list):
                                item["sample"]=data[:3]
                        except Exception as exc:
                            item["jsonError"]=str(exc)
                    else:
                        item["head"]=compact(r.text[:800])
                    results.append(item)
                except Exception as exc:
                    results.append({"path":path,"suffix":suffix,"error":f"{type(exc).__name__}: {exc}"})
        print("MENARINI_ENDPOINT_RESULTS "+json.dumps(results,ensure_ascii=False),flush=True)

if __name__=="__main__":
    asyncio.run(main())
