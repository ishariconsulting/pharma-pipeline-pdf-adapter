"""Read-only browser worker contract diagnostic using the production GET contract."""
import asyncio, json, os
import httpx

TARGETS=[
 ("J&J","https://www.investor.jnj.com/pipeline/development-pipeline/default.aspx"),
 ("Vertex","https://www.vrtx.com/our-science/pipeline/"),
 ("Verve","https://www.vervetx.com/our-programs/our-pipeline"),
 ("Wave","https://wavelifesciences.com/pipeline/research-and-development/"),
 ("Boehringer","https://www.boehringer-ingelheim.com/science-innovation/human-health-innovation/pipeline"),
]
BASE=os.environ.get("BROWSER_FETCH_BASE_URL","").rstrip("/")
KEY=os.environ.get("BROWSER_FETCH_KEY","")

async def main():
    print("BROWSER_CONTRACT_ENV "+json.dumps({"configured":bool(BASE and KEY),"base":BASE}),flush=True)
    if not BASE:
        return
    async with httpx.AsyncClient(timeout=50.0,follow_redirects=False) as c:
        try:
            r=await c.get(BASE+"/health",headers={"X-Browser-Key":KEY,"Accept":"application/json"})
            print("BROWSER_HEALTH_PROBE "+json.dumps({
              "status":r.status_code,"contentType":r.headers.get("content-type"),
              "body":r.text[:2000]
            },ensure_ascii=False),flush=True)
        except Exception as exc:
            print("BROWSER_HEALTH_PROBE "+json.dumps({"error":f"{type(exc).__name__}: {exc}"}),flush=True)

        for label,url in TARGETS:
            try:
                r=await c.get(
                    BASE+"/fetch/browser",
                    params={"url":url,"timeout_seconds":35.0},
                    headers={"X-Browser-Key":KEY,"Accept":"application/json"},
                )
                body=r.text
                try: payload=r.json()
                except Exception: payload=None
                print("BROWSER_FETCH_GET_PROBE "+json.dumps({
                  "label":label,"status":r.status_code,
                  "contentType":r.headers.get("content-type"),
                  "json":isinstance(payload,dict),
                  "version":payload.get("version") if isinstance(payload,dict) else None,
                  "finalUrl":payload.get("finalUrl") if isinstance(payload,dict) else None,
                  "statusCode":payload.get("statusCode") if isinstance(payload,dict) else None,
                  "visibleLines":len(payload.get("visibleLines") or []) if isinstance(payload,dict) else None,
                  "tables":len(payload.get("tables") or []) if isinstance(payload,dict) else None,
                  "bodyHead":body[:1200]
                },ensure_ascii=False),flush=True)
            except Exception as exc:
                print("BROWSER_FETCH_GET_PROBE "+json.dumps({
                  "label":label,"error":f"{type(exc).__name__}: {exc}"
                },ensure_ascii=False),flush=True)

if __name__=="__main__":
    asyncio.run(main())
