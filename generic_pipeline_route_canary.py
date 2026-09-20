"""Read-only canary for static pipeline routes."""
import asyncio, json
from generic_pdf_pipeline_extension import extract_generic_pdf
from lilly_static_extension import extract_lilly_pipeline_compat

TAKEDA="https://assets-dam.takeda.com/image/upload/v1785376660/Global/Investor/Financial-Results/FY2026/Q1/qr2026_q1_Pipeline_table_en.pdf"
ROCHE="https://assets.roche.com/f/176343/x/cb875526bd/pharmahy26.pdf"
ARGENX="https://argenx.com/content/dam/argenx-corp/pipeline/Pipeline_August2026%201.pdf.coredownload.inline.pdf"

async def test_pdf(company,url):
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
    print("STATIC_ROUTE_PDF_CANARY "+json.dumps(payload,ensure_ascii=False),flush=True)

async def main():
    await test_pdf("Takeda",TAKEDA)
    await test_pdf("Roche",ROCHE)
    await test_pdf("argenx SE",ARGENX)
    try:
        r=extract_lilly_pipeline_compat()
        payload={
          "company":r.company,
          "readyForDiscovery":r.readyForDiscovery,
          "rowCount":r.rowCount,
          "summary":r.summary,
          "diagnostics":r.diagnostics,
          "sampleRows":r.rows[:8],
          "masterWrites":0,
        }
    except Exception as exc:
        payload={"company":"Eli Lilly and Company","readyForDiscovery":False,"error":f"{type(exc).__name__}: {exc}","masterWrites":0}
    print("STATIC_ROUTE_LILLY_CANARY "+json.dumps(payload,ensure_ascii=False),flush=True)

if __name__=="__main__":
    asyncio.run(main())
