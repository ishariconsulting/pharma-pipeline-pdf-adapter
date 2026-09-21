"""Read-only J&J reconciliation + Wave route diagnostic startup canary."""
import asyncio, json

import generic_pipeline_extension as gp
import jnj_reconciliation_canary as jnj

WAVE_URL="https://wavelifesciences.com/pipeline/research-and-development/"

async def main():
    try:
        result=await jnj.run_canary()
        print("JNJ_RECONCILIATION_CANARY "+json.dumps(result,ensure_ascii=False),flush=True)
    except Exception as exc:
        print("JNJ_RECONCILIATION_CANARY "+json.dumps({
          "readyForBindingValidation":False,
          "error":f"{type(exc).__name__}: {exc}",
          "masterWrites":0
        }),flush=True)

    try:
        wave=await gp._extract_generic_pipeline(
            company="Wave Life Sciences",
            source_url=WAVE_URL,
            timeout_seconds=35.0,
        )
        print("WAVE_ROUTE_DIAGNOSTIC "+json.dumps({
          "readyForDiscovery":wave.readyForDiscovery,
          "rowCount":wave.rowCount,
          "retrievalMode":wave.diagnostics.get("retrievalMode"),
          "selectedMethod":wave.diagnostics.get("selectedMethod"),
          "visibleLineCount":wave.diagnostics.get("visibleLineCount"),
          "issues":wave.issues,
          "masterWrites":0
        },ensure_ascii=False),flush=True)
    except Exception as exc:
        print("WAVE_ROUTE_DIAGNOSTIC "+json.dumps({
          "readyForDiscovery":False,
          "error":f"{type(exc).__name__}: {exc}",
          "masterWrites":0
        }),flush=True)

if __name__=="__main__":
    asyncio.run(main())
