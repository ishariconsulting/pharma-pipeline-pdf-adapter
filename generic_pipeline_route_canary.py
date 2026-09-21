"""Read-only regression canary for newer generic HTML pipeline interpreter."""
import asyncio, json
from generic_pipeline_extension import _extract_generic_pipeline

SOURCES=[
 ("Johnson & Johnson","https://www.investor.jnj.com/pipeline/development-pipeline/default.aspx"),
 ("Sobi","https://www.sobi.com/en/pipeline"),
 ("Novartis","https://www.novartis.com/research-development/novartis-pipeline"),
 ("Viatris","https://www.viatris.com/en/science"),
]

async def one(company,url):
    try:
        r=await _extract_generic_pipeline(company=company,source_url=url,timeout_seconds=35.0)
        print("GENERIC_HTML_REGRESSION "+json.dumps({
          "company":company,
          "readyForDiscovery":r.readyForDiscovery,
          "rowCount":r.rowCount,
          "retrievalMode":r.summary.get("retrievalMode"),
          "selectedMethod":r.summary.get("selectedMethod"),
          "issues":[x.get("issue") for x in r.issues],
          "coreCompleteRows":r.diagnostics.get("coreCompleteRows"),
          "methods":r.diagnostics.get("methodsEvaluated"),
          "masterWrites":0
        },ensure_ascii=False),flush=True)
    except Exception as exc:
        print("GENERIC_HTML_REGRESSION "+json.dumps({
          "company":company,
          "readyForDiscovery":False,
          "error":f"{type(exc).__name__}: {exc}",
          "masterWrites":0
        },ensure_ascii=False),flush=True)

async def main():
    for company,url in SOURCES:
        await one(company,url)

if __name__=="__main__":
    asyncio.run(main())
