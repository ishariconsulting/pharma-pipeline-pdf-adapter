"""Read-only Vertex official pipeline browser-retrieval diagnostic."""
import asyncio, json, os
import httpx

URL="https://www.vrtx.com/our-science/pipeline/"
BASE=os.environ.get("BROWSER_FETCH_BASE_URL","").rstrip("/")
KEY=os.environ.get("BROWSER_FETCH_KEY","")

async def main():
    out={"sourceUrl":URL,"configured":bool(BASE and KEY),"masterWrites":0}
    if not BASE or not KEY:
        print("VERTEX_BROWSER_PIPELINE_DIAGNOSTIC "+json.dumps(out),flush=True)
        return
    async with httpx.AsyncClient(timeout=65.0,follow_redirects=False) as c:
        try:
            r=await c.get(
                BASE+"/fetch/browser",
                params={"url":URL,"timeout_seconds":35.0,"expand_load_more":True,"include_layout":True},
                headers={"X-Browser-Key":KEY,"Accept":"application/json"},
            )
            try:
                p=r.json()
            except Exception:
                p={}
            lines=p.get("visibleLines") or []
            headings=p.get("headings") or []
            tables=p.get("tables") or []
            layout=p.get("layoutTextNodes") or []
            out.update({
                "status":r.status_code,
                "version":p.get("version"),
                "finalUrl":p.get("finalUrl"),
                "httpStatus":p.get("httpStatus"),
                "title":p.get("title"),
                "visibleTextLength":p.get("visibleTextLength"),
                "expansionClicks":p.get("expansionClicks"),
                "headings":headings[:80],
                "tables":tables[:12],
                "visibleLines":[x for x in lines if any(k in x.lower() for k in (
                    "phase","vx-","povetacicept","inaxaplin","suzetrigine","zimislecel",
                    "cystic","kidney","pain","diabetes","pipeline","clinical"
                ))][:250],
                "layoutNodes":[x for x in layout if any(k in str(x).lower() for k in (
                    "phase","vx-","povetacicept","inaxaplin","suzetrigine","zimislecel","pipeline"
                ))][:300],
                "bodyHead":r.text[:1200] if r.status_code!=200 else None,
            })
        except Exception as exc:
            out["error"]=f"{type(exc).__name__}: {exc}"
    print("VERTEX_BROWSER_PIPELINE_DIAGNOSTIC "+json.dumps(out,ensure_ascii=False),flush=True)

if __name__=="__main__":
    asyncio.run(main())
