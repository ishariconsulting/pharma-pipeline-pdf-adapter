"""Read-only canary for the Amgen public pipeline JSON adapter."""
import asyncio, json
from amgen_json_pipeline_extension import extract_amgen_pipeline

async def main():
    try:
        r=await extract_amgen_pipeline("Amgen","https://www.amgenpipeline.com/",35.0)
        phases={}
        for row in r.rows:
            phases[row["phase"]]=phases.get(row["phase"],0)+1
        print("AMGEN_JSON_ADAPTER_CANARY "+json.dumps({
          "readyForDiscovery":r.readyForDiscovery,
          "rowCount":r.rowCount,
          "phaseCounts":phases,
          "issues":[x.get("issue") for x in r.issues],
          "diagnostics":r.diagnostics,
          "sample":r.rows[:12],
          "masterWrites":0
        },ensure_ascii=False),flush=True)
    except Exception as exc:
        print("AMGEN_JSON_ADAPTER_CANARY "+json.dumps({"readyForDiscovery":False,"error":f"{type(exc).__name__}: {exc}","masterWrites":0},ensure_ascii=False),flush=True)

if __name__=="__main__":
    asyncio.run(main())
