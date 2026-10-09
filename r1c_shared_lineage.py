"""Draft R1C offline shared evidence-to-programme resolver (Framework v2.22).

Composes the existing V1.6 comparator. No network clients, write actions, route
registration, schema migrations, new company-specific identity rules or automation.
An exported assertion is evidence to inspect, never authority to promote a record.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime
import json
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, ValidationError

VERSION = "R1C_SHARED_RESOLVER_V1_READ_ONLY_DRAFT"
FAMILIES = ("PIPELINE", "TRIAL_REGISTRY", "REGULATORY", "SIGNAL")
SCOPE_FIELDS = ("components", "indication", "line", "population", "setting", "route", "dose")
GUARDRAILS = dict(readOnly=True, candidateMutation=False, portfolioMutation=False,
                  sourceWatchMutation=False, queueMutation=False, masterWrites=False,
                  automationMutation=False, fuzzyMatching=False,
                  queueEligible=False, portfolioWriteEligible=False,
                  systemProgrammeKeyMutation=False, pfk1Mutation=False)


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Provenance(Model):
    url: str = Field(min_length=1)
    sourceRecordId: str = Field(min_length=1)
    # Absent official publication dates are explicitly held, not invented.
    asOf: str = ""
    retrievedAt: str = Field(min_length=1)
    version: str = Field(min_length=1)
    authorityId: str = Field(min_length=1)
    # Identifies the originating independent authority, not a republisher.
    originalText: str = Field(min_length=1)


class Scope(Model):
    # Explicit evidence-backed canonical values; no inferred aliases or conversion
    # from number of prior treatments to treatment line. Null means not assessed.
    components: list[str] = Field(min_length=1)
    indication: str | None
    line: str | None
    population: str | None
    setting: str | None
    route: str | None
    dose: str | None
    # Dimensions proved irrelevant use the explicit value "NOT_APPLICABLE".
    proofReferences: dict[str, str]
    companyRole: Literal["owner", "partner", "co-developer", "competitor", "unknown"]
    roleProof: str


class Source(Model):
    stableKey: str = Field(min_length=1)
    sourceWatchRecordId: str = Field(min_length=1)
    company: str = Field(min_length=1)
    adapterVersion: str = Field(min_length=1)
    parserVersion: str = Field(min_length=1)
    granularity: Literal["programme", "multi_indication", "asset_umbrella", "unknown"]
    provenance: Provenance
    comparison: dict
    scope: Scope
    # R1A disposition is distinct from discovery classification/review status.
    baselineDisposition: Literal["MATCHED", "HELD", "NEW", "EXCLUDED", "UNVERIFIED"]
    baselineReason: str
    # Only an UNVERIFIED historical decision may have no baseline proof.
    baselineProof: str = ""
    assessedFamilies: list[Literal["PIPELINE", "TRIAL_REGISTRY", "REGULATORY", "SIGNAL"]]
    relationIds: list[str]
    trialReferences: dict[str, str]


class Candidate(Model):
    recordId: str = Field(min_length=1)
    stableKey: str = Field(min_length=1)
    sourceWatchRecordId: str = Field(min_length=1)
    sourceRecordId: str = Field(min_length=1)
    company: str = Field(min_length=1)
    sourceVersion: str | None
    sourceGranularity: str | None
    active: bool
    reviewStatus: str = Field(min_length=1)
    programmeGate: str = Field(min_length=1)
    discoveryClassification: str = Field(min_length=1)
    holdReason: str
    portfolioIds: list[str]
    queueEligible: bool
    portfolioWriteEligible: bool


class Portfolio(Model):
    recordId: str = Field(min_length=1)
    company: str = Field(min_length=1)
    comparison: dict
    scope: Scope
    candidateIds: list[str]
    landscapeIds: list[str]
    trialIds: list[str]
    evidenceFamilies: list[str]
    crossSourceStatus: str | None


class Trial(Model):
    recordId: str = Field(min_length=1)
    nct: str = Field(pattern=r"^NCT\d{8}$")
    studyName: str = Field(min_length=1)
    status: str = Field(min_length=1)
    provenance: Provenance
    portfolioIds: list[str]
    armIds: list[str]


class Arm(Model):
    recordId: str = Field(min_length=1)
    trialRecordId: str = Field(min_length=1)
    nct: str = Field(pattern=r"^NCT\d{8}$")
    armRef: str = Field(min_length=1)
    interventionRole: Literal["experimental", "comparator", "placebo", "background", "supportive"]
    comparison: dict
    scope: Scope
    provenance: Provenance


class Relation(Model):
    recordId: str = Field(min_length=1)
    stableKey: str = Field(min_length=1)
    portfolioId: str = Field(min_length=1)
    # Multiple company views or indications are relationships, not new programmes.
    relationType: Literal["CANONICAL_PROGRAMME", "JOINT_DEVELOPMENT_VIEW", "INDICATION_RELATIONSHIP"]
    sharedStudyIdentity: str = Field(min_length=1)
    companyRoleProof: str = Field(min_length=1)
    # Official-source assertion at the scope of this relation, retained verbatim.
    sourceComparison: dict
    sourceScope: Scope
    sourceProvenance: Provenance
    sourceProjectionVerified: bool
    sourceProjectionProof: str
    evidenceIds: list[str]


class Evidence(Model):
    recordId: str = Field(min_length=1)
    family: Literal["TRIAL_REGISTRY", "REGULATORY", "SIGNAL"]
    portfolioIds: list[str]
    provenance: Provenance
    armId: str | None
    comparison: dict
    scope: Scope
    jurisdiction: str | None
    independent: bool
    verified: bool


class Landscape(Model):
    recordId: str = Field(min_length=1)
    portfolioIds: list[str]
    comparison: dict
    scope: Scope
    market: str | None
    provenance: Provenance
    confidence: str
    readiness: str
    lastVerified: str


class Case(Model):
    name: str = Field(min_length=1)
    sourceKeys: list[str] = Field(min_length=1)
    expectedNcts: list[str]
    expectedPortfolioIds: list[str]
    expectedLandscapeIds: list[str]
    expectedDisposition: Literal["SUPPORTED_EXACT", "SUPPORTED_RELATIONSHIP_WITH_SCOPE_HOLD", "HELD_AMBIGUOUS", "NOT_YET_CORROBORATED"]
    oracleProvenance: str = Field(min_length=1)


class Snapshot(Model):
    schemaVersion: Literal["R1C_SNAPSHOT_V1"]
    snapshotId: str = Field(min_length=1)
    capturedAt: str = Field(min_length=1)
    company: str = Field(min_length=1)
    companyAliases: list[str]
    relatedCompanies: list[str]
    sourceWatchRecordId: str = Field(min_length=1)
    expectedSourceCount: int = Field(gt=0)
    expectedDispositionCounts: dict[str, int]
    completeTables: list[str]
    scopeDescription: str = Field(min_length=1)
    sources: list[Source]
    candidates: list[Candidate]
    portfolio: list[Portfolio]
    trials: list[Trial]
    arms: list[Arm]
    relations: list[Relation]
    evidence: list[Evidence]
    landscape: list[Landscape]
    cases: list[Case]


def comparator():
    # Supported import order; ASGI startup hooks (live retrieval) are not executed.
    import service_entrypoint  # noqa: F401
    import portfolio_discovery_extension_v11 as base
    import portfolio_discovery_extension_v16 as latest
    if base.DISCOVERY_VERSION != latest.DISCOVERY_VERSION:
        raise RuntimeError("Required V1.6 comparator not active")
    return base


def scope_reasons(a: Scope, b: Scope) -> list[str]:
    reasons = []
    for field in SCOPE_FIELDS:
        left, right = getattr(a, field), getattr(b, field)
        if not a.proofReferences.get(field, "").strip() or not b.proofReferences.get(field, "").strip():
            reasons.append("UNPROVEN_" + field.upper())
        elif left is None or right is None:
            reasons.append("UNASSESSED_" + field.upper())
        elif (sorted(left) != sorted(right) if field == "components" else left != right):
            reasons.append("CONFLICT_" + field.upper())
    if a.companyRole == "unknown" or b.companyRole == "unknown" or not a.roleProof.strip() or not b.roleProof.strip():
        reasons.append("COMPANY_ROLE_UNPROVEN")
    elif a.companyRole != b.companyRole:
        reasons.append("CONFLICT_COMPANY_ROLE")
    if len(set(a.components)) != len(a.components) or len(set(b.components)) != len(b.components):
        reasons.append("DUPLICATE_REGIMEN_COMPONENT")
    return reasons


def provenance_reasons(p: Provenance) -> list[str]:
    reasons = []
    if urlparse(p.url).scheme != "https" or not urlparse(p.url).hostname:
        reasons.append("INVALID_OFFICIAL_SOURCE_URL")
    for field in ("asOf", "retrievedAt"):
        try:
            value = getattr(p, field)
            if not value.strip():
                reasons.append("MISSING_PROVENANCE_" + field.upper())
                continue
            if field == "asOf" and len(value) == 10:
                datetime.strptime(value, "%Y-%m-%d")
            elif datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo is None:
                raise ValueError()
        except ValueError:
            reasons.append("INVALID_PROVENANCE_" + field.upper())
    return reasons


def validate(s: Snapshot) -> dict:
    base = comparator()
    issues = []
    missing = {"sources", "candidates", "portfolio", "trials", "arms", "relations", "evidence", "landscape"} - set(s.completeTables)
    if missing:
        return blocked(["Incomplete exports: " + ", ".join(sorted(missing))], s.expectedSourceCount)
    try:
        if datetime.fromisoformat(s.capturedAt.replace("Z", "+00:00")).tzinfo is None:
            raise ValueError()
    except ValueError:
        issues.append("INVALID_SNAPSHOT_TIMESTAMP")
    company_names = {s.company, *s.companyAliases}
    allowed_companies = company_names | set(s.relatedCompanies)
    indexes = {}
    for name in ("candidates", "portfolio", "trials", "arms", "relations", "evidence", "landscape"):
        records = getattr(s, name)
        indexes[name] = {r.recordId: r for r in records}
        if len(indexes[name]) != len(records):
            issues.append("DUPLICATE_IDS_" + name.upper())
    key_counts = Counter(r.stableKey for r in s.sources)
    if len(s.sources) != s.expectedSourceCount:
        issues.append("SOURCE_DENOMINATOR_MISMATCH")
    if any(v != 1 for v in key_counts.values()):
        issues.append("DUPLICATE_OFFICIAL_SOURCE_KEYS")
    counts = Counter(r.baselineDisposition for r in s.sources)
    unverified_history = counts.get("UNVERIFIED", 0)
    known_history = {k: v for k, v in counts.items() if k != "UNVERIFIED"}
    # A historical aggregate is not a per-key ledger: only compare complete keyed
    # totals; for partial proof, detect overcounts without inventing classifications.
    if unverified_history:
        if any(v > s.expectedDispositionCounts.get(k, 0) for k, v in known_history.items()):
            issues.append("R1A_PARTIAL_DISPOSITION_OVERCOUNT")
    elif known_history != {k: v for k, v in s.expectedDispositionCounts.items() if v}:
        issues.append("R1A_DISPOSITION_TOTAL_MISMATCH")
    if any(p.company not in allowed_companies for p in s.portfolio):
        issues.append("UNDECLARED_RELATED_COMPANY_VIEW")
    for p in s.portfolio:
        if set(p.comparison) - set(base.PortfolioSnapshotRow.model_fields):
            issues.append("UNKNOWN_PORTFOLIO_COMPARISON_FIELDS:" + p.recordId)
        if p.comparison.get("recordId") != p.recordId or p.comparison.get("company") != p.company:
            issues.append("PORTFOLIO_COMPARISON_IDENTITY_MISMATCH:" + p.recordId)
    if len({c.name for c in s.cases}) != len(s.cases):
        issues.append("DUPLICATE_CASE_NAMES")
    active = defaultdict(list)
    for c in s.candidates:
        if c.active and c.sourceWatchRecordId == s.sourceWatchRecordId:
            active[c.stableKey].append(c)
    if set(active) - set(key_counts):
        issues.append("EXTRA_ACTIVE_SOURCE_KEYS")

    def match(data, p, provenance, joint_view=False):
        if set(data) - set(base.DiscoverySourceRow.model_fields):
            raise ValueError("UNKNOWN_COMPARATOR_SOURCE_FIELDS")
        if set(p.comparison) - set(base.PortfolioSnapshotRow.model_fields):
            raise ValueError("UNKNOWN_COMPARATOR_PORTFOLIO_FIELDS")
        if (p.comparison.get("recordId") != p.recordId or p.comparison.get("company") != p.company or
                data.get("sourceRecordId") != provenance.sourceRecordId or data.get("sourceUrl") != provenance.url):
            raise ValueError("COMPARATOR_PROVENANCE_MISMATCH")
        source_input = base.DiscoverySourceRow.model_validate(data)
        if joint_view and source_input.company != p.company:
            # An explicit, verified joint-development relationship authorizes only
            # the read-only company view. Neither raw source nor comparator rules
            # are altered; company names are never registered as aliases.
            source_input = source_input.model_copy(update={"company": p.company, "ownershipResolved": True})
        result = base.compare_discovery(base.DiscoveryCompareRequest(
            company=p.company, companyAliases=s.companyAliases if p.company in company_names else [],
            sourceRows=[source_input],
            # A proposed relation is tested in its controlled company view. Scope
            # and duplicate equivalent canonical views are checked separately.
            portfolioRows=[base.PortfolioSnapshotRow.model_validate(x.comparison)
                           for x in s.portfolio if x.company == p.company], batchRunId=s.snapshotId))
        if not result.readOnly or any(result.guardrails.get(k) is not False for k in
                                     ("masterWrites", "portfolioMutation", "fuzzyMatching")):
            raise RuntimeError("COMPARATOR_GUARDRAIL_VIOLATION")
        r = result.candidates[0]
        reasons = provenance_reasons(provenance)
        if data.get("company") not in allowed_companies or not data.get("sourceFamily"):
            reasons.append("COMPARATOR_COMPANY_FAMILY_UNPROVEN")
        if r["classification"] != "MATCHED" or r["existingPortfolioRecordIds"] != [p.recordId]:
            reasons.append("ASSET_INDICATION_NOT_EXACT")
        if r.get("fieldDeltas"):
            reasons.append("FIELD_DELTA_REQUIRES_REVIEW")
        return reasons, r

    # Links are checked symmetrically, allowing legitimate one-to-many relations.
    edge_issues = defaultdict(list)
    for table, field, reverse in (("candidates", "candidateIds", "portfolioIds"),
                                   ("trials", "trialIds", "portfolioIds"),
                                   ("landscape", "landscapeIds", "portfolioIds")):
        for p in s.portfolio:
            links = getattr(p, field)
            if len(links) != len(set(links)):
                edge_issues[p.recordId].append("DUPLICATE_" + field.upper())
            for rid in links:
                r = indexes[table].get(rid)
                if r is None or p.recordId not in getattr(r, reverse):
                    edge_issues[p.recordId].append(f"NONRECIPROCAL_{table.upper()}:{rid}")
        for r in getattr(s, table):
            links = getattr(r, reverse)
            if len(links) != len(set(links)):
                issues.append(f"DUPLICATE_{table.upper()}_PORTFOLIO_LINK:{r.recordId}")
            for pid in links:
                p = indexes["portfolio"].get(pid)
                if p is None or r.recordId not in getattr(p, field):
                    edge_issues[pid].append(f"NONRECIPROCAL_{table.upper()}:{r.recordId}")
    for t in s.trials:
        if len(t.armIds) != len(set(t.armIds)):
            issues.append("DUPLICATE_TRIAL_ARM_LINK:" + t.recordId)
        for aid in t.armIds:
            a = indexes["arms"].get(aid)
            if a is None or a.trialRecordId != t.recordId or a.nct != t.nct:
                issues.append("BROKEN_TRIAL_ARM_LINK:" + aid)
    for a in s.arms:
        t = indexes["trials"].get(a.trialRecordId)
        if t is None or a.recordId not in t.armIds or a.nct != t.nct:
            issues.append("BROKEN_ARM_PARENT_LINK:" + a.recordId)
    for rel in s.relations:
        source = next((r for r in s.sources if r.stableKey == rel.stableKey), None)
        if source is None or rel.recordId not in source.relationIds:
            issues.append("UNACCOUNTED_RELATION:" + rel.recordId)

    rows = []
    for source in s.sources:
        reasons, failures = [], []
        reasons.extend(provenance_reasons(source.provenance))
        if source.granularity == "unknown":
            reasons.append("OFFICIAL_SOURCE_GRAIN_UNASSESSED")
        try:
            if set(source.comparison) - set(base.DiscoverySourceRow.model_fields):
                raise ValueError("UNKNOWN_OFFICIAL_COMPARATOR_FIELDS")
            base.DiscoverySourceRow.model_validate(source.comparison)
        except (ValueError, ValidationError) as exc:
            failures.append(str(exc))
        if source.comparison.get("sourceRecordId") != source.provenance.sourceRecordId or source.comparison.get("sourceUrl") != source.provenance.url or source.comparison.get("sourceWatchRecordId") != source.sourceWatchRecordId or source.comparison.get("company") != source.company:
            failures.append("OFFICIAL_COMPARISON_IDENTITY_MISMATCH")
        if "PIPELINE" not in source.assessedFamilies:
            reasons.append("OFFICIAL_PIPELINE_NOT_ASSESSED")
        candidates = active.get(source.stableKey, [])
        c = candidates[0] if len(candidates) == 1 else None
        if c is None:
            reasons.append("ACTIVE_CANDIDATE_COUNT_" + str(len(candidates)))
        if source.company not in company_names or source.sourceWatchRecordId != s.sourceWatchRecordId:
            failures.append("OFFICIAL_SOURCE_IDENTITY_MISMATCH")
        if c:
            if c.sourceRecordId != source.provenance.sourceRecordId or c.company not in company_names:
                failures.append("CANDIDATE_SOURCE_IDENTITY_MISMATCH")
            if c.sourceVersion != source.provenance.version or c.sourceGranularity != source.granularity:
                reasons.append("STALE_OR_UNPROVEN_CANDIDATE_SOURCE_GRAIN")
            if c.reviewStatus.strip().casefold() == "superseded":
                reasons.append("SUPERSEDED_ACTIVE_CANDIDATE")
            if c.queueEligible or c.portfolioWriteEligible:
                failures.append("PERSISTED_WRITE_ELIGIBILITY_CONFLICT")
            if c.holdReason.strip():
                reasons.append("PERSISTED_CANDIDATE_HOLD:" + c.holdReason)
            if any(x in c.programmeGate.lower() for x in ("unassessed", "unresolved", "hold", "review")):
                reasons.append("PERSISTED_PROGRAMME_GATE_UNRESOLVED")
        if source.baselineDisposition == "UNVERIFIED":
            reasons.append("R1A_HISTORICAL_DISPOSITION_UNVERIFIED")
        elif not source.baselineProof.strip():
            failures.append("MISSING_R1A_DISPOSITION_PROOF")
        if source.baselineDisposition == "HELD":
            reasons.append("R1A_HELD_PRESERVED:" + source.baselineReason)
            if not source.baselineReason.strip():
                failures.append("MISSING_R1A_HOLD_REASON")
        if source.baselineDisposition in {"NEW", "EXCLUDED"}:
            reasons.append("R1A_" + source.baselineDisposition + "_NOT_PROMOTED")
        if len(set(source.relationIds)) != len(source.relationIds):
            failures.append("DUPLICATE_SOURCE_RELATION_IDS")
        relations = []
        for rid in source.relationIds:
            rel = indexes["relations"].get(rid)
            if rel is None or rel.stableKey != source.stableKey:
                failures.append("RELATION_SOURCE_KEY_MISMATCH:" + rid)
                continue
            p = indexes["portfolio"].get(rel.portfolioId)
            # Evidence and persistence are separate gates. A proposed relation
            # may be assessed before a Candidate link is approved or written.
            rr, evidence_rows, persistence_reasons = [], [], []
            if p is None:
                failures.append("DANGLING_CANONICAL_TARGET:" + rel.portfolioId)
                continue
            if c is None or p.recordId not in c.portfolioIds or c.recordId not in p.candidateIds:
                persistence_reasons.append("NO_PERSISTED_CANDIDATE_CANONICAL_LINK")
            if not rel.companyRoleProof.strip():
                rr.append("UNPROVEN_RELATION_COMPANY_ROLE")
            joint_view = (rel.relationType == "JOINT_DEVELOPMENT_VIEW" and
                          bool(rel.companyRoleProof.strip()) and rel.sourceProjectionVerified and
                          bool(rel.sourceProjectionProof.strip()) and
                          p.company in allowed_companies and p.scope.companyRole in {"owner", "partner", "co-developer"})

            def relation_scope_reasons(left, right):
                codes = scope_reasons(left, right)
                if joint_view and left.companyRole in {"owner", "partner", "co-developer"} and right.companyRole in {"owner", "partner", "co-developer"}:
                    codes = [x for x in codes if x != "CONFLICT_COMPANY_ROLE"]
                return codes
            if rel.sourceProvenance != source.provenance:
                rr.append("RELATION_OFFICIAL_SOURCE_PROVENANCE_MISMATCH")
            preserved = (set(source.comparison) | set(rel.sourceComparison)) - {"company", "indication", "controlledIndicationCandidate"}
            if any(source.comparison.get(k) != rel.sourceComparison.get(k) for k in preserved):
                rr.append("SOURCE_PROJECTION_IDENTITY_OR_STATE_MUTATION")
            if rel.sourceComparison.get("company") != source.company and not joint_view:
                rr.append("UNPROVEN_PROJECTED_COMPANY_VIEW")
            if len(rel.evidenceIds) != len(set(rel.evidenceIds)):
                rr.append("DUPLICATE_RELATION_EVIDENCE_IDS")
            # Multi-indication/source-grain projections require explicit source
            # proof, never a silently substituted indication. Focal composition
            # must still agree, even for a legitimate one-to-many relationship.
            if not rel.sourceProjectionVerified or not rel.sourceProjectionProof.strip():
                rr.append("UNVERIFIED_SOURCE_SCOPE_PROJECTION")
            source_scope_issues = relation_scope_reasons(source.scope, rel.sourceScope)
            if source.granularity in {"multi_indication", "asset_umbrella"} and rel.sourceProjectionVerified and rel.sourceProjectionProof.strip():
                source_scope_issues = [r for r in source_scope_issues if any(x in r for x in
                                      ("COMPONENTS", "ROUTE", "DOSE", "COMPANY_ROLE"))]
            rr.extend("SOURCE_" + x for x in source_scope_issues)
            rr.extend(scope_reasons(rel.sourceScope, p.scope))
            comparison = None
            try:
                mr, comparison = match(rel.sourceComparison, p, rel.sourceProvenance, joint_view)
                rr.extend(mr)
            except (ValueError, ValidationError) as exc:
                rr.append(str(exc))
            for edge_issue in edge_issues[p.recordId]:
                if edge_issue.startswith("NONRECIPROCAL_CANDIDATES:"):
                    persistence_reasons.append(edge_issue)
                else:
                    rr.append(edge_issue)
            for eid in rel.evidenceIds:
                e = indexes["evidence"].get(eid)
                er = []
                t, a = None, None
                if e is None:
                    rr.append("MISSING_EVIDENCE:" + eid)
                    continue
                if e.family not in source.assessedFamilies:
                    er.append("FAMILY_NOT_ASSESSED")
                if p.recordId not in e.portfolioIds:
                    er.append("EVIDENCE_NOT_LINKED_TO_TARGET")
                if not e.verified:
                    er.append("EVIDENCE_NOT_VERIFIED")
                er.extend(relation_scope_reasons(e.scope, p.scope))
                try:
                    er.extend(match(e.comparison, p, e.provenance, joint_view)[0])
                except (ValueError, ValidationError) as exc:
                    er.append(str(exc))
                if e.family == "TRIAL_REGISTRY":
                    a = indexes["arms"].get(e.armId)
                    t = indexes["trials"].get(a.trialRecordId) if a else None
                    if a is None or t is None:
                        er.append("NCT_WITHOUT_FOCAL_ARM_PROOF")
                    else:
                        er.extend(provenance_reasons(t.provenance))
                        er.extend(provenance_reasons(a.provenance))
                        if any(urlparse(prov.url).hostname not in {"clinicaltrials.gov", "www.clinicaltrials.gov"} or t.nct not in prov.url
                               for prov in (t.provenance, a.provenance, e.provenance)):
                            er.append("OFFICIAL_NCT_URL_UNPROVEN")
                        if a.nct != t.nct or a.recordId not in t.armIds:
                            er.append("ARM_PARENT_RELATION_MISMATCH")
                        if p.recordId not in t.portfolioIds:
                            er.append("TRIAL_NOT_LINKED_TO_TARGET")
                        if a.interventionRole != "experimental":
                            er.append("NON_FOCAL_INTERVENTION_ROLE")
                        if e.provenance.authorityId != t.nct or a.provenance.authorityId != t.nct:
                            er.append("NCT_PROVENANCE_MISMATCH")
                        if rel.sharedStudyIdentity != t.nct:
                            er.append("SHARED_STUDY_IDENTITY_MISMATCH")
                        if not source.trialReferences.get(t.nct, "").strip():
                            er.append("OFFICIAL_SOURCE_NCT_RELATION_UNPROVEN")
                        er.extend(relation_scope_reasons(a.scope, p.scope))
                        try:
                            er.extend(match(a.comparison, p, a.provenance, joint_view)[0])
                        except (ValueError, ValidationError) as exc:
                            er.append(str(exc))
                if e.family == "REGULATORY" and not e.jurisdiction:
                    er.append("REGULATORY_JURISDICTION_UNASSESSED")
                evidence_rows.append({"recordId": eid, "family": e.family,
                                      "url": e.provenance.url, "sourceDate": e.provenance.asOf,
                                      "authorityId": e.provenance.authorityId,
                                      "independent": e.independent, "reasonCodes": sorted(set(er)),
                                      "nct": t.nct if t else None, "armRef": a.armRef if a else None,
                                      "trialRecordId": t.recordId if t else None,
                                      "armRecordId": a.recordId if a else None,
                                      "studyName": t.studyName if t else None,
                                      "trialVersion": t.provenance.version if t else None,
                                      "trialStatus": t.status if t else None,
                                      "scopeAssertion": e.scope.model_dump()})
            valid = [e for e in evidence_rows if not e["reasonCodes"]]
            # A link or parent NCT alone is a positive relationship, not exact proof.
            if not valid:
                rr.append("NO_EXACT_CORROBORATING_EVIDENCE")
            for e in evidence_rows:
                rr.extend(e["reasonCodes"])
            # A positive evidence assessment is NOT an approved link, R1C PASS,
            # queue instruction, or permission to bypass R1A programme holds.
            # The legacy disposition still includes persistence and fail-closed
            # requirements, keeping production acceptance unchanged.
            relations.append({"relationId": rid, "portfolioId": p.recordId,
                              "relationType": rel.relationType, "company": p.company,
                              "sharedStudyIdentity": rel.sharedStudyIdentity,
                              "sourceScopeAssertion": rel.sourceScope.model_dump(),
                              "portfolioScopeAssertion": p.scope.model_dump(),
                              "readOnlyEvidenceAssessment": ("SUPPORTED_FOR_READ_ONLY_REVIEW" if not rr else "EVIDENCE_HELD"),
                              "evidenceReasonCodes": sorted(set(rr)),
                              "persistedLinkageAssessment": ("NONRECIPROCAL" if any(x.startswith("NONRECIPROCAL_CANDIDATES:") for x in persistence_reasons)
                                                             else "NOT_PERSISTED" if persistence_reasons else "PERSISTED_RECIPROCAL"),
                              "persistenceReasonCodes": sorted(set(persistence_reasons)),
                              "reasonCodes": sorted(set(rr + persistence_reasons)),
                              "comparison": comparison, "evidence": evidence_rows})
        if c and set(c.portfolioIds) != {r["portfolioId"] for r in relations}:
            reasons.append("CANONICAL_LINK_RELATION_SET_UNASSESSED")
        reasons.extend(x for r in relations for x in r["reasonCodes"])
        if not relations:
            disposition = "HELD_AMBIGUOUS" if reasons and source.baselineDisposition == "HELD" else "NOT_YET_CORROBORATED"
        elif reasons or failures:
            critical = any("CONFLICT_" in r or r in {"ASSET_INDICATION_NOT_EXACT", "NON_FOCAL_INTERVENTION_ROLE"}
                           for r in reasons + failures)
            disposition = "SUPPORTED_RELATIONSHIP_WITH_SCOPE_HOLD" if c and c.portfolioIds and not critical else "HELD_AMBIGUOUS"
        else:
            disposition = "SUPPORTED_EXACT"
        families = {}
        for family in FAMILIES:
            ev = [e for r in relations for e in r["evidence"] if e["family"] == family]
            families[family] = ("NOT_ASSESSED" if family not in source.assessedFamilies else
                                "SUPPORTED" if family == "PIPELINE" or any(not e["reasonCodes"] for e in ev) else
                                "SCOPE_HELD" if ev else "NO_MATCH")
        authorities = {source.provenance.authorityId} if not provenance_reasons(source.provenance) and "PIPELINE" in source.assessedFamilies else set()
        authorities.update(e["authorityId"] for r in relations for e in r["evidence"]
                           if not e["reasonCodes"] and e["independent"])
        rows.append({"stableKey": source.stableKey, "sourceWatchRecordId": source.sourceWatchRecordId,
                     "sourceRecordId": source.provenance.sourceRecordId,
                     "candidateId": c.recordId if c else None,
                     "baselineDisposition": source.baselineDisposition, "disposition": disposition,
                     "status": "FAIL" if failures else "PASS" if disposition == "SUPPORTED_EXACT" else "HOLD",
                     "reasonCodes": sorted(set(reasons + failures)), "relations": relations,
                     "sourceUrl": source.provenance.url, "sourceAsOf": source.provenance.asOf,
                     "retrievedAt": source.provenance.retrievedAt, "adapterVersion": source.adapterVersion,
                     "parserVersion": source.parserVersion,
                     "sourceGranularity": source.granularity, "familyStatus": families,
                     "independentSourceCount": len(authorities), "independentAuthorityIds": sorted(authorities),
                     "queueEligible": False, "portfolioWriteEligible": False})

    # TL is an impact map, never counted as an independent source family. Missing
    # direct TL links are coverage review, not a confirmed integrity defect.
    impacts = []
    for p in s.portfolio:
        mapped = []
        for lid in p.landscapeIds:
            l = indexes["landscape"].get(lid)
            if l is None:
                continue
            reasons = scope_reasons(l.scope, p.scope)
            try:
                reasons.extend(match(l.comparison, p, l.provenance)[0])
            except (ValueError, ValidationError) as exc:
                reasons.append(str(exc))
            mapped.append({"recordId": lid, "status": "HOLD" if reasons else "PASS",
                           "reasonCodes": sorted(set(reasons)), "market": l.market,
                           "sourceUrl": l.provenance.url, "lastVerified": l.lastVerified,
                           "companyRole": l.scope.companyRole,
                           "freshness": "NOT_ASSESSED", "marketAvailability": "NOT_ASSESSED"})
        related = [r for r in rows if any(x["portfolioId"] == p.recordId for x in r["relations"])]
        families = sorted({f for r in related if r["status"] == "PASS"
                           for f, status in r["familyStatus"].items() if status == "SUPPORTED"})
        impacts.append({"portfolioId": p.recordId, "landscape": mapped,
                        "landscapeCoverage": "LINKED_SCOPE_CHECKED" if mapped else "COVERAGE_REVIEW_ONLY",
                        "integrityIssues": edge_issues[p.recordId],
                        "trialIds": p.trialIds, "observedEvidenceFamilies": p.evidenceFamilies,
                        "observedCrossSourceStatus": p.crossSourceStatus,
                        "derivedEvidenceFamilies": families,
                        "status": "FAIL" if edge_issues[p.recordId] else
                                  "HOLD" if any(x["status"] == "HOLD" for x in mapped) else "PASS",
                        "tlRefresh": "UNPROVEN", "statusUpdate": "NONE", "linksChanged": False})
    if any(edge_issues.values()):
        issues.extend(f"{pid}:{e}" for pid, es in edge_issues.items() for e in es)
    cases = []
    for case in s.cases:
        selected = [r for r in rows if r["stableKey"] in case.sourceKeys]
        problems = []
        absent = set(case.sourceKeys) - {r["stableKey"] for r in selected}
        if len(set(case.sourceKeys)) != len(case.sourceKeys):
            problems.append("DUPLICATE_CASE_SOURCE_KEYS")
        if any(r["disposition"] != case.expectedDisposition for r in selected):
            problems.append("CASE_DISPOSITION_DIFFERS_FROM_ORACLE")
        targets = {rel["portfolioId"] for r in selected for rel in r["relations"]}
        if targets != set(case.expectedPortfolioIds):
            problems.append("CASE_PORTFOLIO_RELATION_SET_DIFFERS")
        ncts = {t.nct for t in s.trials if targets.intersection(t.portfolioIds)}
        if not set(case.expectedNcts).issubset(ncts):
            problems.append("EXPECTED_TRIAL_LINK_MISSING")
        proved_ncts = {e["nct"] for r in selected for rel in r["relations"] for e in rel["evidence"]
                       if e["nct"] and not e["reasonCodes"]}
        missing_arm_proof = set(case.expectedNcts) - proved_ncts
        tl = {lid for p in s.portfolio if p.recordId in targets for lid in p.landscapeIds}
        if tl != set(case.expectedLandscapeIds):
            problems.append("CASE_TL_LINK_SET_DIFFERS")
        dependent = [i for i in impacts if i["portfolioId"] in targets]
        status = ("FAIL" if problems or any(r["status"] == "FAIL" for r in selected) or
                  any(i["status"] == "FAIL" for i in dependent) else
                  "HOLD" if absent or missing_arm_proof or issues or not selected or any(r["status"] == "HOLD" for r in selected) or
                  any(i["status"] == "HOLD" for i in dependent) else "PASS")
        cases.append({"name": case.name, "status": status, "reasonCodes": problems,
                      "missingSourceKeys": sorted(absent), "sourceKeys": case.sourceKeys,
                      "nctsWithoutExactFocalArmProof": sorted(missing_arm_proof),
                      "expectedNcts": case.expectedNcts, "relations": [x for r in selected for x in r["relations"]],
                      "downstreamImpacts": dependent})
    # Never emit a validated status proposal when whole-snapshot integrity fails.
    if issues or any(r["status"] == "FAIL" for r in rows):
        for i in impacts:
            i["derivedEvidenceFamilies"] = []
    return {"ruleVersion": VERSION, "comparatorVersion": base.DISCOVERY_VERSION,
            "frameworkVersion": "2.22", "batchId": s.snapshotId,
            "status": "FAIL" if issues or any(r["status"] == "FAIL" for r in rows) or
                      any(c["status"] == "FAIL" for c in cases) else
                      "HOLD" if any(r["status"] == "HOLD" for r in rows) or
                      any(c["status"] == "HOLD" for c in cases) else "PASS",
            "issues": issues, "testedSourceKeys": len(s.sources), "sourceDispositionCounts": dict(counts),
            "historicalDispositionCoverage": {
                "recordedPerKey": len(s.sources) - unverified_history,
                "unverifiedPerKey": unverified_history,
                "reportedR1AAggregate": dict(s.expectedDispositionCounts),
                "verifiedPerKeyCounts": known_history,
                "historicalKeyedReplay": ("NOT_REPLAYED_PARTIAL_EVIDENCE" if unverified_history else "FULL_KEYED_COUNTS_COMPARED"),
            },
            "sourceCoverage": {"expected": s.expectedSourceCount, "observed": len(s.sources),
                               "unique": len(key_counts), "activeCandidateAddressable": sum(len(active[k]) == 1 for k in key_counts)},
            "evidenceCoverage": {"supportedExact": sum(r["disposition"] == "SUPPORTED_EXACT" for r in rows)},
            "confirmedMasterPortfolioCoverage": {"validatedExistingTargetIds": sorted({rel["portfolioId"] for r in rows
                                                                                      if r["status"] == "PASS" and not issues and not any(x["status"] == "FAIL" for x in rows)
                                                                                      for rel in r["relations"]}),
                                                   "gate3Pass": False, "gate7Pass": False,
                                                   "note": "Candidate addressability is not master completeness; gate re-tests remain separate"},
            "rows": rows, "cases": cases, "downstreamImpacts": impacts, "guardrails": GUARDRAILS.copy()}


def blocked(issues, count=None, cases=()):
    return {"ruleVersion": VERSION, "frameworkVersion": "2.22",
            "status": "BLOCKED — INPUT SNAPSHOT REQUIRED", "testedSourceKeys": 0,
            "expectedSourceCount": count, "issues": issues,
            "rows": [], "matrixAvailability": "No observed row matrix — snapshot required",
            "cases": [{"name": c["name"], "status": "HOLD", "ncts": c.get("ncts", []),
                       "reasonCodes": ["INPUT_SNAPSHOT_REQUIRED"], "testedSourceKeys": 0} for c in cases],
            "guardrails": GUARDRAILS.copy()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--cases", type=Path)
    parser.add_argument("--expected-count", type=int)
    parser.add_argument("--schema", action="store_true")
    args = parser.parse_args()
    if args.schema:
        print(json.dumps(Snapshot.model_json_schema(), indent=2))
        return 0
    specs = json.loads(args.cases.read_text()) if args.cases else []
    if args.snapshot is None:
        result = blocked(["No row-level snapshot supplied; audit totals are not fixture data"], args.expected_count, specs)
    else:
        try:
            snapshot = Snapshot.model_validate_json(args.snapshot.read_text())
            if args.expected_count is not None and snapshot.expectedSourceCount != args.expected_count:
                raise ValueError("Requested denominator differs from snapshot")
            result = validate(snapshot)
            required = {c["name"] for c in specs}
            if required - {c.name for c in snapshot.cases}:
                result = blocked(["Required case mappings/oracles missing"], args.expected_count, specs)
        except (ValidationError, ValueError) as exc:
            result = blocked([str(exc)], args.expected_count, specs)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["status"] == "PASS" else 1 if result["status"] == "FAIL" else 2


if __name__ == "__main__":
    raise SystemExit(main())
