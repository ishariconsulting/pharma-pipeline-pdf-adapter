"""Read-only canary for the next unresolved pipeline sources."""
import asyncio, json
from generic_pipeline_extension import _extract_generic_pipeline
from generic_pdf_pipeline_extension import extract_generic_pdf

HTML_SOURCES=[
 ("Johnson & Johnson","https://www.investor.jnj.com/pipeline/development-pipeline/default.aspx"),
 ("Merck KGaA","https://www.reports.emdgroup.com/en/annualreport/2025/management-report/fundamental-information-about-the-group/research-and-development/healthcare.html"),
]
PDF_SOURCES=[
 ("BioNTech SE","https://www.biontech.com/content/dam/biontech-corporate/global/pdf/home/pipeline-and-products/pipeline/assets/BioNTech-Clinical-Pipeline-EN-Q3.pdf"),
]

async def html_one(company,url):
    try:
        r=await _extract_generic_pipeline(company=company,source_url=url,timeout_seconds=30.0)
        payload={
          "company":company,"sourceType":"HTML",
          "readyForDiscovery":r.readyForDiscovery,"rowCount":r.rowCount,
          "retrievalMode":r.summary.get("retrievalMode"),
          "selectedMethod":r.summary.get("selectedMethod"),
          "issues":[x.get("issue") for x in r.issues],
          "diagnostics":r.diagnostics,
          "sampleRows":r.rows[:10],
          "masterWrites":0,
        }
    except Exception as exc:
        payload={"company":company,"sourceType":"HTML","readyForDiscovery":False,"error":f"{type(exc).__name__}: {exc}","masterWrites":0}
    print("NEXT_SOURCE_CANARY "+json.dumps(payload,ensure_ascii=False),flush=True)

async def pdf_one(company,url):
    try:
        r=await extract_generic_pdf(company,url,35.0)
        payload={
          "company":company,"sourceType":"PDF",
          "readyForDiscovery":r.readyForDiscovery,"rowCount":r.rowCount,
          "selectedMethod":r.summary.get("selectedMethod"),
          "issues":[x.get("issue") for x in r.issues],
          "diagnostics":r.diagnostics,
          "sampleRows":r.rows[:10],
          "masterWrites":0,
        }
    except Exception as exc:
        payload={"company":company,"sourceType":"PDF","readyForDiscovery":False,"error":f"{type(exc).__name__}: {exc}","masterWrites":0}
    print("NEXT_SOURCE_CANARY "+json.dumps(payload,ensure_ascii=False),flush=True)

async def main():
    for c,u in HTML_SOURCES:
        await html_one(c,u)
    for c,u in PDF_SOURCES:
        await pdf_one(c,u)

if __name__=="__main__":
    asyncio.run(main())
