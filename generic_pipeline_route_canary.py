"""Read-only canary for reusable semantic JSON pipeline adapter."""
import asyncio, json
from generic_json_pipeline_extension import extract_generic_json

URL="https://www.biogen.com/content/dam/corporate/international/global/en-US/global/json/pipeline-production.json"

async def main():
    try:
        r=await extract_generic_json("Biogen",URL,35.0)
        print("GENERIC_JSON_CANARY "+json.dumps({
          "version":r.version,
          "readyForDiscovery":r.readyForDiscovery,
          "rowCount":r.rowCount,
          "issues":[x.get("issue") for x in r.issues],
          "diagnostics":r.diagnostics,
          "phaseCounts":{
            p:sum(1 for x in r.rows if x.get("phase")==p)
            for p in sorted(set(x.get("phase") for x in r.rows))
          },
          "sampleRows":r.rows[:10],
          "masterWrites":0
        },ensure_ascii=False),flush=True)
    except Exception as exc:
        print("GENERIC_JSON_CANARY "+json.dumps({
          "readyForDiscovery":False,
          "error":f"{type(exc).__name__}: {exc}",
          "masterWrites":0
        },ensure_ascii=False),flush=True)

if __name__=="__main__":
    asyncio.run(main())
