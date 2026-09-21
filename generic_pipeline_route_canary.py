"""Read-only focused canary for J&J browser fallback and Merck KGaA PDF."""
import asyncio, json
from generic_pipeline_extension import _extract_generic_pipeline
from generic_pdf_pipeline_extension import extract_generic_pdf

JNJ_URL="https://www.investor.jnj.com/pipeline/development-pipeline/default.aspx"
MERCK_PDF="https://reporting.emdgroup.com/2026-Q1-Earnings-Presentation-NA.pdf"

async def jnj():
    try:
        r=await _extract_generic_pipeline(
            company="Johnson & Johnson",
            source_url=JNJ_URL,
            timeout_seconds=35.0,
        )
        print("JNJ_BROWSER_FINAL_CANARY "+json.dumps({
            "readyForDiscovery":r.readyForDiscovery,
            "rowCount":r.rowCount,
            "retrievalMode":r.summary.get("retrievalMode"),
            "routingReason":r.summary.get("routingReason"),
            "selectedMethod":r.summary.get("selectedMethod"),
            "issues":[x.get("issue") for x in r.issues],
            "diagnostics":r.diagnostics,
            "sampleRows":r.rows[:10],
            "masterWrites":0,
        },ensure_ascii=False),flush=True)
    except Exception as exc:
        print("JNJ_BROWSER_FINAL_CANARY "+json.dumps({
            "readyForDiscovery":False,
            "error":f"{type(exc).__name__}: {exc}",
            "masterWrites":0,
        },ensure_ascii=False),flush=True)

async def merck():
    try:
        r=await extract_generic_pdf(
            "Merck KGaA",
            MERCK_PDF,
            35.0,
        )
        print("MERCK_Q1_PDF_CANARY "+json.dumps({
            "readyForDiscovery":r.readyForDiscovery,
            "rowCount":r.rowCount,
            "issues":[x.get("issue") for x in r.issues],
            "summary":r.summary,
            "diagnostics":r.diagnostics,
            "sampleRows":r.rows[:12],
            "masterWrites":0,
        },ensure_ascii=False),flush=True)
    except Exception as exc:
        print("MERCK_Q1_PDF_CANARY "+json.dumps({
            "readyForDiscovery":False,
            "error":f"{type(exc).__name__}: {exc}",
            "masterWrites":0,
        },ensure_ascii=False),flush=True)

async def main():
    await jnj()
    await merck()

if __name__=="__main__":
    asyncio.run(main())
