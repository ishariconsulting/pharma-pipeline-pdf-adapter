"""Read-only preflight for Sep 22 catch-up sources not observed in Sep 21 production logs.

Reproduces the V2.60 common-contract request shape in-process. No Airtable or
master-data writes.
"""
import asyncio
import json
import os
import httpx
import service_entrypoint

SOURCES = [
    ("AbbVie", "PIPELINE_ABBVIE_PDF_V1", "/extract/abbvie/pdf-pipeline", "https://investors.abbvie.com/static-files/de1828c0-47ed-42cb-8573-24fe42ceb748"),
    ("Amgen", "PIPELINE_AMGEN_JSON_V1", "/extract/amgen/json-pipeline", "https://www.amgenpipeline.com/pipeline/molecule/getjsondata"),
    ("Sobi", "PIPELINE_GENERIC_HTML_V1", "/extract/generic/pipeline", "https://www.sobi.com/en/pipeline"),
    ("Novo Nordisk", "PIPELINE_GENERIC_HTML_V1", "/extract/generic/pipeline", "https://www.novonordisk.com/science-and-technology/r-d-pipeline.html"),
    ("argenx SE", "PIPELINE_GENERIC_PDF_TABLE_V1", "/extract/generic/pdf-pipeline-table", "https://argenx.com/content/dam/argenx-corp/pipeline/Pipeline_August2026%201.pdf.coredownload.inline.pdf"),
    ("Alnylam Pharmaceuticals", "PIPELINE_GENERIC_HTML_V1", "/extract/generic/pipeline", "https://www.alnylam.com/alnylam-rnai-pipeline"),
    ("Recordati", "PIPELINE_GENERIC_HTML_V1", "/extract/generic/pipeline", "https://recordati.com/research-and-development/"),
    ("Dyne Therapeutics", "PIPELINE_GENERIC_HTML_V1", "/extract/generic/pipeline", "https://www.dyne-tx.com/pipeline/"),
]

def guardrail(p):
    rows = p.get("rows") or []
    summary = p.get("summary") or {}
    diag = p.get("diagnostics") or {}
    issues = p.get("issues") or []
    core = sum(
        1 for r in rows
        if str(r.get("asset") or "").strip()
        and str(r.get("indication") or "").strip()
        and str(r.get("phase") or "").strip()
    )
    ok = bool(
        p.get("readyForDiscovery") is True
        and summary.get("structuralValidationPass") is True
        and not issues
        and len(rows) >= 1
        and core == len(rows)
        and int(diag.get("rowFailures") or 0) == 0
        and int(diag.get("phaseUnresolved") or 0) == 0
        and int(diag.get("boundaryWarnings") or 0) == 0
        and int(diag.get("coverageWarnings") or 0) == 0
        and int(diag.get("exactDuplicates") or 0) == 0
    )
    return {
        "pass": ok,
        "rows": len(rows),
        "coreComplete": core,
        "readyForDiscovery": p.get("readyForDiscovery"),
        "structuralValidationPass": summary.get("structuralValidationPass"),
        "issues": issues[:5],
        "productionStatus": summary.get("productionStatus"),
        "rowFailures": diag.get("rowFailures"),
        "phaseUnresolved": diag.get("phaseUnresolved"),
        "boundaryWarnings": diag.get("boundaryWarnings"),
        "coverageWarnings": diag.get("coverageWarnings"),
        "exactDuplicates": diag.get("exactDuplicates"),
    }

async def one(client, key, company, profile, path, source_url):
    out={"company":company,"profile":profile,"path":path,"masterWrites":0}
    try:
        r=await client.get(
            path,
            params={"company":company,"source_url":source_url},
            headers={"Accept":"application/json","X-Adapter-Key":key},
        )
        out["status"]=r.status_code
        try:p=r.json()
        except Exception:p={}
        if r.status_code == 200:
            out["guardrail"]=guardrail(p)
            out["version"]=p.get("version")
        else:
            out["bodyHead"]=r.text[:800]
    except Exception as exc:
        out["error"]=f"{type(exc).__name__}: {exc}"
    return out

async def main():
    key=os.environ.get("ADAPTER_API_KEY","")
    transport=httpx.ASGITransport(app=service_entrypoint.app)
    results=[]
    async with httpx.AsyncClient(transport=transport,base_url="http://adapter.local",timeout=90.0) as client:
        for source in SOURCES:
            results.append(await one(client,key,*source))
    print("SEP22_DUE_SOURCE_PREFLIGHT "+json.dumps({
        "version":"V2.60_DUE_PREFLIGHT_2026-09-22",
        "tested":len(results),
        "passed":sum(1 for r in results if (r.get("guardrail") or {}).get("pass")),
        "results":results,
        "masterWrites":0,
    },ensure_ascii=False),flush=True)

if __name__=="__main__":
    asyncio.run(main())
