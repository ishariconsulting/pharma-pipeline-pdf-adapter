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
from shared_candidate_inventory_v1 import validate_inventory
from shared_programme_grain_v1 import (
    ProgrammeGrainHold, expand_verified_programmes, candidate_action_plan,
)


class VerifiedSourceRow(base.DiscoverySourceRow):
    verifiedIndications: Optional[List[Dict[str, Any]]] = None


class VerifiedCompareRequest(base.DiscoveryCompareRequest):
    sourceRows: List[VerifiedSourceRow]
    existingCandidateSourceIds: List[str] = Field(default_factory=list)
    existingCandidateInventory: List[Dict[str, Any]] = Field(default_factory=list)
    existingCandidateInventoryComplete: bool = False
    existingCandidateExpectedCount: Optional[int] = None
    evidenceAttestations: List[Dict[str, Any]] = Field(default_factory=list)
    approvedEvidenceHosts: List[str] = Field(default_factory=list)


def _dict(model: Any) -> Dict[str, Any]:
    return model.model_dump(exclude_none=True) if hasattr(model, "model_dump") else model.dict(exclude_none=True)


def compare_verified(request: VerifiedCompareRequest) -> base.DiscoveryCompareResponse:
    existing_source_ids = validate_inventory(
        request.existingCandidateInventory,
        complete=request.existingCandidateInventoryComplete,
        expected_count=request.existingCandidateExpectedCount,
        allow_unkeyed=True,  # complete inventory; held new rows, keyed reuse permitted
    )
    # The older free-form source ID list cannot override the inspected inventory.
    if request.existingCandidateSourceIds and set(request.existingCandidateSourceIds) != existing_source_ids:
        raise ProgrammeGrainHold("LEGACY_SOURCE_ID_LIST_INVENTORY_MISMATCH")
    # Any historical unkeyed Candidate could alias a fresh source key. Do not
    # stage NEW Candidates until these are reconciled; do preserve exact reuse.
    unkeyed_legacy_count = sum(
        1 for record in request.existingCandidateInventory
        if not str(record.get("sourceRecordId") or "").strip()
    )
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
                            existing_parent_candidate_ids=set())  # planner holds parent collisions per row
        for child in expand_verified_programmes(qualified):
            source_id = child["sourceRecordId"]
            if source_id in provenance:
                raise ProgrammeGrainHold("DUPLICATE_COMPARATOR_SOURCE_IDENTITY")
            provenance[source_id] = child
            expanded.append(base.DiscoverySourceRow(**child))

    # Fail closed before any comparisons. In particular, a legacy parent
    # Candidate must never silently become multiple new child Candidates.
    plans = candidate_action_plan(
        list(provenance.values()), existing_source_ids,
        unresolved_legacy_count=unkeyed_legacy_count,
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


WORKER_PREVIEW_VERSION = "R1C_SHARED_WORKER_COMPATIBILITY_V1_READ_ONLY"


def preview_verified_worker(request: VerifiedCompareRequest) -> Dict[str, Any]:
    """Preflight one company/source-snapshot for a future shared Airtable caller.

    Unlike the published Worker, this contract does not presume a 1:1
    source-row to Candidate relationship. It preserves parent-level holds and
    always prevents Candidate, Portfolio, Queue and Source Watch writes.
    Evidence attestations are supplied by caller; this route is NOT an
    independent source verifier or a production-ready Airtable integration.
    """
    if not request.sourceRows:
        raise ProgrammeGrainHold("SOURCE_ROWS_REQUIRED")
    known_source_ids = validate_inventory(
        request.existingCandidateInventory,
        complete=request.existingCandidateInventoryComplete,
        expected_count=request.existingCandidateExpectedCount,
        allow_unkeyed=True,
    )
    if (request.existingCandidateSourceIds
            and set(request.existingCandidateSourceIds) != known_source_ids):
        raise ProgrammeGrainHold("LEGACY_SOURCE_ID_LIST_INVENTORY_MISMATCH")

    seen_parents: set[str] = set()
    for row in request.sourceRows:
        parent_id = str(row.sourceRecordId or "").strip()
        if not parent_id or parent_id in seen_parents:
            raise ProgrammeGrainHold("DUPLICATE_OR_MISSING_PARENT_SOURCE_ID")
        seen_parents.add(parent_id)

    parent_results: list[dict[str, Any]] = []
    seen_children: set[str] = set()
    for row in request.sourceRows:
        parent_id = str(row.sourceRecordId).strip()
        # The comparator's older one-to-one field is not used to gate here.
        # Evaluate each independently attested source parent, then reconstruct
        # a one-to-many, source-parent-keyed preview; none of it is writeable.
        single_request = request.model_copy(update={"sourceRows": [row]})
        try:
            response = compare_verified(single_request)
            if response.readOnly is not True:
                raise ProgrammeGrainHold("COMPARATOR_READ_ONLY_CONTRACT_REQUIRED")
            candidates = []
            for child in response.candidates:
                child_id = str(child.get("sourceRecordId") or "").strip()
                if not child_id or child_id in seen_children:
                    raise ProgrammeGrainHold("DUPLICATE_OR_MISSING_CHILD_SOURCE_ID")
                # Child must retain the immutable parent provenance. A row
                # that was not independently qualified is not a programme.
                if child.get("sourceParentRecordId") != parent_id:
                    raise ProgrammeGrainHold("CHILD_PARENT_PROVENANCE_REQUIRED")
                if not child.get("programmeIdentityKey"):
                    raise ProgrammeGrainHold("CHILD_PROGRAMME_IDENTITY_REQUIRED")
                action = str(child.get("candidateStagingAction") or "")
                if action not in {
                    "REUSE_EXISTING_CANDIDATE",
                    "STAGE_NEW_CANDIDATE_FOR_REVIEW",
                    "HOLD_LEGACY_PARENT_CANDIDATE_MIGRATION",
                    "HOLD_UNKEYED_LEGACY_CANDIDATE_REVIEW",
                }:
                    raise ProgrammeGrainHold("UNSUPPORTED_CANDIDATE_ACTION")
                candidates.append({
                    "sourceParentRecordId": parent_id,
                    "sourceRecordId": child_id,
                    "programmeIdentityKey": child["programmeIdentityKey"],
                    "controlledIndicationId": child["controlledIndicationId"],
                    "candidateStagingActionPreview": action,
                    "sourceFamily": child.get("sourceFamily"),
                    "discoveryCandidateId": child.get("discoveryCandidateId"),
                    "comparatorSuggestedPortfolioIds": list(
                        child.get("existingPortfolioRecordIds") or []
                    ),
                    "portfolioLinkAction": "HOLD_FOR_INDEPENDENT_VERIFICATION",
                    "canWrite": False,
                })
            # Commit IDs only after complete parent validation, so malformed
            # parent output cannot poison another independent parent preview.
            seen_children.update(c["sourceRecordId"] for c in candidates)
            parent_results.append({
                "sourceParentRecordId": parent_id,
                "result": "QUALIFIED_FOR_READ_ONLY_REVIEW",
                "holdReason": None,
                "candidateCount": len(candidates),
                "candidates": candidates,
            })
        except ProgrammeGrainHold as error:
            parent_results.append({
                "sourceParentRecordId": parent_id,
                "result": "HOLD",
                "holdReason": str(error),
                "candidateCount": 0,
                "candidates": [],
            })

    return {
        "version": WORKER_PREVIEW_VERSION,
        "readOnly": True,
        "productionWorkerIntegrated": False,
        "sourceRowCount": len(request.sourceRows),
        "verifiedProgrammePreviewCount": sum(
            p["candidateCount"] for p in parent_results
        ),
        "parentHoldCount": sum(p["result"] == "HOLD" for p in parent_results),
        "existingCandidateInventoryCount": len(request.existingCandidateInventory),
        "existingCandidateInventoryComplete": True,
        "portfolioMasterWrites": 0,
        "candidateWrites": 0,
        "queueWrites": 0,
        "sourceWatchWrites": 0,
        "parentResults": parent_results,
    }


@app.post("/compare/portfolio-discovery/verified-programmes/worker-preview")
async def preview_verified_worker_route(
    request: VerifiedCompareRequest,
    x_adapter_key: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    _auth(x_adapter_key)
    return preview_verified_worker(request)


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
