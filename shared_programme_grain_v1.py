"""Shared, read-only verified programme-grain expansion contract (R1C).

The caller must supply separately verified, controlled indication identities.
Never split an unverified sentence, umbrella label, combination, or trial arm.
The returned sourceRecordId is stable across input ordering and display-name
changes, while sourceParentRecordId preserves the original source identity.

No Airtable, HTTP, Portfolio, or external side effects.
"""
from __future__ import annotations

from hashlib import sha256
import json
import re
import unicodedata
from typing import Any, Mapping, Sequence

CONTRACT_VERSION = "R1C_VERIFIED_PROGRAMME_GRAIN_V1"
QUALIFIERS = (
    "formulation", "routeOfAdministration", "treatmentSetting",
    "patientSegment", "biomarker", "regimen", "trialId", "armId",
)
_CONTROLLED_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{2,119}$")


class ProgrammeGrainHold(ValueError):
    """Fail-closed review required; never stage writes for this source row."""


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def _norm(value: Any) -> str:
    return " ".join(
        unicodedata.normalize("NFKC", _clean(value)).casefold().split()
    )


def _fingerprint(parent_id: str, controlled_id: str, context: Mapping[str, str]) -> str:
    canonical = json.dumps(
        {"parent": _clean(parent_id), "controlledId": _norm(controlled_id),
         "context": {key: _norm(context[key]) for key in QUALIFIERS}},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    )
    return sha256(canonical.encode("utf-8")).hexdigest()[:24]


def expand_verified_programmes(source_row: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Expand ONLY explicitly verified structured indications.

    A legacy row without verifiedIndications is returned unchanged; it is not
    evidence of a programme-grain contract. A source cannot silently rename
    a legacy parent Candidate: its derived child IDs require migration review.
    """
    row = dict(source_row)
    variants = row.get("verifiedIndications")
    if variants is None:
        return [row]
    parent_id = _clean(row.get("sourceRecordId"))
    asset = _clean(row.get("asset") or row.get("molecule") or row.get("brand"))
    if not parent_id or not asset:
        raise ProgrammeGrainHold("SOURCE_PARENT_OR_ASSET_IDENTITY_MISSING")
    if "::programme:" in parent_id:
        raise ProgrammeGrainHold("NESTED_PROGRAMME_EXPANSION_NOT_ALLOWED")
    if not isinstance(variants, list) or not variants:
        raise ProgrammeGrainHold("VERIFIED_INDICATIONS_MUST_BE_NONEMPTY_LIST")

    expanded: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in variants:
        if not isinstance(entry, dict) or entry.get("verified") is not True:
            raise ProgrammeGrainHold("INDICATION_VERIFICATION_MISSING")
        name = _clean(entry.get("indication"))
        controlled_id = _clean(entry.get("controlledIndicationId"))
        evidence_url = _clean(entry.get("evidenceUrl"))
        if not name or not _CONTROLLED_ID.fullmatch(controlled_id):
            raise ProgrammeGrainHold("CONTROLLED_INDICATION_ID_OR_NAME_MISSING")
        if not evidence_url.startswith("https://"):
            raise ProgrammeGrainHold("OFFICIAL_INDICATION_EVIDENCE_MISSING")
        context = {
            key: _clean(entry.get(key) if key in entry else row.get(key))
            for key in QUALIFIERS
        }
        token = _fingerprint(parent_id, controlled_id, context)
        if token in seen:
            raise ProgrammeGrainHold("DUPLICATE_VERIFIED_PROGRAMME_IDENTITY")
        seen.add(token)
        child = {key: value for key, value in row.items()
                 if key != "verifiedIndications"}
        child.update({
            "sourceRecordId": parent_id + "::programme:" + token,
            "sourceParentRecordId": parent_id,
            "indication": name,
            "controlledIndicationId": controlled_id,
            "controlledIndicationCandidate": name,
            "programmeEvidenceUrl": evidence_url,
            "programmeGrainContract": CONTRACT_VERSION,
            "programmeIdentityKey": token,
            **context,
        })
        expanded.append(child)
    return sorted(expanded, key=lambda child: child["sourceRecordId"])


def candidate_action_plan(
    rows: Sequence[Mapping[str, Any]],
    existing_source_ids: set[str],
) -> list[dict[str, str]]:
    """Preview idempotent Candidate-only actions; Portfolio writes are absent.

    Do not revive, overwrite, or supersede existing parent-source Candidates:
    existing legacy parents must be reconciled explicitly before child creates.
    """
    seen: set[str] = set()
    planned: list[dict[str, str]] = []
    for row in rows:
        source_id = _clean(row.get("sourceRecordId"))
        if not source_id or source_id in seen:
            raise ProgrammeGrainHold("MISSING_OR_DUPLICATE_SOURCE_IDENTITY")
        seen.add(source_id)
        parent_id = _clean(row.get("sourceParentRecordId"))
        if parent_id and parent_id != source_id and parent_id in existing_source_ids:
            raise ProgrammeGrainHold("LEGACY_PARENT_CANDIDATE_MIGRATION_REQUIRED")
        planned.append({
            "sourceRecordId": source_id,
            "sourceParentRecordId": parent_id,
            "action": (
                "REUSE_EXISTING_CANDIDATE"
                if source_id in existing_source_ids
                else "STAGE_NEW_CANDIDATE_FOR_REVIEW"
            ),
        })
    return planned
