"""Read-only J&J generic pipeline/browser fallback live canary."""
import asyncio, json, time
import generic_pipeline_extension as gp

URL="https://www.investor.jnj.com/pipeline/development-pipeline/default.aspx"

async def main():
    started=time.time()
    out={"masterWrites":0,"sourceUrl":URL}
    try:
        r=await gp._extract_generic_pipeline(
            company="Johnson & Johnson",
            source_url=URL,
            timeout_seconds=25.0,
        )
        out.update({
            "ok":True,
            "elapsedSeconds":round(time.time()-started,3),
            "readyForDiscovery":r.readyForDiscovery,
            "rowCount":r.rowCount,
            "retrievalMode":r.summary.get("retrievalMode"),
            "routingReason":r.summary.get("routingReason"),
            "browserVersion":r.summary.get("browserVersion"),
            "issues":r.issues,
            "selectedMethod":r.summary.get("selectedMethod"),
        })
    except Exception as exc:
        detail=getattr(exc,"detail",None)
        out.update({
            "ok":False,
            "elapsedSeconds":round(time.time()-started,3),
            "error":f"{type(exc).__name__}: {exc}",
            "detail":detail,
        })
    print("JNJ_GENERIC_BROWSER_LIVE_CANARY "+json.dumps(out,ensure_ascii=False),flush=True)

if __name__=="__main__":
    asyncio.run(main())
