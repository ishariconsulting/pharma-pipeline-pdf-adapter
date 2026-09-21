"""Read-only structural canary for remaining pipeline sources."""
import asyncio, json
from generic_pipeline_extension import _extract_generic_pipeline

SOURCES=[
 ("Johnson & Johnson","https://www.investor.jnj.com/pipeline/development-pipeline/default.aspx"),
 ("Menarini Group","https://www.menarini.com/en-us/innovation-research/our-pipeline-and-products.html"),
 ("BioNTech SE","https://www.biontech.com/int/en/home/pipeline-and-products/pipeline.html"),
 ("Biogen","https://www.biogen.com/science-and-innovation/pipeline.html"),
 ("Wave Life Sciences","https://wavelifesciences.com/pipeline/research-and-development/"),
 ("Vertex Pharmaceuticals","https://www.vrtx.com/our-science/pipeline/"),
 ("Verve Therapeutics","https://www.vervetx.com/our-programs/our-pipeline"),
 ("Boehringer Ingelheim","https://www.boehringer-ingelheim.com/science-innovation/human-health-innovation/pipeline"),
]

async def one(company,url):
    try:
        r=await _extract_generic_pipeline(company=company,source_url=url,timeout_seconds=28.0)
        print("REMAINING_PIPELINE_CANARY "+json.dumps({
          "company":company,
          "readyForDiscovery":r.readyForDiscovery,
          "rowCount":r.rowCount,
          "retrievalMode":r.summary.get("retrievalMode"),
          "routingReason":r.summary.get("routingReason"),
          "selectedMethod":r.summary.get("selectedMethod"),
          "issues":[x.get("issue") for x in r.issues],
          "diagnostics":r.diagnostics,
          "sampleRows":r.rows[:6],
          "masterWrites":0,
        },ensure_ascii=False),flush=True)
    except Exception as exc:
        print("REMAINING_PIPELINE_CANARY "+json.dumps({
          "company":company,"readyForDiscovery":False,
          "error":f"{type(exc).__name__}: {exc}","masterWrites":0
        },ensure_ascii=False),flush=True)

async def main():
    for company,url in SOURCES:
        await one(company,url)

if __name__=="__main__":
    asyncio.run(main())
