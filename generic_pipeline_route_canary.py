"""Read-only canary for reusable rendered-flow pipeline strategies."""
import asyncio, json
from generic_pipeline_extension import _extract_generic_pipeline

SOURCES=[
 ("Johnson & Johnson","https://www.investor.jnj.com/pipeline/development-pipeline/default.aspx"),
 ("BioNTech SE","https://www.biontech.com/int/en/home/pipeline-and-products/pipeline.html"),
 ("Wave Life Sciences","https://wavelifesciences.com/pipeline/research-and-development/"),
]

async def one(company,url):
    try:
        r=await _extract_generic_pipeline(company=company,source_url=url,timeout_seconds=30.0)
        print("RENDERED_FLOW_CANARY "+json.dumps({
          "company":company,
          "readyForDiscovery":r.readyForDiscovery,
          "rowCount":r.rowCount,
          "retrievalMode":r.summary.get("retrievalMode"),
          "routingReason":r.summary.get("routingReason"),
          "selectedMethod":r.summary.get("selectedMethod"),
          "issues":[x.get("issue") for x in r.issues],
          "diagnostics":r.diagnostics,
          "sampleRows":r.rows[:12],
          "masterWrites":0,
        },ensure_ascii=False),flush=True)
    except Exception as exc:
        print("RENDERED_FLOW_CANARY "+json.dumps({
          "company":company,"readyForDiscovery":False,
          "error":f"{type(exc).__name__}: {exc}","masterWrites":0
        },ensure_ascii=False),flush=True)

async def main():
    for company,url in SOURCES:
        await one(company,url)

if __name__=="__main__":
    asyncio.run(main())
