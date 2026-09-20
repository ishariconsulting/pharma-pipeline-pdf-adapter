"""Read-only GSK XLSX baseline export canary."""

import asyncio
import json
from generic_xlsx_pipeline_extension import extract_generic_xlsx

URL="https://www.gsk.com/media/2qfbw2yv/2q2026-pipeline-list.xlsx"

async def main():
    result=await extract_generic_xlsx("GSK",URL,35.0)
    compact=[
        {
            "asset":r.get("asset",""),
            "molecule":r.get("molecule",""),
            "developmentCode":r.get("developmentCode",""),
            "brand":r.get("brand",""),
            "indication":r.get("indication",""),
            "phase":r.get("phase",""),
        }
        for r in result.rows
    ]
    print("GSK_XLSX_BASELINE_ROWS "+json.dumps({
        "readyForDiscovery":result.readyForDiscovery,
        "rowCount":result.rowCount,
        "rows":compact
    },ensure_ascii=False),flush=True)

if __name__=="__main__":
    asyncio.run(main())
