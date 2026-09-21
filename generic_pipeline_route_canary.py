"""Read-only network/source discovery for Novo Nordisk, Alnylam and Dyne."""
import asyncio, json, os, re
import httpx

BASE=os.environ.get("BROWSER_FETCH_BASE_URL","").rstrip("/")
KEY=os.environ.get("BROWSER_FETCH_KEY","")
SOURCES=[
 ("NOVO","https://www.novonordisk.com/science-and-technology/r-d-pipeline.html"),
 ("ALNYLAM","https://www.alnylam.com/alnylam-rnai-pipeline"),
 ("DYNE","https://www.dyne-tx.com/pipeline/"),
]

async def one(client,label,url):
    out={"label":label,"url":url,"masterWrites":0}
    try:
        r=await client.get(
            BASE+"/diagnostic/network-sources",
            params={"url":url,"timeout_seconds":35.0},
            headers={"X-Browser-Key":KEY,"Accept":"application/json"},
        )
        out["status"]=r.status_code
        try:p=r.json()
        except Exception:p={}
        responses=p.get("responses") or []
        out.update({
          "version":p.get("version"),
          "finalUrl":p.get("finalUrl"),
          "documentStatus":p.get("documentStatus"),
          "title":p.get("title"),
          "visibleTextLength":p.get("visibleTextLength"),
          "responseCount":p.get("responseCount"),
          "responses":responses[:120],
          "bodyHead":r.text[:1000] if r.status_code!=200 else None,
        })
    except Exception as exc:
        out["error"]=f"{type(exc).__name__}: {exc}"
    return out

async def main():
    if not BASE or not KEY:
        print("THREE_SOURCE_NETWORK_DISCOVERY "+json.dumps({"configured":False,"masterWrites":0}),flush=True)
        return
    async with httpx.AsyncClient(timeout=70.0,follow_redirects=False) as client:
        results=[]
        for item in SOURCES:
            results.append(await one(client,*item))
    print("THREE_SOURCE_NETWORK_DISCOVERY "+json.dumps({"results":results,"masterWrites":0},ensure_ascii=False),flush=True)

if __name__=="__main__":
    asyncio.run(main())
