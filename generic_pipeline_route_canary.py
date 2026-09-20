"""Read-only canary for the semantic PDF-grid pipeline adapter."""

import asyncio
import json

from generic_pdf_grid_pipeline_extension import extract_generic_pdf_grid

AMGEN_PDF = "https://www.amgenpipeline.com/-/media/Themes/Amgen/amgenpipeline-com/amgenpipeline-com/PDF/amgen-pipeline-chart.pdf"


async def main():
    try:
        result = await extract_generic_pdf_grid("Amgen", AMGEN_PDF, 35.0)
        payload = {
            "version": result.version,
            "routeVersion": result.routeVersion,
            "company": result.company,
            "readyForDiscovery": result.readyForDiscovery,
            "rowCount": result.rowCount,
            "summary": result.summary,
            "validation": result.validation,
            "diagnostics": result.diagnostics,
            "sampleRows": result.rows[:12],
            "writeMode": "READ_ONLY",
            "masterWrites": 0,
        }
    except Exception as exc:
        payload = {
            "company": "Amgen",
            "readyForDiscovery": False,
            "error": f"{type(exc).__name__}: {exc}",
            "writeMode": "READ_ONLY",
            "masterWrites": 0,
        }

    print("GENERIC_PDF_GRID_CANARY " + json.dumps(payload, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
