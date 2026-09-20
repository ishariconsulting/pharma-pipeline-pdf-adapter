"""Read-only static-document canary for reusable pipeline PDF routing."""
import asyncio, json
from generic_pdf_pipeline_extension import extract_generic_pdf

SOURCES=[
 ("Roche","https://assets.roche.com/f/176343/x/cb875526bd/pharmahy26.pdf"),
 ("argenx SE","https://argenx.com/content/dam/argenx-corp/pipeline/Pipeline_August2026%201.pdf.coredownload.inline.pdf"),
 ("Bayer","https://www.bayer.com/sites/default/files/ph-rd-pipeline-2026-04-29-final.pdf"),
]

async def one(company,url):
    try:
        r=await extract_generic_pdf(company,url,35.0)
        print("STATIC_PDF_PIPELINE_CANARY "+json.dumps({
          "company":company,
          "readyForDiscovery":r.readyForDiscovery,
          "rowCount":r.rowCount,
          "selectedMethod":r.summary.get("selectedMethod"),
          "issues":[x.get("issue") for x in r.issues],
          "diagnostics":{
            "semanticTablePages":r.diagnostics.get("semanticTablePages"),
            "semanticStageBarPages":r.diagnostics.get("semanticStageBarPages"),
            "rowFailures":r.diagnostics.get("rowFailures"),
            "boundaryWarnings":r.diagnostics.get("boundaryWarnings"),
            "exactDuplicatesRemoved":r.diagnostics.get("exactDuplicatesRemoved"),
            "outOfScopeCommercialRows":r.diagnostics.get("outOfScopeCommercialRows"),
          },
          "sampleRows":r.rows[:8],
          "masterWrites":0,
        },ensure_ascii=False),flush=True)
    except Exception as exc:
        print("STATIC_PDF_PIPELINE_CANARY "+json.dumps({
          "company":company,"readyForDiscovery":False,
          "error":f"{type(exc).__name__}: {exc}","masterWrites":0
        },ensure_ascii=False),flush=True)

async def main():
    for company,url in SOURCES:
        await one(company,url)

if __name__=="__main__":
    asyncio.run(main())
