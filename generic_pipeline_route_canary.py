"""Read-only structural canary for official pipeline HTML sources."""
import asyncio, json
from generic_pipeline_extension import _extract_generic_pipeline

SOURCES=[
 ("Bayer","https://www.bayer.com/en/pharma/development-pipeline"),
 ("Roche","https://www.roche.com/solutions/pipeline"),
 ("argenx SE","https://argenx.com/pipeline"),
]

async def one(company,url):
    try:
        r=await _extract_generic_pipeline(company=company,source_url=url,timeout_seconds=28.0)
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
             "portfolioDependentValidation":r.diagnostics.get("portfolioDependentValidation"),
          },
          "sampleRows":r.rows[:8],
          "masterWrites":0,
        }
    except Exception as exc:
        payload={"company":company,"readyForDiscovery":False,"error":f"{type(exc).__name__}: {exc}","masterWrites":0}
    print("GENERIC_HTML_PIPELINE_CANARY "+json.dumps(payload,ensure_ascii=False),flush=True)

async def main():
    for company,url in SOURCES:
        await one(company,url)

if __name__=="__main__":
    asyncio.run(main())
