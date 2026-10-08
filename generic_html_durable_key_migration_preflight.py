"""Read-only Step 2 generic-HTML durable-key migration preflight.

Runs the audit-branch generic pipeline extraction code directly against current
official Source Watch URLs and emits current V1.3 durable source keys.

Guardrails:
- no Airtable access;
- no Render configuration changes;
- no adapter secret required;
- no Portfolio/master writes;
- source failures are recorded and do not abort other sources;
- bounded concurrency and bounded source timeout.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List

from generic_pipeline_extension import _extract_generic_pipeline
from generic_pipeline_interpreter_canary import VERSION as INTERPRETER_VERSION


SOURCES: List[Dict[str, str]] = [
    {"sourceWatchRecordId":"rec30WpNaPR8P2T31","sourceWatchId":"MEN-SW-003","company":"Menarini Group","sourceName":"Stemline Oncology Pipeline","sourceUrl":"https://medical.menarinistemline.com/Pipeline/StemlinePipeline"},
    {"sourceWatchRecordId":"recCzXWgPfrLb3Auo","sourceWatchId":"NOV|Pipeline|Corporate","company":"Novartis","sourceName":"Novartis Pipeline","sourceUrl":"https://www.novartis.com/research-development/novartis-pipeline"},
    {"sourceWatchRecordId":"recOWqONHi2YBj7xb","sourceWatchId":"VIAT-SW-003","company":"Viatris","sourceName":"Viatris Science / Innovative Pipeline","sourceUrl":"https://www.viatris.com/en/science"},
    {"sourceWatchRecordId":"recTGKParWvCXJuJM","sourceWatchId":"JNJ-SW-002","company":"Johnson & Johnson","sourceName":"Johnson & Johnson 2026 Key Pipeline Events","sourceUrl":"https://www.investor.jnj.com/pipeline/2026-key-events/default.aspx"},
    {"sourceWatchRecordId":"recTTAiNfquZnXeC8","sourceWatchId":"AUTO|recpibSFRFE7U6SKO|PIPELINE","company":"Verve Therapeutics","sourceName":"Verve Therapeutics — Pipeline","sourceUrl":"https://www.vervetx.com/our-programs/our-pipeline"},
    {"sourceWatchRecordId":"recUaq5w669zo4Uyi","sourceWatchId":"JNJ-SW-001","company":"Johnson & Johnson","sourceName":"Johnson & Johnson Development Pipeline","sourceUrl":"https://www.investor.jnj.com/pipeline/development-pipeline/default.aspx"},
    {"sourceWatchRecordId":"recY1nk7LGfgzatTs","sourceWatchId":"AST|Pipeline|Corporate","company":"Astellas","sourceName":"Astellas Product Pipeline","sourceUrl":"https://www.astellas.com/en/science/research-and-development/pipeline.html"},
    {"sourceWatchRecordId":"rececZFW3IobI19Ei","sourceWatchId":"VRTX-SW-001","company":"Vertex Pharmaceuticals","sourceName":"Vertex R&D Pipeline","sourceUrl":"https://www.vrtx.com/our-science/pipeline/"},
    {"sourceWatchRecordId":"recfX1QV7yqFHgHcY","sourceWatchId":"MRK-SW-001","company":"Merck & Co. (MSD)","sourceName":"Merck Product Pipeline","sourceUrl":"https://www.merck.com/research/product-pipeline/"},
    {"sourceWatchRecordId":"reck5oLWNoHuyMvAB","sourceWatchId":"AUTO|recc3M66GspatASx7|PIPELINE","company":"Arrowhead Pharmaceuticals","sourceName":"Arrowhead Pharmaceuticals — Pipeline","sourceUrl":"https://arrowheadpharma.com/en-us/pipeline"},
    {"sourceWatchRecordId":"reckgEdv4ZdgkJGFU","sourceWatchId":"NOVO-SW-001","company":"Novo Nordisk","sourceName":"Novo Nordisk R&D Pipeline","sourceUrl":"https://www.novonordisk.com/science-and-technology/r-d-pipeline.html"},
    {"sourceWatchRecordId":"recp4DqsZgkBkQYMo","sourceWatchId":"REGN-SW-003","company":"Regeneron Pharmaceuticals","sourceName":"Regeneron Clinical Pipeline","sourceUrl":"https://www.regeneron.com/science/investigational-pipeline"},
    {"sourceWatchRecordId":"rectZvXGriiGR5gcE","sourceWatchId":"AUTO|recLZOSeQ7hizLHHr|PIPELINE","company":"Alnylam Pharmaceuticals","sourceName":"Alnylam Pharmaceuticals — Pipeline","sourceUrl":"https://www.alnylam.com/alnylam-rnai-pipeline"},
    {"sourceWatchRecordId":"recth9XJ345XekVPe","sourceWatchId":"REC-SW-002","company":"Recordati","sourceName":"Recordati Research & Development Pipeline","sourceUrl":"https://recordati.com/research-and-development/"},
    {"sourceWatchRecordId":"recuuwc5o0cS6LGRF","sourceWatchId":"BI|Pipeline|Human","company":"Boehringer Ingelheim","sourceName":"Boehringer Ingelheim Human Health Pipeline","sourceUrl":"https://www.boehringer-ingelheim.com/science-innovation/human-health-innovation/pipeline"},
    {"sourceWatchRecordId":"recvWeM9VsrFILTed","sourceWatchId":"DS-SW-001","company":"Daiichi Sankyo","sourceName":"Daiichi Sankyo Pipeline","sourceUrl":"https://www.daiichisankyo.com/alias/pc/rd/pipeline/"},
    {"sourceWatchRecordId":"recIxr1Li8RD0Jj31","sourceWatchId":"SOBI|Pipeline|Corporate","company":"Sobi","sourceName":"Sobi Pipeline","sourceUrl":"https://www.sobi.com/en/pipeline"},
    {"sourceWatchRecordId":"recpYNnKjnaIg0UkV","sourceWatchId":"BAYER-SW-001","company":"Bayer","sourceName":"Bayer Pharmaceuticals Development Pipeline","sourceUrl":"https://www.bayer.com/en/pharma/development-pipeline"},
    {"sourceWatchRecordId":"recEwVZeLX9Ao6mpf","sourceWatchId":"CHIESI-SW-001","company":"Chiesi","sourceName":"Chiesi Pipeline","sourceUrl":"https://www.chiesi.com/en/science-and-innovation/pipeline"},
    {"sourceWatchRecordId":"recKISbnSzaXbfenW","sourceWatchId":"ULTX-SW-001","company":"Ultragenyx Pharmaceutical","sourceName":"Ultragenyx Pipeline","sourceUrl":"https://www.ultragenyx.com/our-research/pipeline/"},
]

CONCURRENCY = 4
SOURCE_TIMEOUT_SECONDS = 20.0


def row_preview(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "sourceRecordId": row.get("sourceRecordId"),
        "asset": row.get("asset"),
        "molecule": row.get("molecule"),
        "developmentCode": row.get("developmentCode"),
        "brand": row.get("brand"),
        "indication": row.get("indication"),
        "phase": row.get("phase"),
        "study": row.get("study"),
        "trialIds": row.get("trialIds") or [],
        "parserMethod": row.get("parserMethod"),
        "sourceOrdinal": row.get("sourceOrdinal"),
    }


async def one_source(source: Dict[str, str], sem: asyncio.Semaphore) -> Dict[str, Any]:
    async with sem:
        base = dict(source)
        try:
            result = await _extract_generic_pipeline(
                company=source["company"],
                source_url=source["sourceUrl"],
                timeout_seconds=SOURCE_TIMEOUT_SECONDS,
            )
            rows = [row_preview(x) for x in result.rows]
            keys = [str(x.get("sourceRecordId") or "") for x in rows]
            duplicate_keys = sorted({k for k in keys if k and keys.count(k) > 1})
            base.update(
                {
                    "status": "PASS" if result.readyForDiscovery else "FAIL_CLOSED",
                    "readyForDiscovery": result.readyForDiscovery,
                    "rowCount": result.rowCount,
                    "routeVersion": result.routeVersion,
                    "interpreterVersion": result.interpreterVersion,
                    "retrievalMode": result.summary.get("retrievalMode"),
                    "routingReason": result.summary.get("routingReason"),
                    "selectedMethod": result.summary.get("selectedMethod"),
                    "duplicateCurrentDurableKeys": duplicate_keys,
                    "rows": rows,
                    "issues": result.issues,
                    "guardrails": result.guardrails,
                }
            )
        except Exception as exc:
            base.update(
                {
                    "status": "DEFERRED_OR_BLOCKED",
                    "readyForDiscovery": False,
                    "rowCount": 0,
                    "errorType": type(exc).__name__,
                    "error": str(exc)[:2000],
                    "rows": [],
                }
            )
        return base


async def main() -> Dict[str, Any]:
    sem = asyncio.Semaphore(CONCURRENCY)
    results = await asyncio.gather(*(one_source(x, sem) for x in SOURCES))
    pass_sources = [x for x in results if x["status"] == "PASS"]
    failed_sources = [x for x in results if x["status"] != "PASS"]
    duplicate_key_sources = [
        x for x in pass_sources if x.get("duplicateCurrentDurableKeys")
    ]

    return {
        "version": "STEP2_GENERIC_HTML_DURABLE_KEY_MIGRATION_PREFLIGHT_V1_READ_ONLY",
        "interpreterVersion": INTERPRETER_VERSION,
        "readOnly": True,
        "airtableWrites": 0,
        "renderConfigWrites": 0,
        "masterDataWrites": 0,
        "sourceCount": len(SOURCES),
        "passSourceCount": len(pass_sources),
        "failedOrDeferredSourceCount": len(failed_sources),
        "currentDurableRowCount": sum(int(x.get("rowCount") or 0) for x in pass_sources),
        "duplicateDurableKeySourceCount": len(duplicate_key_sources),
        "sources": results,
    }


if __name__ == "__main__":
    print(json.dumps(asyncio.run(main()), indent=2, ensure_ascii=False))
