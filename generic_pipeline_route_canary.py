"""Read-only validation canary for BioNTech AEM GraphQL pipeline adapter."""
import asyncio, json
from biontech_graphql_pipeline_extension import extract_biontech_pipeline

async def main():
    try:
        r=await extract_biontech_pipeline()
        print("BIONTECH_GRAPHQL_CANARY "+json.dumps({
          "readyForDiscovery":r.readyForDiscovery,
          "rowCount":r.rowCount,
          "issues":[x.get("issue") for x in r.issues],
          "diagnostics":r.diagnostics,
          "sampleRows":r.rows[:20],
          "masterWrites":0
        },ensure_ascii=False),flush=True)
    except Exception as exc:
        print("BIONTECH_GRAPHQL_CANARY "+json.dumps({
          "readyForDiscovery":False,
          "error":f"{type(exc).__name__}: {exc}",
          "masterWrites":0
        },ensure_ascii=False),flush=True)

if __name__=="__main__":
    asyncio.run(main())
