"""Read-only targeted canary for improved remaining source routes."""
import asyncio, json
from generic_pipeline_extension import _extract_generic_pipeline

SOURCES=[
 ("Merck KGaA","https://www.emdgroup.com/en/research/healthcare-pipeline.html"),
 ("Johnson & Johnson","https://www.investor.jnj.com/pipeline/development-pipeline/default.aspx"),
 ("BioNTech SE","https://www.biontech.com/int/en/home/pipeline-and-products/pipeline.html"),
]

async def one(company,url):
    try:
        r=await _extract_generic_pipeline(company=company,source_url=url,timeout_seconds=28.0)
        print("TARGETED_REMAINING_CANARY "+json.dumps({
          "company":company,"url":url,"readyForDiscovery":r.readyForDiscovery,
          "rowCount":r.rowCount,"retrievalMode":r.summary.get("retrievalMode"),
          "routingReason":r.summary.get("routingReason"),
          "selectedMethod":r.summary.get("selectedMethod"),
          "issues":[x.get("issue") for x in r.issues],
          "diagnostics":r.diagnostics,"sampleRows":r.rows[:8],"masterWrites":0
        },ensure_ascii=False),flush=True)
    except Exception as exc:
        print("TARGETED_REMAINING_CANARY "+json.dumps({
          "company":company,"url":url,"readyForDiscovery":False,
          "error":f"{type(exc).__name__}: {exc}","masterWrites":0
        },ensure_ascii=False),flush=True)

async def main():
    for company,url in SOURCES:
        await one(company,url)

if __name__=="__main__":
    asyncio.run(main())
