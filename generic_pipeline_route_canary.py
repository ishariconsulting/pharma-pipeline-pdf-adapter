"""Read-only J&J browser retrieval retry + structure diagnostic."""
import asyncio, json, os
import httpx

URL="https://www.investor.jnj.com/pipeline/development-pipeline/default.aspx"
BASE=os.environ.get("BROWSER_FETCH_BASE_URL","").rstrip("/")
KEY=os.environ.get("BROWSER_FETCH_KEY","")

async def main():
    out={"configured":bool(BASE and KEY),"attempts":[],"masterWrites":0}
    if not BASE or not KEY:
        print("JNJ_BROWSER_RETRY "+json.dumps(out),flush=True)
        return
    async with httpx.AsyncClient(timeout=55.0,follow_redirects=False) as c:
        try:
            h=await c.get(BASE+"/health",headers={"X-Browser-Key":KEY,"Accept":"application/json"})
            out["health"]={"status":h.status_code,"body":h.text[:1200]}
        except Exception as exc:
            out["health"]={"error":f"{type(exc).__name__}: {exc}"}
        for i in range(1,4):
            attempt={"n":i}
            try:
                r=await c.get(
                    BASE+"/fetch/browser",
                    params={"url":URL,"timeout_seconds":35.0},
                    headers={"X-Browser-Key":KEY,"Accept":"application/json"},
                )
                attempt["status"]=r.status_code
                attempt["bodyHead"]=r.text[:1600]
                try: payload=r.json()
                except Exception: payload={}
                if isinstance(payload,dict):
                    attempt["version"]=payload.get("version")
                    attempt["finalUrl"]=payload.get("finalUrl")
                    attempt["visibleLineCount"]=len(payload.get("visibleLines") or [])
                    attempt["visibleLines"]=(payload.get("visibleLines") or [])[:450]
                    attempt["tables"]=payload.get("tables") or []
                    attempt["headings"]=payload.get("headings") or []
                    attempt["anchors"]=(payload.get("anchors") or [])[:120]
                if r.status_code==200 and attempt.get("visibleLineCount",0)>0:
                    out["success"]=True
                    out["selectedAttempt"]=i
                    out["selected"]=attempt
                    out["attempts"].append({k:v for k,v in attempt.items() if k not in {"visibleLines","tables","headings","anchors"}})
                    break
            except Exception as exc:
                attempt["error"]=f"{type(exc).__name__}: {exc}"
            out["attempts"].append(attempt)
            await asyncio.sleep(1.5)
    print("JNJ_BROWSER_RETRY "+json.dumps(out,ensure_ascii=False),flush=True)

if __name__=="__main__":
    asyncio.run(main())
