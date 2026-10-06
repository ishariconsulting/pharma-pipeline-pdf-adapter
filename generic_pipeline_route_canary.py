"""Read-only startup canary for generic HTML pipeline routing.

Canary-only service. No Airtable access and no master-data writes.
Validates that substantial direct HTML parser failures remain DIRECT/fail-closed,
while browser escalation is reserved for sparse HTML or transport failure.
"""

import asyncio
import json

from generic_pipeline_extension import _extract_generic_pipeline, _fetch_raw_public_html


TARGETS = [
    {
        "name": "Sobi",
        "url": "https://www.sobi.com/en/pipeline",
        "must_pass": True,
    },
    {
        "name": "Ipsen",
        "url": "https://www.ipsen.com/science/pipeline/",
        "must_pass": True,
    },
    {
        "name": "Jazz Pharmaceuticals",
        "url": "https://www.jazzpharma.com/science/pipeline",
        "must_pass": True,
    },
    {
        "name": "Chiesi",
        "url": "https://www.chiesi.com/en/science-and-innovation/pipeline",
        "must_pass": False,
    },
    {
        "name": "Ultragenyx Pharmaceutical",
        "url": "https://www.ultragenyx.com/our-research/pipeline/",
        "must_pass": False,
    },
]


async def check(target):
    name = target["name"]
    try:
        result = await _extract_generic_pipeline(
            company=name,
            source_url=target["url"],
            timeout_seconds=25.0,
        )
        diagnostics = dict(result.diagnostics or {})
        routing_reason = diagnostics.get("routingReason")
        retrieval_mode = diagnostics.get("retrievalMode")

        if routing_reason == "DIRECT_STRUCTURE_BROWSER_RETRY":
            raise RuntimeError(
                f"{name}: forbidden structural-failure browser retry returned"
            )

        if (
            routing_reason == "DIRECT_STRUCTURE_UNSUPPORTED"
            and retrieval_mode != "DIRECT"
        ):
            raise RuntimeError(
                f"{name}: DIRECT_STRUCTURE_UNSUPPORTED must remain DIRECT"
            )

        if (
            retrieval_mode == "BROWSER_REQUIRED"
            and routing_reason not in {
                "SPARSE_SERVER_HTML",
                "DIRECT_TRANSPORT_FAIL",
            }
        ):
            raise RuntimeError(
                f"{name}: unexpected browser escalation reason {routing_reason}"
            )

        if target["must_pass"] and not result.readyForDiscovery:
            raise RuntimeError(
                f"{name}: known-good generic source no longer passes: "
                + json.dumps(result.validation, ensure_ascii=False)
            )

        return {
            "company": name,
            "status": "RESPONSE",
            "routeVersion": result.routeVersion,
            "readyForDiscovery": result.readyForDiscovery,
            "rowCount": result.rowCount,
            "retrievalMode": retrieval_mode,
            "routingReason": routing_reason,
            "directFailure": diagnostics.get("directFailure"),
            "directVisibleTextLength": diagnostics.get("directVisibleTextLength"),
            "visibleLineCount": diagnostics.get("visibleLineCount"),
            "selectedMethod": diagnostics.get("selectedMethod"),
            "issueCount": len(result.issues or []),
            "rowKeys": [
                {
                    "asset": row.get("asset"),
                    "indication": row.get("indication"),
                    "phase": row.get("phase"),
                    "sourceFormulation": row.get("sourceFormulation"),
                    "sourceRegion": row.get("sourceRegion"),
                }
                for row in (result.rows or [])[:30]
            ],
            "masterWrites": 0,
        }
    except RuntimeError:
        raise
    except Exception as exc:
        if target["must_pass"]:
            raise
        direct_probe = None
        if name == "Ultragenyx Pharmaceutical":
            try:
                raw_html, final_url = await _fetch_raw_public_html(
                    target["url"],
                    timeout_seconds=25.0,
                )
                direct_probe = {
                    "status": "OK",
                    "htmlChars": len(raw_html),
                    "finalUrl": final_url,
                }
            except Exception as direct_exc:
                direct_probe = {
                    "status": "ERROR",
                    "errorType": type(direct_exc).__name__,
                    "error": str(direct_exc)[:300],
                }
        return {
            "company": name,
            "status": "SOURCE_OR_TRANSPORT_ERROR",
            "errorType": type(exc).__name__,
            "error": str(exc)[:500],
            "directProbe": direct_probe,
            "masterWrites": 0,
        }


async def main():
    results = []
    for target in TARGETS:
        results.append(await check(target))

    print(
        "GENERIC_ROUTE_GATE_CANARY "
        + json.dumps(
            {
                "version": "GENERIC_ROUTE_GATE_CANARY_2026_10_06",
                "results": results,
                "portfolioWrites": 0,
                "airtableWrites": 0,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )


if __name__ == "__main__":
    asyncio.run(main())
