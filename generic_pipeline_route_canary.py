"""Read-only Vertex generic pipeline extraction probe."""
import asyncio, json
import generic_pipeline_extension as g

URL="https://www.vrtx.com/our-science/pipeline/"

async def main():
    try:
        r=await g._extract_generic_pipeline(
            company="Vertex Pharmaceuticals",
            source_url=URL,
            timeout_seconds=35.0,
        )
        print("VERTEX_GENERIC_PIPELINE_PROBE "+json.dumps({
          "version":r.version,
          "routeVersion":r.routeVersion,
          "readyForDiscovery":r.readyForDiscovery,
          "rowCount":r.rowCount,
          "summary":r.summary,
          "issues":r.issues,
          "diagnostics":r.diagnostics,
          "sample":r.rows[:50],
          "masterWrites":0,
        },ensure_ascii=False),flush=True)
    except Exception as exc:
        print("VERTEX_GENERIC_PIPELINE_PROBE "+json.dumps({
          "readyForDiscovery":False,
          "error":f"{type(exc).__name__}: {exc}",
          "masterWrites":0,
        }),flush=True)

if __name__=="__main__":
    asyncio.run(main())
