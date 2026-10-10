"""Read-only R1C Candidate inventory admission; company/source-family agnostic.

An absent source ID in a partial/legacy inventory must never be interpreted as
proof that an existing Candidate does not exist. No Airtable or HTTP calls.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence
from shared_programme_grain_v1 import ProgrammeGrainHold


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def validate_inventory(
    records: Sequence[Mapping[str, Any]], *, complete: bool,
    expected_count: int | None,
    allow_unkeyed: bool = False,
) -> set[str]:
    """Validate a scoped, *fully paginated* Candidate snapshot and collect raw IDs.

    Caller must scope records to exactly the Source Watch being compared and
    independently check pagination/record count. SourceRecordId is the raw
    adapter parent or R1C child key, NOT the human-readable Candidate ID.
    """
    if not complete or expected_count is None or expected_count < 0:
        raise ProgrammeGrainHold("COMPLETE_CANDIDATE_INVENTORY_REQUIRED")
    if len(records) != expected_count:
        raise ProgrammeGrainHold("CANDIDATE_INVENTORY_COUNT_MISMATCH")
    source_ids = set()
    unresolved = 0
    candidate_ids = set()
    for record in records:
        if not isinstance(record, Mapping):
            raise ProgrammeGrainHold("INVALID_CANDIDATE_INVENTORY_ROW")
        candidate_id = _clean(record.get("discoveryCandidateId"))
        if not candidate_id or candidate_id in candidate_ids:
            raise ProgrammeGrainHold("CANDIDATE_IDENTITY_MISSING_OR_DUPLICATE")
        candidate_ids.add(candidate_id)
        source_id = _clean(record.get("sourceRecordId"))
        if source_id:
            source_ids.add(source_id)
        else:
            unresolved += 1
    # Distinct existing Candidates may share a legacy source parent; retain
    # every existing row without assuming that the parent is one programme.
    # Default callers retain the strict fail-closed behaviour. Read-only R1C
    # preview may admit a COMPLETE inventory with unkeyed historical Candidates,
    # but its action planner MUST hold all new Candidate actions in that case.
    # Exact keyed Candidate reuse can then be assessed independently.
    if unresolved and not allow_unkeyed:
        raise ProgrammeGrainHold(
            f"LEGACY_CANDIDATE_SOURCE_KEYS_UNRESOLVED:{unresolved}"
        )
    return source_ids
