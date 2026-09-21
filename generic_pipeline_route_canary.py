"""Read-only structural canary for remaining unresolved pipeline sources."""
import asyncio, json
from generic_pipeline_extension import _extract_generic_pipeline

SOURCES=[
 ("Johnson & Johnson Innovative Medicine","https://www.investor.jnj.com/pipeline/Innovative-Medicine-pipeline/default.aspx"),
 ("Johnson & Johnson 2026 Key Events","https://www.investor.jnj.com/pipeline/2026-key-events/default.aspx"),
 ("Biogen","https://www.biogen.com/science-and-innovation/pipeline.html"),
 ("Merck KGaA","https://www.emdgroup.com/en/research/our-approach-to-research-and-development/healthcare.html"),
 ("Menarini Group","https://www.menarini.com/en-us/innovation-research/our-pipeline-and-products.html"),
 ("BioNTech SE","https://www.biontech.com/int/en/home/pipeline-and-products/pipeline.html"),
 ("Wave Life Sciences","https://wavelifesciences.com/pipeline/research-and-development/"),
 ("Vertex Pharmaceuticals","https://www.vrtx.com/our-science/pipeline/"),
 ("Boehringer Ingelheim","https://www.boehringer-ingelheim.com/science-innovation/human-health-innovation/pipeline"),
]

async def one(company,url):
    try:
        r=await _extract_generic_pipeline(company=company,source_url=url,timeout_seconds=30.0)
        payload={
          "company":company,
          "readyForDiscovery":r.readyForDiscovery,
          "rowCount":r.rowCount,
          "retrievalMode":r.summary.get("retrievalMode"),
          "routingReason":r.summary.get("routingReason"),
          "selectedMethod":r.summary.get("selectedMethod"),
          "issues":[x.get("issue") for x in r.issues],
          "diagnostics":{
            "semanticTableRows":r.diagnostics.get("semanticTableRows"),
            "labelledFlowRows":r.diagnostics.get("labelledFlowRows"),
            "tableCount":r.diagnostics.get("tableCount"),
            "visibleLineCount":r.diagnostics.get("visibleLineCount"),
            "portfolioDependentValidation":r.diagnostics.get("portfolioDependentValidation")
          },
          "sampleRows":r.rows[:6],
          "masterWrites":0,
        }
    except Exception as exc:
        payload={"company":company,"readyForDiscovery":False,"error":f"{type(exc).__name__}: {exc}","masterWrites":0}
    print("REMAINING_PIPELINE_CANARY "+json.dumps(payload,ensure_ascii=False),flush=True)

async def main():
    for company,url in SOURCES:
        await one(company,url)

if __name__=="__main__":
    asyncio.run(main())
