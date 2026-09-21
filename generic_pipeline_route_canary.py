"""Read-only Bayer generic-PDF production-contract canary."""
import asyncio, json
from generic_pdf_pipeline_extension import extract_generic_pdf

URL="https://www.bayer.com/sites/default/files/ph-rd-pipeline-2026-07-21-final-updated.pdf"

async def main():
    try:
        r=await extract_generic_pdf("Bayer",URL,35.0)
        print("BAYER_GENERIC_PDF_CANARY "+json.dumps({
          "readyForDiscovery":r.readyForDiscovery,
          "rowCount":r.rowCount,
          "issues":[x.get("issue") for x in r.issues],
          "summary":r.summary,
          "diagnostics":r.diagnostics,
          "sample":r.rows[:12],
          "masterWrites":0
        },ensure_ascii=False),flush=True)
    except Exception as exc:
        print("BAYER_GENERIC_PDF_CANARY "+json.dumps({
          "readyForDiscovery":False,
          "error":f"{type(exc).__name__}: {exc}",
          "masterWrites":0
        },ensure_ascii=False),flush=True)

if __name__=="__main__":
    asyncio.run(main())
