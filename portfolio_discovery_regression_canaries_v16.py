"""READ-ONLY regression bridge for Portfolio Discovery V1.6.

Re-runs the frozen Pfizer and Vertex fixtures after the latest comparator is
installed. The gate validates classification behaviour and read-only
guardrails, while allowing the comparator version to advance explicitly to
V1.6.

No Airtable, Portfolio, RPC, MRS, Queue, or automation writes are introduced.
"""

from typing import Any, Dict

import portfolio_discovery_extension_v16 as latest
import portfolio_discovery_extension_v11 as base
import portfolio_discovery_regression_canaries as frozen


CANARY_VERSION = "V1.3 PORTFOLIO DISCOVERY REGRESSION CANARIES - V1.6"

CURRENT_PFIZER = frozen._run_pfizer()
CURRENT_VERTEX = frozen._run_vertex()

LATEST_REGRESSION_CHECKS = {
    "pfizer_runs_on_latest": CURRENT_PFIZER.get("version") == latest.DISCOVERY_VERSION,
    "vertex_runs_on_latest": CURRENT_VERTEX.get("version") == latest.DISCOVERY_VERSION,
    "pfizer_all_58_still_match": CURRENT_PFIZER.get("checks", {}).get("all_58_matched") is True,
    "pfizer_no_new_asset": CURRENT_PFIZER.get("checks", {}).get("no_new_asset") is True,
    "pfizer_no_new_indication": CURRENT_PFIZER.get("checks", {}).get("no_new_indication") is True,
    "pfizer_no_possible_duplicate": CURRENT_PFIZER.get("checks", {}).get("no_possible_duplicate") is True,
    "vertex_vx993_still_new_asset": CURRENT_VERTEX.get("checks", {}).get("vx993_new_asset") is True,
    "vertex_vx407_still_new_asset": CURRENT_VERTEX.get("checks", {}).get("vx407_new_asset") is True,
    "vertex_cushing_still_new_indication": CURRENT_VERTEX.get("checks", {}).get("atumelnant_cushing_new_indication") is True,
    "vertex_cah_still_matched": CURRENT_VERTEX.get("checks", {}).get("atumelnant_cah_matched") is True,
    "pfizer_read_only": CURRENT_PFIZER.get("checks", {}).get("read_only") is True,
    "vertex_read_only": CURRENT_VERTEX.get("checks", {}).get("read_only") is True,
}

LATEST_REGRESSION_RESULTS: Dict[str, Any] = {
    "ok": all(LATEST_REGRESSION_CHECKS.values()),
    "canaryVersion": CANARY_VERSION,
    "comparatorVersion": latest.DISCOVERY_VERSION,
    "checks": LATEST_REGRESSION_CHECKS,
    "pfizer": CURRENT_PFIZER,
    "vertex": CURRENT_VERTEX,
    "v16SelfTest": latest.V16_SELF_TEST_RESULTS,
    "guardrails": {
        "readOnly": True,
        "masterWrites": False,
        "portfolioMutation": False,
        "rpcMutation": False,
        "mrsMutation": False,
        "queueMutation": False,
        "existingAutomationMutation": False,
        "fuzzyMatching": False,
    },
}

if not LATEST_REGRESSION_RESULTS["ok"] or not latest.V16_SELF_TEST_RESULTS.get("ok"):
    raise RuntimeError(
        f"Portfolio Discovery V1.6 regression failed: {LATEST_REGRESSION_RESULTS}"
    )


@base.app.get("/compare/portfolio-discovery/regression-health-current")
async def portfolio_discovery_regression_health_current_v16() -> Dict[str, Any]:
    return LATEST_REGRESSION_RESULTS
