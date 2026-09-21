"""Read-only Merck KGaA first-party pipeline data.js probe."""
import asyncio, json
import merck_kgaa_js_pipeline_extension as m

async def main():
    try:
        r=await m.extract_merck_pipeline(
            company="Merck KGaA",
            source_url=m.DEFAULT_DATA_URL,
            timeout_seconds=35.0,
        )
        print("MERCK_KGAA_JS_PIPELINE_CANARY "+json.dumps({
          "version":r.version,
          "routeVersion":r.routeVersion,
          "readyForDiscovery":r.readyForDiscovery,
          "rowCount":r.rowCount,
          "summary":r.summary,
          "issues":r.issues,
          "diagnostics":r.diagnostics,
          "sample":r.rows[:80],
          "masterWrites":0,
        },ensure_ascii=False),flush=True)
    except Exception as exc:
        print("MERCK_KGAA_JS_PIPELINE_CANARY "+json.dumps({
          "readyForDiscovery":False,
          "error":f"{type(exc).__name__}: {exc}",
          "masterWrites":0,
        }),flush=True)

if __name__=="__main__":
    asyncio.run(main())
