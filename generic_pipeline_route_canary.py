"""Read-only Boehringer 2025 annual-report snapshot adapter canary."""
import asyncio, json
import boehringer_annual_report_pipeline_extension as bi

async def main():
    try:
        r=await bi.extract_boehringer_annual_pipeline()
        sample=[{
          "ta":x.get("therapeuticArea"),
          "asset":x.get("asset"),
          "code":x.get("developmentCode"),
          "indication":x.get("indication"),
          "phase":x.get("phase"),
        } for x in r.rows[:60]]
        print("BOEHRINGER_ANNUAL_ADAPTER_CANARY "+json.dumps({
          "version":r.version,
          "readyForDiscovery":r.readyForDiscovery,
          "sourceDate":r.sourceDate,
          "sourceProvenance":r.sourceProvenance,
          "retrievalMode":r.retrievalMode,
          "rowCount":r.rowCount,
          "issues":r.issues,
          "diagnostics":r.diagnostics,
          "sample":sample,
          "masterWrites":0,
        },ensure_ascii=False),flush=True)
    except Exception as exc:
        print("BOEHRINGER_ANNUAL_ADAPTER_CANARY "+json.dumps({
          "readyForDiscovery":False,
          "error":f"{type(exc).__name__}: {exc}",
          "masterWrites":0,
        }),flush=True)

if __name__=="__main__":
    asyncio.run(main())
