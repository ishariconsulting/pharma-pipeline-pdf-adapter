"""Read-only Roche semantic phase-column PDF canary."""
import asyncio, json
from generic_pdf_pipeline_extension import extract_generic_pdf

URL="https://assets.roche.com/f/176343/x/cb875526bd/pharmahy26.pdf"

async def main():
    try:
        r=await extract_generic_pdf("Roche",URL,35.0)
        print("ROCHE_PHASE_COLUMN_CANARY "+json.dumps({
          "readyForDiscovery":r.readyForDiscovery,
          "rowCount":r.rowCount,
          "selectedMethod":r.summary.get("selectedMethod"),
          "issues":[x.get("issue") for x in r.issues],
          "diagnostics":r.diagnostics,
          "sampleRows":r.rows[:20],
          "masterWrites":0
        },ensure_ascii=False),flush=True)
    except Exception as exc:
        print("ROCHE_PHASE_COLUMN_CANARY "+json.dumps({
          "readyForDiscovery":False,
          "error":f"{type(exc).__name__}: {exc}",
          "masterWrites":0
        },ensure_ascii=False),flush=True)

if __name__=="__main__":
    asyncio.run(main())
