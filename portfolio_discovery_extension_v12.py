"""V1.2 additive patch for the read-only Portfolio Discovery comparator.

This module deliberately imports V1.1, lets it register the existing read-only
routes, then patches only deterministic phase normalization / commercial-scope
logic. It does not add any master-data write path.
"""

import re
from typing import Any, Dict, List, Optional, Tuple

import portfolio_discovery_extension_v11 as base


DISCOVERY_VERSION = "V1.2.1 PORTFOLIO DISCOVERY READ ONLY - HYBRID PHASE AWARE"

# Capture the V1.1 implementations BEFORE patching module globals. Any V1.2
# fallback must call these stable references, never base._phase_canonical after
# it has been replaced by V1.2 (which would recurse).
_original_phase_canonical = base._phase_canonical
_original_compare = base.compare_discovery


def _phase_canonical_v12(value: Any) -> str:
    raw = base._clean(value).lower()
    if not raw:
        return ""

    normalized = base._norm(raw)
    if normalized in {"registration", "filed", "filed registration"} or (
        "filed" in normalized and "registration" in normalized
    ):
        return "registration"

    token = r"(?:iii|ii|i|[123])(?:[abc])?"
    match = re.search(
        rf"\bphase\s*({token}(?:\s*(?:/|\\|\+|&|\-|to)\s*{token})*)",
        raw,
        flags=re.I,
    )
    if not match:
        match = re.search(r"\bphase\s+((?:(?:iii|ii|i|[123])(?:[abc])?\s*){1,3})", raw, flags=re.I)

    if match:
        tokens = re.findall(token, match.group(1), flags=re.I)
        mapping = {"i": "1", "ii": "2", "iii": "3"}
        stages: List[str] = []
        for item in tokens:
            core_match = re.match(r"(iii|ii|i|[123])", item.lower())
            if not core_match:
                continue
            core = core_match.group(1)
            stage = mapping.get(core, core)
            if stage not in stages:
                stages.append(stage)
        if stages:
            stages = sorted(stages, key=int)
            return "phase " + " ".join(stages)

    return _original_phase_canonical(value)


def _commercial_decision_v12(
    row: base.DiscoverySourceRow,
) -> Tuple[str, List[str], Optional[str]]:
    status = base._norm(row.programStatus)
    if any(term in status for term in base.EXCLUDED_STATUS_TERMS):
        return "Exclude", ["Inactive / Discontinued"], "Source status is inactive/discontinued/terminated/withdrawn."

    if row.genericCommodity:
        return "Exclude", ["Generic / Commodity"], "Source identifies a generic/commodity product outside commercial scope."

    phase = _phase_canonical_v12(row.phase)
    if row.marketedStrategicRx:
        return "Include", ["Strategic Marketed Rx Brand"], None
    if row.importantLabelExpansion:
        return "Include", ["Important Label Expansion"], None
    if phase == "registration":
        return "Include", ["Filed / Registration"], None

    stage_numbers = set(re.findall(r"\b[123]\b", phase)) if phase.startswith("phase ") else set()
    if "2" in stage_numbers or "3" in stage_numbers:
        basis = "Active Phase 2+"
        if len(stage_numbers) > 1:
            basis = "Integrated Phase 2+"
        return "Include", [basis], None

    if stage_numbers == {"1"}:
        if row.strategicPhase1:
            return "Include", ["Strategic Phase 1"], None
        return "Exclude", ["Legacy / Low Commercial Value"], "Phase 1 is excluded unless explicitly strategic under COMMERCIAL_PORTFOLIO_V1."

    return "Review", ["Insufficient Evidence"], "No deterministic commercial inclusion signal or eligible development phase."


def _compare_discovery_v12(request: base.DiscoveryCompareRequest) -> base.DiscoveryCompareResponse:
    result = _original_compare(request)
    result.version = DISCOVERY_VERSION
    result.guardrails["hybridPhaseAware"] = True
    result.guardrails["integratedPhase2PlusIncluded"] = True
    return result


base.DISCOVERY_VERSION = DISCOVERY_VERSION
base._phase_canonical = _phase_canonical_v12
base._commercial_decision = _commercial_decision_v12
base.compare_discovery = _compare_discovery_v12


def _v12_self_test() -> Dict[str, Any]:
    cases = [
        ("Phase I/II", "phase 1 2", "Include", "Integrated Phase 2+"),
        ("Phase 1/2", "phase 1 2", "Include", "Integrated Phase 2+"),
        ("Phase 1/2/3", "phase 1 2 3", "Include", "Integrated Phase 2+"),
        ("Phase 2b/3", "phase 2 3", "Include", "Integrated Phase 2+"),
        ("Phase II/III", "phase 2 3", "Include", "Integrated Phase 2+"),
        ("Phase 2", "phase 2", "Include", "Active Phase 2+"),
        ("Phase 1", "phase 1", "Exclude", "Legacy / Low Commercial Value"),
    ]
    checks: Dict[str, bool] = {}
    for idx, (source_phase, expected_phase, expected_decision, expected_basis) in enumerate(cases, start=1):
        row = base.DiscoverySourceRow(
            company="Vertex Pharmaceuticals",
            sourceFamily="Company Pipeline",
            sourceRecordId=f"phase-{idx}",
            asset=f"TEST-{idx}",
            indication="Test indication",
            phase=source_phase,
        )
        decision, basis, _ = _commercial_decision_v12(row)
        checks[f"phase_case_{idx}"] = (
            _phase_canonical_v12(source_phase) == expected_phase
            and decision == expected_decision
            and expected_basis in basis
        )

    # Regression for a non-phase Portfolio value: this was the recursion edge
    # exposed by AstraZeneca marketed records during the live canary.
    checks["approved_fallback_no_recursion"] = _phase_canonical_v12("Approved") == _original_phase_canonical("Approved")

    regression = base._self_test()
    checks["v11_regression"] = bool(regression.get("ok"))
    return {"ok": all(checks.values()), "checks": checks, "v11Regression": regression}


V12_SELF_TEST_RESULTS = _v12_self_test()
if not V12_SELF_TEST_RESULTS["ok"]:
    raise RuntimeError(f"Portfolio discovery V1.2 self-test failed: {V12_SELF_TEST_RESULTS}")

base.SELF_TEST_RESULTS = {
    "ok": True,
    "checks": {
        **V12_SELF_TEST_RESULTS["v11Regression"].get("checks", {}),
        **V12_SELF_TEST_RESULTS["checks"],
    },
    "summary": V12_SELF_TEST_RESULTS["v11Regression"].get("summary", {}),
    "hybridPhaseSelfTest": True,
}

# Register company-source adapters only after comparator patching is complete.
# These routes are read-only and do not alter Airtable or existing automations.
import astrazeneca_pipeline_adapter  # noqa: E402,F401
