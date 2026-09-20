"""Read-only direct source-shape diagnostics for generic pipeline onboarding.

No Airtable writes. No browser fallback. Captures enough structural evidence
from the official source HTML to improve the reusable parser safely.
"""

import asyncio
import json
import re

from generic_pipeline_extension import _fetch_raw_public_html
from generic_pipeline_interpreter_canary import (
    PageShapeParser,
    interpret_pipeline_html,
    validate_source,
)


SOURCES = [
    ("Gilead Sciences", "https://www.gilead.com/science/pipeline"),
    ("Amgen", "https://www.amgen.com/science/clinical-trials"),
    ("Ionis Pharmaceuticals", "https://ionis.com/science-and-innovation/pipeline"),
    ("Johnson & Johnson Key Events", "https://www.investor.jnj.com/pipeline/2026-key-events/default.aspx"),
    ("GSK", "https://www.gsk.com/en-gb/innovation/pipeline/"),
    ("Biogen", "https://www.biogen.com/science-and-innovation/pipeline.html"),
    ("Johnson & Johnson Innovative Medicine", "https://www.investor.jnj.com/pipeline/Innovative-Medicine-pipeline/default.aspx"),
    ("Merck KGaA", "https://www.emdgroup.com/en/research/our-approach-to-research-and-development/healthcare.html"),
    ("Menarini Group", "https://www.menarini.com/en-us/innovation-research/our-pipeline-and-products.html"),
    ("Takeda", "https://www.takeda.com/science/pipeline/"),
    ("argenx SE", "https://argenx.com/pipeline"),
    ("Roche", "https://www.roche.com/solutions/pipeline"),
    ("BioNTech SE", "https://www.biontech.com/int/en/home/pipeline-and-products/pipeline.html"),
    ("Wave Life Sciences", "https://wavelifesciences.com/pipeline/research-and-development/"),
    ("Boehringer Ingelheim", "https://www.boehringer-ingelheim.com/science-innovation/human-health-innovation/pipeline"),
]

SIGNAL_RE = re.compile(
    r"phase\s*[1-4]|phase\s*i{1,3}|preclinical|registration|regulatory|indication|pipeline|program|programme|candidate",
    re.I,
)


def compact_line(line: str) -> str:
    return " ".join(str(line).split())[:300]


async def one(company: str, url: str, sem: asyncio.Semaphore):
    async with sem:
        try:
            html, final_url = await _fetch_raw_public_html(url, timeout_seconds=25.0)
            parser = PageShapeParser()
            parser.feed(html)
            rows, diagnostics = await asyncio.to_thread(
                interpret_pipeline_html,
                company,
                final_url,
                html,
            )
            validation = validate_source(company, rows, diagnostics)

            signal_lines = []
            for idx, line in enumerate(parser.visible_lines):
                if SIGNAL_RE.search(line):
                    signal_lines.append({"i": idx, "text": compact_line(line)})
                    if len(signal_lines) >= 18:
                        break

            table_samples = []
            for ti, table in enumerate(parser.tables[:5]):
                sample_rows = []
                for raw_row in table[:5]:
                    cells = [compact_line(c) for c in raw_row if compact_line(c)]
                    if cells:
                        sample_rows.append(cells[:10])
                if sample_rows:
                    table_samples.append({"table": ti, "rows": sample_rows})

            payload = {
                "company": company,
                "finalUrl": final_url,
                "htmlChars": len(html),
                "visibleLineCount": len(parser.visible_lines),
                "tableCount": len(parser.tables),
                "semanticTableRows": diagnostics.get("semanticTableRows"),
                "labelledFlowRows": diagnostics.get("labelledFlowRows"),
                "selectedRows": diagnostics.get("selectedRows"),
                "selectedMethod": diagnostics.get("selectedMethod"),
                "validationPass": validation.get("pass"),
                "issues": validation.get("issues"),
                "signalLines": signal_lines,
                "tableSamples": table_samples,
            }
        except Exception as exc:
            payload = {
                "company": company,
                "validationPass": False,
                "issues": [f"{type(exc).__name__}: {exc}"],
            }

        print("PIPELINE_SHAPE_DIAGNOSTIC", json.dumps(payload, ensure_ascii=False), flush=True)
        return payload


async def main():
    sem = asyncio.Semaphore(4)
    results = await asyncio.gather(*(one(company, url, sem) for company, url in SOURCES))
    print(
        "PIPELINE_SHAPE_SUMMARY",
        json.dumps(
            {
                "tested": len(results),
                "structuralPass": sum(1 for r in results if r.get("validationPass")),
                "failed": sum(1 for r in results if not r.get("validationPass")),
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    asyncio.run(main())
