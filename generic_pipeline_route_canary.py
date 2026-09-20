"""Read-only canary for the reusable semantic PDF pipeline table adapter."""
import asyncio, json
from generic_pdf_pipeline_extension import extract_generic_pdf

SOURCES=[
 ("Takeda","https://assets-dam.takeda.com/image/upload/v1785376660/Global/Investor/Financial-Results/FY2026/Q1/qr2026_q1_Pipeline_table_en.pdf"),
 ("Roche","https://assets.roche.com/f/176343/x/cb875526bd/pharmahy26.pdf"),
 ("argenx SE","https://argenx.com/content/dam/argenx-corp/pipeline/Pipeline_August2026%201.pdf.coredownload.inline.pdf"),
]

async def one(company,url):
    try:
        r=await extract_generic_pdf(company,url,35.0)
        payload={
          "company":company,
          "readyForDiscovery":r.readyForDiscovery,
          "rowCount":r.rowCount,
          "validation":r.validation,
          "diagnostics":r.diagnostics,
          "sampleRows":r.rows[:12],
          "masterWrites":0,
        }
    except Exception as exc:
        payload={"company":company,"readyForDiscovery":False,"error":f"{type(exc).__name__}: {exc}","masterWrites":0}
    print("GENERIC_PDF_CANARY "+json.dumps(payload,ensure_ascii=False),flush=True)

async def main():
    for company,url in SOURCES:
        await one(company,url)

if __name__=="__main__":
    asyncio.run(main())
