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


---

## 2026-10-09 — LIVE six-case evidence reconciliation checkpoint (read-only)

**Status: 58 synthetic regression methods passed in the user's Python 3.11 Codespace (terminal: `Ran 58 tests in 6.572s; OK`). GitHub recovery branch at checkpoint was `746041055a7718ed44a639b20afe65ae69c9b6a4`. The local `git rev-parse HEAD` output was not visible in the submitted terminal screenshot. Six real programme acceptance cases remain HOLD, and no validation output has been backfilled or fabricated.** This dated update supersedes the outdated 43-test summary *for the regression count only*; prior results remain historical.

### Existing shared architecture and current source evidence

- Source Watch `GILD-SW-003`, Gilead Pipeline, was Active/Established, linked to Adapter Registry profile `PIPELINE_SITECORE_SXA_JSON_V1` (Validated). Its Last Checked field was 2026-10-02 and Next Check 2026-10-09 when inspected. The official adapter's historical validation found 53 structurally complete pipeline programme rows (out of 56 results); this checkpoint does not assert a new official extraction.
- The deployed weekly `Clinical Trials - CT.gov` script fills the Clinical Trials field `CT.gov Arm / Cohort Raw` with registry descriptions. Its source-facing raw arms must not be mistaken for separately verified focal arm/cohort relationships. The existing read-only arm-evidence and cohort audit workflows were scoped to Regeneron/ORCHARD/PALISADE canaries and were OFF for the Gilead use case. No workflow was turned on, revised or cloned.
- All six Gilead Candidates below were independently re-read live from Airtable as `NEW ASSET` / `No Match` with an empty `Existing Portfolio Match`. All eight existing Portfolio views have no linked Candidate, despite the six plausible source asset identities. Eight existing parent Clinical Trial records include raw registry arm descriptions. Eleven observed Portfolio-to-parent-Trial link edges are reciprocal across eight distinct NCTs, and all eight Portfolio-to-Treatment Landscape links were reciprocal. This **does not prove** exact programme scope or current live registry freshness.
- A structured Airtable *exact equality filter* over all eight NCTs in both `Clinical Trial Arms & Cohorts` and `CT.gov Arm Evidence` returned zero persisted records; all eight parent Clinical Trial records have empty structured arm links. This identifies the bounded evidence-persistence gap. No claim is made that the official registry itself lacks arm information.
- The shared offline `r1c_shared_lineage.py` and R1C source-to-arm proof requirements remain fail-closed: Candidate fields had no explicit official trial identifiers, so a source Candidate/asset + linked parent NCT cannot alone certify source-to-NCT provenance, focal intervention, treatment line, population, route/dose or partner role. Source `NEW ASSET` is discovery classification, not the independent R1A historical disposition; no promotion based on it is authorised.

### Six-case ledger — verified observations versus programme HOLDS

| Candidate / official asset | Proposed pre-existing Portfolio target(s) | Parent trial evidence already captured in Clinical Trials | Specific gate still HOLD |
|---|---|---|---|
| iMMagine-1 `recOGc2QkKjGiXhk8` / anitocabtagene autoleucel | Gilead `recSPdCh4UJgdQVGd` (4th-line-or-later anito-cel) | `NCT05396885` / `recx96KA6Jft71emY`; explicitly labelled experimental anito-cel arm; reciprocal parent link | Source `4L+` vs TL `3L+` display semantics; canonical regimen and 3-prior-lines equivalence require official scope proof; no independently persisted focal arm or explicit Candidate-to-NCT provenance |
| iMMagine-3 `recLd0O4DDoSUICO0` / anitocabtagene autoleucel | Gilead `recJ6Gw3qoSQRi2x9` (after 1–3 prior lines) | `NCT06413498` / `recTRPQ0vfEJ8NAem`; distinct experimental anito-cel versus standard-of-care comparator | Source `2–4L` cannot automatically be converted into after 1–3 prior lines. Require trial eligibility/protocol proof; focal arm and source-to-NCT lineage not persisted |
| ISLEND-1/2 `recUaxfv5urojBewZ` / islatravir-lenacapavir oral combination | Gilead `recOx6PWK0MJ4rJHy`; joint partner view Merck `recAMZGRRM6BC0Haq` retained distinctly | `NCT06630286` / `recpNXLBUqLwrYYlC` and `NCT06630299` / `recThSREvqOGeZ6q2`; raw registry includes focal ISL/LEN arms plus placebo-to-match or standard-care regimens | Preserve regimen/competing arms and once-weekly scope, independently prove shared-study Gilead/Merck roles, no duplicate development programme count; focal arms and official source-to-NCT links not persisted |
| NAPISTAR 1-01 `recj50kAokdSo6REw` / GS-8824 (TUB-040) | Gilead ovarian `recTOUCjUJMUhVjuq`; distinct NSCLC `recD3oDxpTGvWbNSd` is a separate indication projection, **not** automatically linked to ovarian source card | `NCT06303505` / `recpt1qoZl3N4rQz4`; parent raw descriptions separate platinum-resistant ovarian, NSCLC and ovarian+bevacizumab arms | Source Phase 2 vs parent/Portfolio Phase 1/2 are different scopes, not automatic field delta. Need evidence-backed ovarian focal arm, combination separation and company/licensing-role proof. Existing Intelligence Update Queue `recToOGN4tq92ENqa` recognises ovarian Portfolio target yet remains Needs Review; Candidate is still No Match |
| PALISADES-1 `recfWkIVpdJboItRp` / KITE-753 | Gilead `recBiCP8FUS5E4qBG` | `NCT04989803` / `recJbBenSNuduKnCE`; saved raw explicitly separates KITE-363 Phase 1 arms, KITE-753 Phase 1 and Phase 2 arms | Actual Candidate development-code field incorrectly reads `CD19` (biomarker). Generic read-only branch parser correction recovers `KITE-753` but is **not deployed**. Focal KITE-753 Phase 2 and `3L+` versus TL `2L` source-scope proof required; no cross-arm blending |
| ARTISTRY-1/2 `rectOd70xCzPWfkls` / bictegravir-lenacapavir | Gilead `recnTXAC84OeTnZp0` / BIXLENVO | `NCT05502341` / `recxfNKfbvQrwrp0v`; `NCT06333808` / `rec9DIxpxiG0pCaIE`; raw trial arms distinguish BIC/LEN dose/formulation and B/F/TAF, placebo or stable-baseline comparators | Source Candidate `Filed / Registration` and Portfolio `Approved` represent differing authority/as-of scopes; **do not overwrite either automatically**. Earlier primary-authority review found US FDA BIXLENVO NDA 221104 approval letter dated 2026-08-27 and label at `https://www.accessdata.fda.gov/drugsatfda_docs/appletter/2026/221104Orig1s000ltr.pdf` and `https://www.accessdata.fda.gov/drugsatfda_docs/label/2026/221104Orig1s000lbl.pdf`. Approval is US-jurisdiction only; local regulatory coverage and exact clinical formulation/arm links still require controlled review |

### Next gate; no new feature or automation

1. Preserve these verified asset/source facts in read-only output even when programme edges are held. Do not relabel six existing `NEW ASSET` Candidates as confirmed new products; do not auto-write links.
2. Reuse the existing read-only shared resolver with the **actual source-row original provenance / source-to-NCT proof** and **existing official saved CT.gov arm evidence**, rather than fabricating `Arm` records. For each exact candidate/target/NCT, require independent source scope, experimental arm, regimen, indication, line/population, company role and official version/date before `SUPPORTED_EXACT`. The existing Candidate → Portfolio link being absent remains a separate persistence hold even if identity proof is established.
3. No full 53-key R1C PASS can be claimed until full source-row/R1A keyed snapshot and its linked-record closure are supplied and validated by the current contract. The six-case ledger is a bounded acceptance preflight, **not** a substitute or test rerun.
4. No merge, deployment, workflow trigger, master update, Candidate edit, clinical-arm/cohort creation or Portfolio linkage is approved. If production changes are ever proposed, ask the user first.
