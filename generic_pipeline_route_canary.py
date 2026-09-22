"""Read-only Amgen current adapter latency/availability canary."""
import asyncio, json, time
import amgen_json_pipeline_extension as amgen

async def main():
    started=time.time()
    out={"masterWrites":0}
    try:
        r=await amgen.extract_amgen_pipeline(
            "Amgen",
            "https://www.amgenpipeline.com/pipeline/molecule/getjsondata",
            timeout_seconds=20.0,
        )
        out.update({
            "ok":True,
            "elapsedSeconds":round(time.time()-started,3),
            "readyForDiscovery":r.readyForDiscovery,
            "rowCount":r.rowCount,
            "issues":r.issues,
            "finalUrl":r.finalUrl,
            "diagnostics":r.diagnostics,
        })
    except Exception as exc:
        out.update({
            "ok":False,
            "elapsedSeconds":round(time.time()-started,3),
            "error":f"{type(exc).__name__}: {exc}",
        })
    print("AMGEN_CURRENT_ADAPTER_CANARY "+json.dumps(out,ensure_ascii=False),flush=True)

if __name__=="__main__":
    asyncio.run(main())
