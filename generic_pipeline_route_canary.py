"""Read-only canary for the reusable semantic XLSX pipeline adapter."""

import asyncio
import json

from generic_xlsx_pipeline_extension import extract_generic_xlsx

GSK_URL = "https://www.gsk.com/media/2qfbw2yv/2q2026-pipeline-list.xlsx"

async def main():
    try:
        result = await extract_generic_xlsx("GSK", GSK_URL, 35.0)
        payload = {
            "version": result.version,
            "company": result.company,
            "readyForDiscovery": result.readyForDiscovery,
            "rowCount": result.rowCount,
            "validation": result.validation,
            "diagnostics": result.diagnostics,
            "sampleRows": result.rows[:8],
            "writeMode": "READ_ONLY",
            "masterWrites": 0,
        }
    except Exception as exc:
        payload = {
            "company": "GSK",
            "readyForDiscovery": False,
            "error": f"{type(exc).__name__}: {exc}",
            "writeMode": "READ_ONLY",
            "masterWrites": 0,
        }
    print("GENERIC_XLSX_CANARY "+json.dumps(payload,ensure_ascii=False),flush=True)

if __name__ == "__main__":
    asyncio.run(main())
