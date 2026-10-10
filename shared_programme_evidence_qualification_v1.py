"""R1C read-only evidence admission. No fetching, persistence or writes.

Caller must provide independently reviewed evidence attestations. This module
does NOT itself verify websites, trial registry details or clinical truth.
"""
from __future__ import annotations

from urllib.parse import urlparse
from typing import Any, Mapping, Sequence
from shared_programme_grain_v1 import ProgrammeGrainHold

def qualify(source: Mapping[str, Any], attestations: Sequence[Mapping[str, Any]], *,
            approved_hosts: set[str], existing_parent_candidate_ids: set[str] | None = None) -> dict[str, Any]:
    """Return a source copy with verifiedIndications only when all gates pass."""
    parent = str(source.get("sourceRecordId") or "").strip()
    if not parent or not str(source.get("asset") or "").strip():
        raise ProgrammeGrainHold("SOURCE_IDENTITY_MISSING")
    if parent in (existing_parent_candidate_ids or set()):
        raise ProgrammeGrainHold("LEGACY_PARENT_CANDIDATE_MIGRATION_REQUIRED")
    if not attestations:
        raise ProgrammeGrainHold("NO_INDEPENDENT_EVIDENCE_ATTESTATIONS")
    children = []
    seen = set()
    for item in attestations:
        if item.get("sourceRecordId") != parent or item.get("reviewed") is not True:
            raise ProgrammeGrainHold("EVIDENCE_ATTESTATION_NOT_REVIEWED")
        controlled = str(item.get("controlledIndicationId") or "").strip()
        name = str(item.get("indication") or "").strip()
        url = str(item.get("evidenceUrl") or "").strip()
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if (not controlled or not name or not url or parsed.scheme != "https"
                or not host or host not in approved_hosts or parsed.username or parsed.password):
            raise ProgrammeGrainHold("CONTROLLED_INDICATION_OR_TRUSTED_EVIDENCE_MISSING")
        if item.get("scopeVerified") is not True or item.get("assetVerified") is not True:
            raise ProgrammeGrainHold("PROGRAMME_SCOPE_OR_ASSET_UNVERIFIED")
        context = {k: item[k] for k in (
            "formulation", "routeOfAdministration", "treatmentSetting", "patientSegment",
            "biomarker", "regimen", "trialId", "armId") if item.get(k)}
        identity = (controlled, tuple(sorted(context.items())))
        if identity in seen:
            raise ProgrammeGrainHold("DUPLICATE_VERIFIED_PROGRAMME_IDENTITY")
        seen.add(identity)
        children.append(dict(controlledIndicationId=controlled, indication=name,
                             verified=True, evidenceUrl=url, **context))
    return {**source, "verifiedIndications": children}
