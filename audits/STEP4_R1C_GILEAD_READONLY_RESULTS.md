# Step 4 / R1C — read-only implementation and regression results

**Decision: HOLD / IN PROGRESS. Full Gilead reconciliation: BLOCKED — INPUT SNAPSHOT REQUIRED.**

Branch: `recovery/step4-r1c-gilead-readonly`. Base: `e657d3c9b0e7db9c0513ccd08218bff6cc062479`.

## Scope and framework

Reviewed the supplied **Ishari Production Reliability Framework v2.22**, especially its shared evidence-to-programme resolver specification, Rules A–E, six-case fixtures and R1C acceptance sequence. Attachment SHA-256: `d618ebe15bde60d308c21fa98e82c6cf45c11485270c874830c68b4f180f37ba`.

Document requirements supplied acceptance criteria. They did not authorize external project-control updates, production publication or writes beyond the user's request. No Airtable access, credential use, production deployment, merge, push, master-data change or new automation occurred. Original tracked repository files remain unchanged. All new code and results are local, uncommitted branch files for review.

## Architecture and changes for review

`r1c_shared_lineage.py` is an offline, company-agnostic composition layer around the existing V1.6 shared comparator. The `service_entrypoint` import initializes the supported comparator stack without running ASGI startup hooks. No endpoint or production caller is registered, and no existing comparator implementation is changed.

The archived V2.61.2 recurring Source Watch caller is found at `origin/audit/source-watch-v2.61.2-baseline-2026-10-07:airtable_scripts/pipeline_source_watch_recurring_deployed_2026-10-07.txt`. It accepts `sourceWatchRecordId` and has queue-create and Source Watch metadata-update calls. It is **not safe to execute as a read-only regression** and was only inspected. Framework v2.22 identifies it as the published caller; current live deployment parity was not independently queried. V2.61.3 remains a separate diagnostic draft; it was not executed or published.

The draft resolver:

- Preserves opaque Source Watch + official stable key identity and historical Candidate state. None, multiple, superseded-only or stale-grain active mappings hold; no Candidates are recreated.
- Keeps R1A MATCHED/HELD/NEW separate from Candidate discovery classification and review status. HELD and NEW rows cannot be promoted by newly positive evidence; queue/write eligibility stays false.
- Reuses V1.6 deterministic asset/qualified-indication matching and adds strict, cited regimen, line, population, setting, route/dose and company-role checks. Numeric prior-treatment conversion is never inferred.
- Requires official source-to-NCT proof, reciprocal trial/arm linkage and focal experimental arm/cohort evidence. Comparator, placebo, background/supportive drugs and separate experimental arms cannot positively leak into the focal regimen.
- Supports explicitly proven joint company views and multi-indication relationships without aliases or double-counting parent NCTs as independent sources.
- Emits immutable source references, Candidate identity, exact relation types and targets, official evidence URLs/dates, NCT/arm references, scope assertions/conflicts, independent authorities, reason codes, rule/comparator versions and batch ID. Output dispositions are SUPPORTED_EXACT, SUPPORTED_RELATIONSHIP_WITH_SCOPE_HOLD, HELD_AMBIGUOUS and NOT_YET_CORROBORATED.
- Separates NOT_ASSESSED, NO_MATCH, SCOPE_HELD and SUPPORTED evidence-family states. TL is a downstream consumer and is never counted as an independent evidence family.
- Checks reciprocal Candidate/Portfolio/TL/trial links, clinical scope and owner/competitor role. Missing direct TL links are coverage review only; automatic TL refresh, freshness and market availability remain unproven.

`test_r1c_shared_lineage.py` contains **synthetic** safety fixtures. These are not snapshots or clinical findings for Gilead. `r1c_regression.py` executes those tests and produces structured six-case outcomes that remain HOLD when real input is absent. `R1C_GILEAD_CASES.json` contains only framework-supplied names, NCTs and scope requirements—no invented keys or Airtable records.

## Actual executable results

| Check | Actual result |
|---|---|
| New synthetic safety suite | **43 tests passed; 0 failures, 0 errors, 0 skipped** |
| Synthetic replay | Identical validator output on rerun; input snapshot unchanged |
| Offline/route boundary | Validation passes with HTTP/socket calls blocked; existing route list unchanged |
| Existing comparator concurrency canary | PASS: event loop responsive, concurrent 503 and Retry-After, failure slot released |
| Existing staging-note preservation canary | PASS: notes/evidence/gates/scopes preserved; new synthetic candidate preparation; transient HTTP deferred |
| Existing V1.6 regressions after R1C import | PASS: Pfizer 58/58, Vertex expected classifications, four V1.6 identity checks |
| Missing-snapshot CLI | Expected exit **2**, BLOCKED, actual keys tested **0**, empty observed row matrix |
| Snapshot schema generation | Valid JSON schema emitted from the implementation |
| Positive synthetic snapshot CLI | PASS, exit 0, with and without required-case manifest; missing required-case mapping returns BLOCKED / exit 2 |

An end-to-end CLI check initially caught a typed-case/dictionary access error in the new draft. It was fixed and is covered by the CLI regression above.

The earlier direct import of `portfolio_discovery_regression_canaries_v16` failed with a pre-existing circular import (`astrazeneca_pipeline_adapter.AZPipelineRow` not initialized). The supported service-entrypoint import passes. That defect was not repaired or hidden by modifying existing code.

## Real six-case outcomes

| Case | NCTs from framework | Observed-data acceptance | Synthetic safety checks |
|---|---|---|---|
| iMMagine-1 | NCT05396885 | **HOLD** — source key, canonical target, population/line and arm snapshot absent | PASS: line mismatch; parent NCT without arm |
| iMMagine-3 | NCT06413498 | **HOLD** — protocol-backed prior-lines equivalence and separate programme proof absent | PASS: unproved prior-line conversion; population mismatch |
| ISLEND-1/2 | NCT06630286, NCT06630299 | **HOLD** — focal ISL/LEN arms and company-view mappings absent | PASS: comparator/placebo isolation; single-vs-combination |
| NAPISTAR 1-01 | NCT06303505 | **HOLD** — indication-specific TUB-040 and separate combination-arm records absent | PASS: indication mismatch; combination-arm leakage |
| PALISADES-1 | NCT04989803 | **HOLD** — explicit KITE-753 arm proof absent | PASS: separate-arm asset mismatch; mixed arms as combination |
| ARTISTRY-1/2 | NCT05502341, NCT06333808 | **HOLD** — focal regimen and dose/formulation/population evidence absent | PASS: comparator isolation; dose/route/population mismatch |

These PASS safety checks prove that deliberately unsafe **synthetic** inputs are rejected. They do not prove correct resolution, current record links or clinical scope for the actual six cases.

## Full 53-key reconciliation and downstream gaps

**BLOCKED — INPUT SNAPSHOT REQUIRED. Actual official Gilead keys tested: 0/53.** The complete source-key list and consistent Candidate/Portfolio/TL/Clinical Trials/arm/evidence snapshot do not exist locally. The blocked matrix deliberately contains no fabricated rows.

Historical R1A audit asserts 53 official source keys: 11 MATCHED / 16 HELD / 26 NEW / 0 unaccounted. Historical R1B asserts one active Candidate per current key, with 62 linked records and retained history. Those aggregates are preserved as expected baseline metadata, not independently rerun results. The exact current active/legacy record and key semantics need the row-level export.

Framework's historical TL baseline: 55 Portfolio records, 25 with links to 36 distinct TL records, 30 with no direct TL link; no blanket claim of 30 defects is made. The framework also reports no explicit arm/cohort children for the eight NCTs at its prior check. Neither historical statement is a current-instance readback.

Uncovered gaps: current source-to-Candidate uniqueness; source-backed canonical programme/indication scope; exact NCT/focal-arm proof; cross-company views and multi-indication mappings; reciprocal TL/Clinical Trials links; patient segment/line/owner-vs-competitor preservation; independent regulatory/Signal authority; evidence freshness, jurisdiction and actual downstream refresh. The code consumes reviewed scope/provenance assertions; it cannot establish protocol semantics, freshness or market availability from citation strings alone.

Source coverage, evidence coverage and confirmed master Portfolio coverage are reported separately when a valid snapshot is supplied. Candidate addressability cannot make Gate 3 pass. **Gate 3 and Gate 7 remain GAP; TL readiness remains UNPROVEN.** R2–R5 and the 39-company audit stay parked.

## Artifacts and next prerequisite

- `R1C_GILEAD_REGRESSION_RESULTS.json`: actual synthetic test results plus six real-case HOLD outcomes.
- `R1C_GILEAD_53_KEY_VALIDATION.json`: explicit BLOCKED result, 0 tested keys, no observed matrix.
- `R1C_SNAPSHOT_REQUIREMENTS.md`: exact table/field and evidence requirements, including supplied Airtable IDs and native Candidate field names verified in existing code.
- `R1C_SNAPSHOT_SCHEMA.json`: exhaustive normalized offline schema.

Supply a read-only export with these fields and independently sourced case mappings/oracles. No credentials are requested. Missing evidence must remain missing; do not fabricate normalized proof or create Airtable fields/records to satisfy the contract.

**Approval boundary:** the new shared resolver, evidence contract and company-view/scope projection rules are draft changes requiring review before any production integration. No change to the published caller is proposed in this batch. Stop before merging or deploying; actual R1C acceptance remains pending the input snapshot and six-case/full-denominator rerun.
