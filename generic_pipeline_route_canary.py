"""Read-only browser worker contract diagnostic."""
import asyncio, json, os, hashlib
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
    print("CANARY_KEY_FINGERPRINT "+json.dumps({
        "configured":bool(KEY),
        "sha256_12":hashlib.sha256(KEY.encode("utf-8")).hexdigest()[:12] if KEY else None,
        "length":len(KEY)
    }),flush=True)
    print("BROWSER_CONTRACT_ENV "+json.dumps({"configured":bool(BASE and KEY),"base":BASE}),flush=True)
    if not BASE:
        return
    async with httpx.AsyncClient(timeout=45.0,follow_redirects=True) as c:
        try:
            r=await c.get(BASE+"/health",headers={"x-browser-fetch-key":KEY})
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
                    headers={"x-browser-key":KEY,"Accept":"application/json"},
                    params={"url":url,"timeout_seconds":35.0},
                )
                print("BROWSER_FETCH_PROBE "+json.dumps({
                  "label":label,"status":r.status_code,
                  "contentType":r.headers.get("content-type"),
                  "body":r.text[:3500]
                },ensure_ascii=False),flush=True)
            except Exception as exc:
                print("BROWSER_FETCH_PROBE "+json.dumps({
                  "label":label,"error":f"{type(exc).__name__}: {exc}"
                },ensure_ascii=False),flush=True)

if __name__=="__main__":
    asyncio.run(main())
