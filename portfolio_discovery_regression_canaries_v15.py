"""READ-ONLY regression bridge for the latest Portfolio Discovery comparator.

This module installs V1.5 first, then imports the frozen Pfizer and Vertex
regression fixtures. That forces the legacy canary suite to execute against the
current comparator rather than the historical V1.3 import state.

No Airtable, Portfolio, RPC, MRS, Queue, or automation writes are introduced.
"""

from typing import Any, Dict

import portfolio_discovery_extension_v15 as latest
import portfolio_discovery_extension_v11 as base
import portfolio_discovery_regression_canaries as frozen


CANARY_VERSION = "V1.1 PORTFOLIO DISCOVERY REGRESSION CANARIES - CURRENT COMPARATOR"

LATEST_REGRESSION_CHECKS = {
    "frozen_suite_passes": bool(frozen.REGRESSION_RESULTS.get("ok")),
    "pfizer_runs_on_v15": frozen.PFIZER_REGRESSION.get("version") == latest.DISCOVERY_VERSION,
    "vertex_runs_on_v15": frozen.VERTEX_REGRESSION.get("version") == latest.DISCOVERY_VERSION,
    "pfizer_all_58_still_match": frozen.PFIZER_REGRESSION.get("checks", {}).get("all_58_matched") is True,
    "vertex_vx993_still_new_asset": frozen.VERTEX_REGRESSION.get("checks", {}).get("vx993_new_asset") is True,
    "vertex_vx407_still_new_asset": frozen.VERTEX_REGRESSION.get("checks", {}).get("vx407_new_asset") is True,
    "vertex_cushing_still_new_indication": frozen.VERTEX_REGRESSION.get("checks", {}).get("atumelnant_cushing_new_indication") is True,
    "vertex_cah_still_matched": frozen.VERTEX_REGRESSION.get("checks", {}).get("atumelnant_cah_matched") is True,
}

LATEST_REGRESSION_RESULTS: Dict[str, Any] = {
    "ok": all(LATEST_REGRESSION_CHECKS.values()),
    "canaryVersion": CANARY_VERSION,
    "comparatorVersion": latest.DISCOVERY_VERSION,
    "checks": LATEST_REGRESSION_CHECKS,
    "pfizer": frozen.PFIZER_REGRESSION,
    "vertex": frozen.VERTEX_REGRESSION,
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

if not LATEST_REGRESSION_RESULTS["ok"]:
    raise RuntimeError(
        f"Portfolio Discovery current-comparator regression failed: {LATEST_REGRESSION_RESULTS}"
    )


@base.app.get("/compare/portfolio-discovery/regression-health-current")
async def portfolio_discovery_regression_health_current() -> Dict[str, Any]:
    """Safe public regression summary for the currently installed comparator."""
    return LATEST_REGRESSION_RESULTS
