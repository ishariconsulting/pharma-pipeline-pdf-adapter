"""Read-only Boehringer pipeline network-source discovery diagnostic."""
import asyncio, json, os
import httpx

URL="https://www.boehringer-ingelheim.com/science-innovation/human-health-innovation/pipeline"
BASE=os.environ.get("BROWSER_FETCH_BASE_URL","").rstrip("/")
KEY=os.environ.get("BROWSER_FETCH_KEY","")

async def main():
    out={"configured":bool(BASE and KEY),"masterWrites":0}
    if not BASE or not KEY:
        print("BOEHRINGER_NETWORK_DISCOVERY "+json.dumps(out),flush=True)
        return
    async with httpx.AsyncClient(timeout=65.0,follow_redirects=False) as c:
        try:
            r=await c.get(
                BASE+"/diagnostic/network-sources",
                params={"url":URL,"timeout_seconds":35.0},
                headers={"X-Browser-Key":KEY,"Accept":"application/json"},
            )
            body=r.text
            try:
                p=r.json()
            except Exception:
                p={}
            responses=p.get("responses") or []
            out.update({
                "status":r.status_code,
                "version":p.get("version"),
                "finalUrl":p.get("finalUrl"),
                "documentStatus":p.get("documentStatus"),
                "title":p.get("title"),
                "visibleTextLength":p.get("visibleTextLength"),
                "responseCount":p.get("responseCount"),
                "responses":responses[:120],
                "bodyHead":body[:1200] if r.status_code != 200 else None,
            })
        except Exception as exc:
            out["error"]=f"{type(exc).__name__}: {exc}"
    print("BOEHRINGER_NETWORK_DISCOVERY "+json.dumps(out,ensure_ascii=False),flush=True)

if __name__=="__main__":
    asyncio.run(main())
