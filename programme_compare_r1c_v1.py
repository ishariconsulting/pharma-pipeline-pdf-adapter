"""Additive, read-only R1C comparator route for verified programme-grain rows.

It leaves /compare/portfolio-discovery and all live Airtable/Render behaviour
unchanged. A future explicitly approved Worker version can call this route.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import Header
from pydantic import Field

from main import _auth, app
import portfolio_discovery_extension_v16  # noqa: F401 - installs existing V1.6 matching
import portfolio_discovery_extension_v11 as base
from shared_programme_evidence_qualification_v1 import qualify
from shared_programme_grain_v1 import (
    ProgrammeGrainHold, expand_verified_programmes, candidate_action_plan,
)


class VerifiedSourceRow(base.DiscoverySourceRow):
    verifiedIndications: Optional[List[Dict[str, Any]]] = None


class VerifiedCompareRequest(base.DiscoveryCompareRequest):
    sourceRows: List[VerifiedSourceRow]
    existingCandidateSourceIds: List[str] = Field(default_factory=list)
    evidenceAttestations: List[Dict[str, Any]] = Field(default_factory=list)
    approvedEvidenceHosts: List[str] = Field(default_factory=list)


def _dict(model: Any) -> Dict[str, Any]:
    return model.model_dump(exclude_none=True) if hasattr(model, "model_dump") else model.dict(exclude_none=True)


def compare_verified(request: VerifiedCompareRequest) -> base.DiscoveryCompareResponse:
    expanded = []
    provenance = {}
    for source in request.sourceRows:
        source_data = _dict(source)
        parent = source_data["sourceRecordId"]
        evidence = [a for a in request.evidenceAttestations if a.get("sourceRecordId") == parent]
        if not evidence:
            raise ProgrammeGrainHold("VERIFIED_PROGRAMME_EVIDENCE_REQUIRED")
        # A supplied verifiedIndications flag is never sufficient: attestations
        # must pass the independent read-only qualification contract.
        qualified = qualify(source_data, evidence,
                            approved_hosts=set(request.approvedEvidenceHosts),
                            existing_parent_candidate_ids=set(request.existingCandidateSourceIds))
        for child in expand_verified_programmes(qualified):
            source_id = child["sourceRecordId"]
            if source_id in provenance:
                raise ProgrammeGrainHold("DUPLICATE_COMPARATOR_SOURCE_IDENTITY")
            provenance[source_id] = child
            expanded.append(base.DiscoverySourceRow(**child))

    # Fail closed before any comparisons. In particular, a legacy parent
    # Candidate must never silently become multiple new child Candidates.
    plans = candidate_action_plan(
        list(provenance.values()), set(request.existingCandidateSourceIds)
    )
    child_requests = base.DiscoveryCompareRequest(
        company=request.company, companyAliases=request.companyAliases,
        batchRunId=request.batchRunId, sourceRows=expanded,
        portfolioRows=request.portfolioRows,
    )
    result = base.compare_discovery(child_requests)
    lookup = {p["sourceRecordId"]: p for p in plans}
    for candidate in result.candidates:
        source_id = candidate["sourceRecordId"]
        p = provenance[source_id]
        if "programmeIdentityKey" not in p:
            continue  # legacy comparator behaviour retained verbatim
        # Use immutable parent/grain identity, not mutable labels or source order.
        candidate["discoveryCandidateId"] = "|".join((
            base._norm(request.company).replace(" ", "_"),
            base._norm(candidate["sourceFamily"]).replace(" ", "_"),
            base._norm(source_id).replace(" ", "_"),
        ))
        candidate["sourceParentRecordId"] = p["sourceParentRecordId"]
        candidate["programmeIdentityKey"] = p["programmeIdentityKey"]
        candidate["controlledIndicationId"] = p["controlledIndicationId"]
        candidate["programmeEvidenceUrl"] = p["programmeEvidenceUrl"]
        candidate["candidateStagingAction"] = lookup[source_id]["action"]
        candidate["portfolioMasterWritesAllowed"] = False
    return result


@app.post(
    "/compare/portfolio-discovery/verified-programmes",
    response_model=base.DiscoveryCompareResponse,
)
async def compare_verified_route(
    request: VerifiedCompareRequest,
    x_adapter_key: Optional[str] = Header(default=None),
) -> base.DiscoveryCompareResponse:
    _auth(x_adapter_key)
    return compare_verified(request)
