"""Read-only generic pipeline routing canary for J&J and Wave."""
import asyncio, json

import generic_pipeline_extension as gp

TARGETS=[
 ("J&J","Johnson & Johnson","https://www.investor.jnj.com/pipeline/development-pipeline/default.aspx"),
 ("Wave","Wave Life Sciences","https://wavelifesciences.com/pipeline/research-and-development/"),
]

async def main():
    for label,company,url in TARGETS:
        try:
            r=await gp._extract_generic_pipeline(
                company=company,
                source_url=url,
                timeout_seconds=35.0,
            )
            rows=[x for x in r.rows]
            print("GENERIC_PIPELINE_ROUTE_CANARY "+json.dumps({
              "label":label,
              "company":company,
              "readyForDiscovery":r.readyForDiscovery,
              "rowCount":r.rowCount,
              "retrievalMode":r.diagnostics.get("retrievalMode"),
              "routingReason":r.diagnostics.get("routingReason"),
              "browserVersion":r.diagnostics.get("browserVersion"),
              "directFailure":r.diagnostics.get("directFailure"),
              "issues":r.issues,
              "diagnostics":r.diagnostics,
              "sampleRows":rows[:15],
              "masterWrites":0,
            },ensure_ascii=False),flush=True)
        except Exception as exc:
            print("GENERIC_PIPELINE_ROUTE_CANARY "+json.dumps({
              "label":label,
              "company":company,
              "readyForDiscovery":False,
              "error":f"{type(exc).__name__}: {exc}",
              "masterWrites":0,
            },ensure_ascii=False),flush=True)

if __name__=="__main__":
    asyncio.run(main())
