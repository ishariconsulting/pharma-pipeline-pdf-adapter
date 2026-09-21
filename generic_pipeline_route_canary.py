"""Read-only reproduction of Airtable V2.60 routing for Merck & Co."""
import asyncio, json, os
import httpx
import service_entrypoint

COMPANY="Merck & Co. (MSD)"
SOURCE_URL="https://www.merck.com/research/product-pipeline/"
PATH="/extract/generic/pipeline"

async def main():
    key=os.environ.get("ADAPTER_API_KEY","")
    out={"profile":"PIPELINE_GENERIC_HTML_V1","path":PATH,"requestShape":"V2.60_COMMON_CONTRACT","masterWrites":0}
    transport=httpx.ASGITransport(app=service_entrypoint.app)
    try:
        async with httpx.AsyncClient(transport=transport,base_url="http://adapter.local",timeout=70.0) as client:
            r=await client.get(PATH,params={"company":COMPANY,"source_url":SOURCE_URL},headers={"Accept":"application/json","X-Adapter-Key":key})
        out["status"]=r.status_code
        try:p=r.json()
        except Exception:p={}
        rows=p.get("rows") or []
        issues=p.get("issues") or []
        diag=p.get("diagnostics") or {}
        summary=p.get("summary") or {}
        out.update({
          "version":p.get("version"),"readyForDiscovery":p.get("readyForDiscovery"),
          "rowCount":len(rows),
          "coreCompleteRows":sum(1 for x in rows if str(x.get("asset") or "").strip() and str(x.get("indication") or "").strip() and str(x.get("phase") or "").strip()),
          "structuralValidationPass":summary.get("structuralValidationPass"),
          "issues":issues,
          "selectedMethod":summary.get("selectedMethod"),
          "rowFailures":diag.get("rowFailures"),
          "phaseUnresolved":diag.get("phaseUnresolved"),
          "boundaryWarnings":diag.get("boundaryWarnings"),
          "coverageWarnings":diag.get("coverageWarnings"),
          "exactDuplicates":diag.get("exactDuplicates"),
          "bodyHead":r.text[:1500] if r.status_code!=200 else None
        })
    except Exception as exc:
        out["error"]=f"{type(exc).__name__}: {exc}"
    print("V260_MERCK_ROUTE_REPRO "+json.dumps(out,ensure_ascii=False),flush=True)

if __name__=="__main__":
    asyncio.run(main())
