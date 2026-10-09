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
