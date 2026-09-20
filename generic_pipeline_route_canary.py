"""Read-only V1.2 generic pipeline route canary.

Runs the outstanding Source Watch pipeline URLs through the same generic
extraction function that production would call. Prints compact structural
results only. No Airtable or master-data writes.
"""

import asyncio
import json

from generic_pipeline_extension import _extract_generic_pipeline


SOURCES = [
    ("AbbVie", "https://www.abbvie.com/science/pipeline.html"),
    ("Gilead Sciences", "https://www.gilead.com/science/pipeline"),
    ("Amgen", "https://www.amgen.com/science/clinical-trials"),
    ("Ionis Pharmaceuticals", "https://ionis.com/science-and-innovation/pipeline"),
    ("Johnson & Johnson Key Events", "https://www.investor.jnj.com/pipeline/2026-key-events/default.aspx"),
    ("Verve Therapeutics", "https://www.vervetx.com/our-programs/our-pipeline"),
    ("GSK", "https://www.gsk.com/en-gb/innovation/pipeline/"),
    ("Biogen", "https://www.biogen.com/science-and-innovation/pipeline.html"),
    ("Johnson & Johnson Innovative Medicine", "https://www.investor.jnj.com/pipeline/Innovative-Medicine-pipeline/default.aspx"),
    ("Merck KGaA", "https://www.emdgroup.com/en/research/our-approach-to-research-and-development/healthcare.html"),
    ("Menarini Group", "https://www.menarini.com/en-us/innovation-research/our-pipeline-and-products.html"),
    ("Vertex Pharmaceuticals", "https://www.vrtx.com/our-science/pipeline/"),
    ("Takeda", "https://www.takeda.com/science/pipeline/"),
    ("argenx SE", "https://argenx.com/pipeline"),
    ("Bayer", "https://www.bayer.com/en/pharma/development-pipeline"),
    ("Roche", "https://www.roche.com/solutions/pipeline"),
    ("Boehringer Ingelheim", "https://www.boehringer-ingelheim.com/science-innovation/human-health-innovation/pipeline"),
    ("BioNTech SE", "https://www.biontech.com/int/en/home/pipeline-and-products/pipeline.html"),
    ("Wave Life Sciences", "https://wavelifesciences.com/pipeline/research-and-development/"),
    ("Sobi", "https://www.sobi.com/en/pipeline"),
]


async def one(company: str, url: str, sem: asyncio.Semaphore):
    async with sem:
        try:
            result = await _extract_generic_pipeline(
                company=company,
                source_url=url,
                timeout_seconds=22.0,
            )
            payload = {
                "company": company,
                "readyForDiscovery": result.readyForDiscovery,
                "rowCount": result.rowCount,
                "retrievalMode": result.summary.get("retrievalMode"),
                "routingReason": result.summary.get("routingReason"),
                "selectedMethod": result.summary.get("selectedMethod"),
                "portfolioDependentValidation": result.summary.get("portfolioDependentValidation"),
                "issues": [x.get("issue") for x in result.issues],
                "sample": [
                    {
                        "asset": r.get("asset"),
                        "indication": r.get("indication"),
                        "phase": r.get("phase"),
                    }
                    for r in result.rows[:2]
                ],
            }
        except Exception as exc:
            payload = {
                "company": company,
                "readyForDiscovery": False,
                "rowCount": 0,
                "retrievalMode": None,
                "routingReason": "EXCEPTION",
                "selectedMethod": None,
                "portfolioDependentValidation": False,
                "issues": [f"{type(exc).__name__}: {exc}"],
                "sample": [],
            }

        print("GENERIC_PIPELINE_CANARY", json.dumps(payload, ensure_ascii=False), flush=True)
        return payload


async def main():
    sem = asyncio.Semaphore(4)
    results = await asyncio.gather(*(one(company, url, sem) for company, url in SOURCES))
    summary = {
        "tested": len(results),
        "pass": sum(1 for r in results if r["readyForDiscovery"]),
        "fail": sum(1 for r in results if not r["readyForDiscovery"]),
        "browser": sum(1 for r in results if r.get("retrievalMode") == "BROWSER_REQUIRED"),
        "portfolioDependentValidation": any(r.get("portfolioDependentValidation") for r in results),
    }
    print("GENERIC_PIPELINE_CANARY_SUMMARY", json.dumps(summary), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
