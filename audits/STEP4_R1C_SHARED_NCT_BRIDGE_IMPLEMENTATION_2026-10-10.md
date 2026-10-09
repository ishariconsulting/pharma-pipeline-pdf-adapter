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


## First real end-to-end authoritative evidence canary: iMMagine-1 — 10 Oct 2026

**Test scope:** ONE of the existing six Gilead R1C cases, chosen because the recorded trial has one explicit experimental CAR-T arm and one existing Portfolio target. **No complete 53-key resolver input or write attempted.** All other five case assessments remain unchanged. Goal: distinguish whether real official clinical programme evidence exists from whether the system has projected/persisted an approved exact link.

**Official cross-source evidence found (externally observed read-only):**
- Official Gilead pipeline `https://www.gilead.com/science/pipeline`, source baseline updated 2026-08-04 as of end-Q2: `Anitocabtagene autoleucel (iMMagine-1)`, 4L+ relapsed/refractory multiple myeloma, Filed.
- **Gilead's own clinical study site** `https://www.gileadclinicaltrials.com/study?nctid=NCT05396885`: explicitly links iMMagine-1, NCT05396885 and anitocabtagene autoleucel (formerly CART-ddBCMA), multiple myeloma; eligibility at least three prior systemic regimens; study last updated 2026-02-11.
- Official registry `https://clinicaltrials.gov/study/NCT05396885`: Sponsor Kite, A Gilead Company, one **experimental** anitocabtagene-autoleucel arm, single IV dose. This is a focal registry arm description, not a persisted structured verified arm child.
- Gilead ownership/role: `https://www.gilead.com/news/news-details/2026/gilead-sciences-completes-acquisition-of-arcellx-ahead-of-potential-commercial-launch-of-anito-cel` (2026-04-28) confirms acquisition of prior co-development partner Arcellx and full control of anito-cel. This is a date-sensitive company-role fact, not proof that prior sponsor records should be retroactively altered.

**Direct live Airtable read-only inspection:**
- Pipeline Candidate `recOGc2QkKjGiXhk8` / stable official Sitecore source ID `60c61c1d-d2db-4aa6-8318-6969fcf40ab1`: original asset `Anitocabtagene autoleucel (iMMagine-1)`, indication `4L+ relapsed/refractory multiple myeloma`, Filed / Registration, review status `New`, and **no Existing Portfolio Match**. Candidate's stored evidence says `study=""` and `trialIds=[]`, as expected for the original pipeline feed.
- Portfolio `recSPdCh4UJgdQVGd`: `Anito-cel` / `anitocabtagene autoleucel`, indication `Fourth-line or later relapsed/refractory multiple myeloma`, linked Clinical Trial `recx96KA6Jft71emY` (`NCT05396885`), but **not linked to the above source Candidate**. Exact programme endorsement still unapproved.
- **Important semantic discrepancy:** Portfolio `Treatment Setting / Line` contains `3L+` (also embedded in immutable PFK1 qualifier), whereas the official Gilead pipeline and Portfolio indication say `4L+`. The registry eligibility says `at least 3 prior regimens`, which is *consistent with treatment in fourth or a later line*; 3 prior regimens must not silently become 3L+. This requires controlled shared qualifier review; don't change PFK1 or Portfolio automatically.
- Clinical Trial `recx96KA6Jft71emY` contains raw `Arm 1: anitocabtagene-autoleucel; Type: EXPERIMENTAL; single-dose IV ...`, sponsor Kite, partner Arcellx, registry update 2026-02-11, synced 2026-09-28. **No linked `Clinical Trial Arms & Cohorts` child; no independently signed-off focal-arm assertion.**

**Strict resolver compatibility flags (not a new code test):**
1. New `assess_authority_bridge` requires identical `asOf` across all source/trial/arm/evidence provenance (and optional protocol), but the Gilead pipeline baseline 2026-08-04 and CT.gov study update 2026-02-11 are legitimately different. That means a fabricated common date would be wrong, and an otherwise genuine evidence set would HOLD pending an explicit **temporal compatibility** policy. Do not relax without source/version/freshness analysis and approval.
2. The optional `protocol` corroboration requires exactly matching original source hostname and authority. Gilead's public trial site is `www.gileadclinicaltrials.com`, whereas the official pipeline uses `www.gilead.com`, so verified corporate source-family equivalence must not be silently inferred. Cite the exact official source, relationship and date if this proof is needed.
3. The original 53 source-key R1A per-key ledger and full `R1C_SNAPSHOT_V1` linked-record closure have not been supplied to the resolver, and existing six focal Candidates lack persisted Portfolio link. No full R1C gate verdict can be computed from a single manually inspected case.

**Finite gate outcome:** **Official identity / NCT / experimental-arm / ≥3 prior regimens / owner provenance: independently corroborated for this one programme at document/registry level.** **Persisted canonical Candidate→Portfolio programme reconciliation and R1C acceptance: HOLD** because no exact approved Candidate link or structured verified focal arm, treatment-line qualifier mismatch, and strict temporal/source authority contract. This is a positive demonstration that the essential clinical source evidence **exists**, and a precise counterexample to "no clinical evidence available". It is not production success. Do not investigate another five programmes, enable OFF audit writers, create new automations, edit Portfolio/PFK1, or force R1A HELD states through the bridge.

**Architecture takeaway:** source availability is not the obstacle for this programme. The next bounded shared decision must establish safe, reviewed **evidence attestation to existing arm/portfolio relationships**, together with provenance temporal compatibility and distinct **prior regimens vs treatment line** semantics; otherwise even genuine source observations cannot reach a trusted client-ready relationship. R1C BLOCKED; Gilead Gates 3 and 7 GAP. Any implementation/master writes need separate approval.
