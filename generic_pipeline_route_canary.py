"""Read-only reproduction of Airtable V2.60 routing for Lilly.

Uses the actual FastAPI app in-process and the same request shape produced by
Pipeline Source Watch - Recurring. No Airtable or master-data writes.
"""
import asyncio
import json
import os
import httpx

import service_entrypoint

COMPANY = "Eli Lilly and Company"
SOURCE_URL = "https://investor.lilly.com/static-files/ab69001c-650b-44f6-b629-309ee33f2335"
PATH = "/extract/lilly/pipeline"

async def main():
    key = os.environ.get("ADAPTER_API_KEY", "")
    out = {
        "profile": "PIPELINE_LILLY_INVESTOR_PDF_V1",
        "path": PATH,
        "requestShape": "V2.60_COMMON_CONTRACT",
        "masterWrites": 0,
    }
    transport = httpx.ASGITransport(app=service_entrypoint.app)
    try:
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://adapter.local",
            timeout=70.0,
        ) as client:
            r = await client.get(
                PATH,
                params={"company": COMPANY, "source_url": SOURCE_URL},
                headers={"Accept": "application/json", "X-Adapter-Key": key},
            )
        out["status"] = r.status_code
        try:
            p = r.json()
        except Exception:
            p = {}
        rows = p.get("rows") or []
        issues = p.get("issues") or []
        diagnostics = p.get("diagnostics") or {}
        summary = p.get("summary") or {}
        out.update({
            "version": p.get("version"),
            "readyForDiscovery": p.get("readyForDiscovery"),
            "rowCount": len(rows),
            "coreCompleteRows": sum(
                1 for x in rows
                if str(x.get("asset") or "").strip()
                and str(x.get("indication") or "").strip()
                and str(x.get("phase") or "").strip()
            ),
            "structuralValidationPass": summary.get("structuralValidationPass"),
            "issues": issues,
            "rowFailures": diagnostics.get("rowFailures"),
            "phaseUnresolved": diagnostics.get("phaseUnresolved"),
            "boundaryWarnings": diagnostics.get("boundaryWarnings"),
            "coverageWarnings": diagnostics.get("coverageWarnings"),
            "exactDuplicates": diagnostics.get("exactDuplicates"),
            "bodyHead": r.text[:1200] if r.status_code != 200 else None,
        })
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    print("V260_LILLY_ROUTE_REPRO " + json.dumps(out, ensure_ascii=False), flush=True)

if __name__ == "__main__":
    asyncio.run(main())
