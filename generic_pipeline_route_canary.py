"""Read-only J&J rendered pipeline structure diagnostic."""
import asyncio, json, os
import httpx

URL="https://www.investor.jnj.com/pipeline/development-pipeline/default.aspx"
BASE=os.environ.get("BROWSER_FETCH_BASE_URL","").rstrip("/")
KEY=os.environ.get("BROWSER_FETCH_KEY","")

async def main():
    if not BASE or not KEY:
        print("JNJ_RENDERED_STRUCTURE "+json.dumps({"configured":False,"masterWrites":0}),flush=True)
        return
    async with httpx.AsyncClient(timeout=55.0,follow_redirects=False) as c:
        r=await c.get(
            BASE+"/fetch/browser",
            params={"url":URL,"timeout_seconds":35.0},
            headers={"X-Browser-Key":KEY,"Accept":"application/json"},
        )
        try:
            payload=r.json()
        except Exception:
            payload={}
        print("JNJ_RENDERED_STRUCTURE "+json.dumps({
            "status":r.status_code,
            "version":payload.get("version"),
            "finalUrl":payload.get("finalUrl"),
            "visibleLineCount":len(payload.get("visibleLines") or []),
            "visibleLines":payload.get("visibleLines") or [],
            "tables":payload.get("tables") or [],
            "headings":payload.get("headings") or [],
            "anchors":payload.get("anchors") or [],
            "masterWrites":0
        },ensure_ascii=False),flush=True)

if __name__=="__main__":
    asyncio.run(main())
