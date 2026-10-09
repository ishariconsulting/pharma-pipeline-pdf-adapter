# Shared independent-authority bridge — read-only implementation

Recovery branch only; default callers and production comparator unchanged.

## Input and assessment

The existing `R1C_SNAPSHOT_V1` input accepts optional
`enableIndependentAuthorityBridge` (default false) and `authorityBridges`
(default empty). No Airtable fields, routes, network retrieval or automation
are introduced. `AuthorityBridge` reuses existing Provenance and Scope records;
the original source-item envelope remains captured, unverified evidence under
`source_evidence_contract.py`, not proof of programme reconciliation.

Each bridge binds a relation/evidence ID, immutable official stable key, trial
and experimental arm to exact source/trial/arm provenance. It requires explicit
reviewer verification, independent originating registry evidence, and verbatim
proof excerpts for programme, trial, experimental arm, company role, components,
indication, line, population, setting, route and dose. Missing dimensions remain
held; applicability must be explicitly proved rather than inferred.

Existing shared comparator, reciprocal links, scope, provenance, focal-arm,
R1A, case-oracle and downstream checks still apply. Parent NCT and aggregated
CT.gov asset/first-condition seed output cannot substitute for arm evidence.
An optional original official publisher protocol can prove an exact alias;
it must share the pipeline publisher's hostname and originating authority.
Republished/non-independent evidence cannot establish a bridge or increase
independent-source counts. Multiple competing bridges are ambiguous, not ranked.

Opted-in evidence emits `bridgeAssessment` with `PIPELINE_DIRECT_NCT`,
`INDEPENDENT_AUTHORITY_BRIDGE`, `NO_BRIDGE_EVIDENCE` or `AMBIGUOUS`, bound
provenance, reasons and false write/auto-link eligibility. Direct pipeline NCT
references retain precedence. Disabling the option retains legacy output.
Evidence support cannot override R1A HELD/UNVERIFIED or absent persistence.

## Deliberately conservative limits

Inputs are reviewer-verified assertions with original excerpts; this is not an
automatic semantic parser or a means of authenticating a fabricated export.
Authenticity and exact interpretation must be established during the controlled
evidence review. All authority as-of dates must currently align exactly;
registry versions must agree. Different observation dates remain held until an
explicit temporal compatibility contract is approved. A protocol on a different
official hostname also remains held; hostname/authority equivalence is not
inferred. No alias vocabulary or company-specific rules are added.

The clinical-canary inventory/design documents were inspected. Their original
module-aware/protocol-assignment automation bodies are not available in this
checkout, so their executable logic was not replayed or activated.

## Gilead evidence gap

The existing design-decision audit records a user-observed official capture of
53 programme IDs, no registry URLs and no NCT mentions. This task did not fetch
or independently inspect that raw payload. The live-gate audit records zero
verified focal-arm child relationships for the eight six-case trial NCTs and
no direct Portfolio links for the six focal Candidates. These observations
are not verified programme bridges. All six cases remain held.

A controlled replay still needs the private original capture and source-issued
dates/granularity; complete current keyed source/Candidate/Portfolio inputs;
original versioned registry studies with exact experimental arm records;
verified scope/role/proof excerpts and official alias/co-development protocols
where needed; temporal alignment; exact historical keyed R1A dispositions and
reasons (or UNVERIFIED); and the independent six-case oracle and downstream
Treatment Landscape relationships. Candidate statuses cannot reconstruct R1A.

## Validation commands

Baseline: 93 tests passed, zero failures/errors/skips.

```sh
PYTHONDONTWRITEBYTECODE=1 python -m unittest test_source_evidence_contract test_sitecore_source_evidence test_r1c_shared_lineage test_r1c_authority_bridge -v
PYTHONDONTWRITEBYTECODE=1 python r1c_regression.py
```

The expanded unittest suite comprises the preserved 93 plus 24 bridge tests.
Actual final run: **117 run, 117 passed, 0 failed, 0 errored, 0 skipped**,
11.456 seconds, exit 0. Regression report: **105 run, 105 passed, 0 failed,
0 errored, 0 skipped**, exit 2; all six real cases HOLD and 0 real source keys
tested. `git diff --check` passed. Dependency deprecation warnings were nonfatal.
The regression report now includes all 81 existing resolver tests plus the 24
bridge tests. Its missing-real-snapshot exit code 2 remains an evidence HOLD,
not a synthetic-test failure. Code-level success is not Gilead Gate 3/7 approval.

Recommendation: ready for a controlled offline read-only evidence assessment
with independently reviewed inputs; R1C/customer release remains HOLD. No live
source calls, Airtable writes, commits, pushes, deployment or production merge.


## Controlled Gilead live Airtable evidence readiness decision — 10 October 2026

**Read-only evidence gate: BLOCKED — no verified real independent-authority programme bridge.** This follows the GitHub branch commit `9cd8fb6b09e54578948071a79abaa8224758da95` and its user-reported 117/117 passing synthetic regressions. This is an evidence inspection, not an execution of `validate()` on a complete authoritative 53-key `R1C_SNAPSHOT_V1` snapshot; do not report 53 source keys semantically tested.

**Observed directly by the current scoped Airtable read:**
- Company `rec60nNJ7EvlHlt0v`; Gilead pipeline Source Watch `recCyELG6w7TZKwQZ` last checked `2026-10-02`; Source Snapshot Imports link empty.
- 62 linked pipeline Candidates: **55 active** (53 nonempty distinct source keys plus two resolved, keyless historical Portfolio-completeness Candidates), **7 Superseded**. Zero duplicate distinct-key identities among active source-keyed Candidates. The 53 count agrees numerically with the user's separate official-source 53-row Codespaces capture, but exact keyed per-row equality was not rerun in this assessment.
- 55 Company-linked Portfolio records. **Zero** currently populated `Cross-source Status` and **zero** populated `Evidence Families` fields.
- All six held programme Candidates remain without a direct approved `Existing Portfolio Match` link: `recOGc2QkKjGiXhk8` (iMMagine-1), `recLd0O4DDoSUICO0` (iMMagine-3), `recUaxfv5urojBewZ` (ISLEND-1/2), `recj50kAokdSo6REw` (NAPISTAR 1-01), `recfWkIVpdJboItRp` (PALISADES-1), `rectOd70xCzPWfkls` (ARTISTRY-1/2). Their statuses remain New or Needs Review, and scope-gate evidence is absent/unresolved.
- All **eight** scoped Clinical Trial parents (NCT05396885, NCT06413498, NCT06630286, NCT06630299, NCT06303505, NCT04989803, NCT05502341, NCT06333808) retain one or more Portfolio links and contain a raw `CT.gov Arm / Cohort Raw` description, but **none** has a structured `Clinical Trial Arms & Cohorts` child. Gilead Company has no linked structured cohort or CT.gov Arm Evidence record. A parent/NCT/arm-description is not a verified focal experimental arm.
- Existing 55-row baseline remains `Needs review` for all rows on strict evidence-scope requirements; no master data edited.

**Boundary conclusion:** Evidence intake/validation, not the opt-in resolver code, is the currently missing R1C acceptance ingredient: source-key/issuer-as-of provenance, verified official trial-arm/version assertion, programme/indication/population/role/temporal match, and correct Candidate↔Portfolio persistence. The existing Gilead Sitecore source includes zero NCT tokens or registry anchors in the user-captured 53 raw items, so the independent bridge is the only designed option; **do not infer links** or repeat source retrieval hoping for hidden NCT references. Without independently reviewed authority bridge assertions and a complete 53-key closure snapshot, no actual R1C source row is positively certified. Six cases remain HOLD. No Gate 3/Gate 7 status change.

**Stop decision:** Do not undertake more generic code tasks, re-run synthetic tests, create company-specific automations, trigger OFF CT.gov audit writers, or claim production release. Retain this R1C evidence blocker as a named gate. To proceed within the currently locked Step 4 priority order requires a separately approved, finite *source/arm evidence acquisition and attestation* task using the existing authenticated source and clinical data contracts (with every unsupported programme HELD). Alternatively, moving to R2 while keeping R1C BLOCKED changes the recovery work order and requires explicit user approval. No new code or production action authorised here.
