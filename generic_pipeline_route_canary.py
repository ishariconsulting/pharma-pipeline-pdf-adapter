"""Read-only GSK semantic XLSX pipeline adapter canary."""

import asyncio
import json
from collections import Counter

from generic_xlsx_pipeline_extension import extract_generic_xlsx

URL = "https://www.gsk.com/media/2qfbw2yv/2q2026-pipeline-list.xlsx"


async def main():
    try:
        result = await extract_generic_xlsx("GSK", URL, 35.0)
        phases = Counter(r.get("phase") for r in result.rows)
        sample = [
            {
                "asset": r.get("asset"),
                "developmentCode": r.get("developmentCode"),
                "molecule": r.get("molecule"),
                "brand": r.get("brand"),
                "therapeuticArea": r.get("therapeuticArea"),
                "indication": r.get("indication"),
                "phase": r.get("phase"),
            }
            for r in result.rows[:8]
        ]
        print("GSK_XLSX_CANARY " + json.dumps({
            "version": result.version,
            "readyForDiscovery": result.readyForDiscovery,
            "rowCount": result.rowCount,
            "phaseCounts": dict(phases),
            "validation": result.validation,
            "diagnostics": result.diagnostics,
            "sample": sample,
            "writes": 0,
        }, ensure_ascii=False), flush=True)
    except Exception as exc:
        print("GSK_XLSX_CANARY " + json.dumps({
            "readyForDiscovery": False,
            "error": f"{type(exc).__name__}: {exc}",
            "writes": 0,
        }), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
