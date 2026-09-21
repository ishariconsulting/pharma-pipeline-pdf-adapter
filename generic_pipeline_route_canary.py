"""Read-only static-document canary for unresolved pipeline sources."""
import asyncio, json
from generic_pdf_pipeline_extension import extract_generic_pdf

SOURCES=[
 ("Wave Life Sciences","https://ir.wavelifesciences.com/static-files/70d130e3-8c51-4059-9dc4-5b5f117a62fc"),
 ("BioNTech SE","https://investors.biontech.de/static-files/3d7f3499-9d42-4e9d-8dcb-3c5da9be7450"),
 ("Vertex Pharmaceuticals","https://investors.vrtx.com/static-files/25a09e85-5615-46d3-8f28-7e5e75440a14"),
]

async def one(company,url):
    try:
        r=await extract_generic_pdf(company,url,35.0)
        print("STATIC_PIPELINE_CANARY "+json.dumps({
          "company":company,
          "readyForDiscovery":r.readyForDiscovery,
          "rowCount":r.rowCount,
          "issues":[x.get("issue") for x in r.issues],
          "selectedMethod":r.summary.get("selectedMethod"),
          "diagnostics":r.diagnostics,
          "sampleRows":r.rows[:10],
          "masterWrites":0,
        },ensure_ascii=False),flush=True)
    except Exception as exc:
        print("STATIC_PIPELINE_CANARY "+json.dumps({
          "company":company,"readyForDiscovery":False,
          "error":f"{type(exc).__name__}: {exc}","masterWrites":0
        },ensure_ascii=False),flush=True)

async def main():
    for company,url in SOURCES:
        await one(company,url)

if __name__=="__main__":
    asyncio.run(main())
