"""Read-only reproduction of Airtable V2.60 BMS route."""
import asyncio, json, os
import httpx
import service_entrypoint

SOURCE_URL="https://www.bms.com/research-and-development/pipeline.html"
PATH="/extract-bms-v4"

async def main():
    key=os.environ.get("ADAPTER_API_KEY","")
    out={"profile":"PIPELINE_BMS_HTML_V1.3","path":PATH,"requestShape":"V2.60_SPECIALISED_SOURCE_URL_ONLY","masterWrites":0}
    transport=httpx.ASGITransport(app=service_entrypoint.app)
    try:
        async with httpx.AsyncClient(transport=transport,base_url="http://adapter.local",timeout=180.0) as client:
            r=await client.get(PATH,params={"source_url":SOURCE_URL},headers={"Accept":"application/json","X-Adapter-Key":key})
        out["status"]=r.status_code
        try:p=r.json()
        except Exception:p={}
        rows=p.get("rows") or []
        out.update({
          "version":p.get("version"),
          "rowCount":len(rows),
          "structuralValidationPass":(p.get("summary") or {}).get("structuralValidationPass"),
          "issues":p.get("issues") or [],
          "diagnostics":{k:(p.get("diagnostics") or {}).get(k) for k in [
              "browserWorkerBase","browserVersion","browserHttpStatus","browserAttempt",
              "cacheHit","rowFailures","phaseUnresolved","exactDuplicates"
          ]},
          "bodyHead":r.text[:1600] if r.status_code!=200 else None,
        })
    except Exception as exc:
        out["error"]=f"{type(exc).__name__}: {exc}"
    print("V260_BMS_ROUTE_REPRO "+json.dumps(out,ensure_ascii=False),flush=True)

if __name__=="__main__":
    asyncio.run(main())
