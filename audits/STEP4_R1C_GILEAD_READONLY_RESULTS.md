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


## 2026-10-09 — Real six-Candidate × 55-Portfolio V1.6 comparator preview

**OBSERVED RUN SUCCESS — NO PRODUCTION WRITES.** This section supersedes the old “actual Gilead comparator 0/53” statement for **only this bounded six-Case / 55-Portfolio preview**. Full 53-key end-to-end source/R1A/arm/persistence acceptance is still not performed.

Read-only inputs were retrieved from Airtable on 2026-10-09 and frozen on this recovery branch as [STEP4_R1C_GILEAD_COMPARATOR_OBSERVED_INPUT.json](STEP4_R1C_GILEAD_COMPARATOR_OBSERVED_INPUT.json): six current Candidate source rows, 55 distinct Gilead Portfolio records, six externally proposed programme targets, original keys/fields and explicit no-write guardrails. This snapshot is **not** all 53 Gilead source rows.

User ran the existing comparator in Codespaces with \`import service_entrypoint\` first (to avoid the documented pre-existing AstraZeneca module cycle), then \`portfolio_discovery_extension_v16\`, \`portfolio_discovery_extension_v11\`, and the existing R1C \`identity_preflight\`.

**Actual terminal result**: \`PREVIEW COMPLETE - NO PRODUCTION WRITES\`.

- Comparator: \`V1.6.0 PORTFOLIO DISCOVERY READ ONLY - DETERMINISTIC IDENTITY VARIANTS\`.
- V1.6 summary: \`MATCHED=0; NEW ASSET=6; NEW INDICATION=0; POSSIBLE DUPLICATE=0; OWNERSHIP REVIEW=0; EXCLUDED BY RULE=0; SOURCE UNAVAILABLE=0\`.
- **All six V1.6 rows** returned \`existingPortfolioRecordIds=[]\`.
- **All six R1C read-only asset preflights** found the pre-identified existing Portfolio target (\`Expected target identified: True\`). Each independently reports \`programmeIdentity=NOT_ASSESSED\`, \`autoLink=False\`, \`queueEligible=False\`, \`portfolioWriteEligible=False\`.

| Source programme | V1.6 observed | R1C asset identity candidate record IDs (NOT programme-approved) | Expected existing target |
|---|---|---|---|
| iMMagine-1 | NEW ASSET, [] | \`recSPdCh4UJgdQVGd\`; \`recJ6Gw3qoSQRi2x9\` | \`recSPdCh4UJgdQVGd\` |
| iMMagine-3 | NEW ASSET, [] | \`recSPdCh4UJgdQVGd\`; \`recJ6Gw3qoSQRi2x9\` | \`recJ6Gw3qoSQRi2x9\` |
| ISLEND-1/2 | NEW ASSET, [] | \`recOx6PWK0MJ4rJHy\` | \`recOx6PWK0MJ4rJHy\` |
| NAPISTAR 1-01 | NEW ASSET, [] | \`recTOUCjUJMUhVjuq\`; \`recD3oDxpTGvWbNSd\` | ovarian \`recTOUCjUJMUhVjuq\` |
| PALISADES-1 | NEW ASSET, [] | \`recBiCP8FUS5E4qBG\` | \`recBiCP8FUS5E4qBG\` |
| ARTISTRY-1/2 | NEW ASSET, [] | \`recnTXAC84OeTnZp0\` | \`recnTXAC84OeTnZp0\` |

**Root cause and bounded shared design:** V1.6 \`_match_methods\` compares mainly *same named identity fields* (asset↔asset, molecule↔molecule, developmentCode↔developmentCode). Real Sitecore Candidate names are decorated with programme/study labels, molecule fields are often absent, and existing Portfolio entries may store the same identity in another field. V1.6's limited parenthesis stripping fails this cross-field identity scenario. The independently implemented R1C exact cross-field whole-name, whole-regimen and development-code preflight demonstrates an existing asset representation, but cannot prove indication-specific programme identity. PALISADES has an upstream CD19 target-vs-KITE-753 code parsing problem; the recovery branch contains a generic extractor correction, not deployed.

**Proposed shared fix for review (not implemented or authorised for production):** integrate the existing R1C generic identity-preflight methods as an independent asset-presence assessment before programme disposition, report method/targets/hold reasons, and leave exact source-to-Portfolio link and classification promotion contingent on indication/line/population/focal-arm/owner/source-version proof and R1A holds. Do not collapse iMMagine line programmes or NAPISTAR ovarian/NSCLC indications, infer Merck programme ownership from Gilead-only comparisons, or treat combo-component overlap as entire regimen. Do **not** reclassify all six to \`MATCHED\`, \`NEW INDICATION\` or \`POSSIBLE DUPLICATE\` from identity presence alone.

**Next acceptance check:** bounded code proposal on this recovery branch using existing workers, and generic negative controls (same asset/different programme, ovarian vs NSCLC, monotherapy vs combination, placebo/comparator, biomarker vs development code, sponsor/company ownership). Then **separate explicit user approval** before deployment, Candidate edits, queue write, Portfolio link or master-data mutation. R1C remains production HOLD.


## 2026-10-09 — Shared asset-presence regression validation (actual Codespaces result)

**PASS: 73 of 73 tests; 0 failures; 0 errors.** User ran
\`git pull --ff-only && .venv/bin/python -m unittest -v test_r1c_shared_lineage\`
in their existing Codespaces Python 3.11 environment on the recovery branch. The
terminal screenshot displayed \`Ran 73 tests in 5.952s\` and \`OK\`.
A non-fatal \`DeprecationWarning\` about \`swigvarlink\` followed the test result.

Recovery branch implementation at \`bf0763c5f2cc2f79452a463b7da93c27bfd08555\` changes only
\`r1c_shared_lineage.py\` and \`test_r1c_shared_lineage.py\`.
The new read-only \`assess_asset_presence\` contract remains separate from
V1.6's unmodified programme comparator. It can identify exact whole names,
whole regimens or verified development-code identities across fields and flag
an original \`NEW ASSET\` classification for re-assessment. It returns candidate
identity IDs and evidence strength, but \`programmeIdentity=NOT_ASSESSED\`,
\`canonicalPortfolioMatch=null\`, \`proposedDiscoveryClassification=null\`,
\`autoLink=False\`, queue/write eligibility false and \`masterWrites=0\`.

15 newly added tests cover existing Gilead 6×55 snapshot asset-preflight
presence, comparator output preservation, same molecule/different programmes,
indication separation, whole combinations versus monotherapy, target biomarkers
versus development codes, exact code versus display-only weak evidence,
cross-company exclusion, missing company, duplicate record IDs and other
fail-closed cases. They build on 58 prior regression methods.

**Scope of PASS:** code-level regression safety and frozen observed-data
asset-presence assertions only. These tests do **not** prove that the live
production comparator now classifies any Candidate differently; V1.6 is
intentionally unchanged and still returned 6 × \`NEW ASSET\` in the prior
live-data read-only preview. They do not validate 53/53 official source keys,
persisted Candidate→Portfolio links, all 39-company fixtures, business report
release gates or end-to-end scheduled refreshes. All six Gilead programme links
remain on R1C HOLD, with no production Airtable changes, automation changes,
merges or deployment.

**Next controlled step:** trace the existing Source Watch → Adapter Registry →
shared comparator → Candidate staging boundaries and the current publication
guardrails; prepare one explicit read-only integration and impact proposal
without adding a new automation or overriding held historical dispositions.
Require user approval before any production deployment, Candidate edits,
Portfolio master writes, queues or automatic links.


## 2026-10-09 — Production architecture trace and integration decision (READ ONLY)

**Decision: PROPOSED SHARED INTEGRATION; NO PRODUCTION IMPLEMENTATION OR DEPLOYMENT APPROVED.** This trace uses the live Airtable automation draft/published-version inventory and existing code on the R1C recovery branch. It is not an instruction to activate an automation.

### Actual existing source → adapter → comparator → Candidate paths

| Layer | Live observed state | Integration significance |
|---|---|---|
| Source Watch \`GILD-SW-003\` (\`recCyELG6w7TZKwQZ\`) | Monitoring **Active**, Pipeline Adapter **Validated**, Adapter Binding **Validated**, baseline **Established**; 53 official source rows in historical adapter run; current notes record a monitoring reconciliation HOLD on 2026-10-09 | Do not reset baseline or infer current programme acceptance from historical source counts |
| Adapter Registry \`PIPELINE_SITECORE_SXA_JSON_V1\` (\`recOUVw7W4ekRsYxV\`) | Profile **Validated**, linked to GILD-SW-003 | Preserve existing Source Watch/Adapter Registry binding; current Sitecore source \`CD19\`→\`KITE-753\` parser improvement remains on recovery branch only |
| Python service \`portfolio_discovery_extension_v11.py\` + \`portfolio_discovery_extension_v16.py\` | Existing read-only authenticated endpoint \`POST /compare/portfolio-discovery\`; V1.6 patches existing comparator, but matching primarily intersects same-type identity fields | **Preferred optional diagnostic integration seam**: extend the existing V1.6 output with R1C \`assess_asset_presence\` metadata only. Do not change legacy \`classification\`, \`existingPortfolioRecordIds\`, \`matchConfidence\`, \`commercialInclusionDecision\` or write flags |
| \`Portfolio Discovery Staging V4\` Airtable automation \`wflzjmH2akEgSyL6s\` | **OFF**; draft V4.4.8 calls the existing read-only comparator, then uses a simplistic same-field identity collision guard; currently changes some \`NEW ASSET\` to \`POSSIBLE DUPLICATE\`, and would \`createRecordsAsync/updateRecordsAsync\` for Candidates if run | NOT safe to turn ON merely to see results. Candidate writes would occur; existing programme gate/human-reviewed controls must be preserved. Its Find Records filter excludes \`Pipeline Baseline Status=Established\`, so **Gilead would not be selected even if activated** |
| \`Portfolio Discovery Worker V1\` \`wflWzZBSZDlaGYGpL\`, source-driven staging alternatives | **OFF**; has Candidate write paths and semantic holds | No secondary workflow activation; decide a single existing Candidate staging route before authorised writes |
| \`Pipeline Source Watch - Recurring\` \`wfl4harJ5tbxHZxMW\` | **ON**; **published script V2.61.2** executes the pipeline delta/queue router and can write Intelligence Update Queue and Source Watch metadata; editable **draft script V2.61.3** has different read-only canary code and is NOT published | DO NOT publish the draft, alter current source routing, treat its read-only text as the deployed behavior, or embed the new asset preflight into the active queue router as an ad hoc fix. Live monitor does not constitute an approved Candidate refresh |
| \`Portfolio Controlled Promotion Writer V1\` \`wflCf0nUMilBEdL8C\` | **ON**; draft V1.9.12 described as preview by default with explicit live-write allowlisting; writer contains real Portfolio and Candidate write paths | Do not trigger or change eligibility/gates, permit source baseline reset, or rely on a banner alone for write safety. Any change must independently assert zero Portfolio writes |
| Candidate table \`Portfolio Discovery Candidates\` | Existing fields include \`Discovery Classification\`, \`Latest Staging Evidence\`, \`Programme Reconciliation Gate\`, \`Next Verification Gate\`, \`Programme Review Next Action\`, \`Existing Portfolio Match\`, \`Review Status\`, \`Discovery Candidate ID\` | A reviewable identity-versus-programme distinction can be displayed using **existing fields** after a separately approved Candidate-only operation; no new field or automation needed |

Source Watch current data is not evidence of a successful end-to-end product refresh. Draft/published distinction and time-of-observation must accompany any deployment plan.

### Minimal, gated shared integration proposal

1. **Recovery-branch code proposal (read-only, no operational side effects):** Integrate the already-tested generic \`assess_asset_presence\` output into the *existing authenticated comparator response* as an **additive optional per-Candidate diagnostic**, after the unchanged V1.6 comparison. Keep source company scoped and include exact versus review-only code-in-display strength; \`originalDiscoveryClassification\`, \`classificationReview\`, \`assetExistenceAssessment\`, \`candidatePortfolioIdentities\`, \`programmeIdentity=NOT_ASSESSED\` and all no-write controls must be preserved. The 73 regression tests already cover the independent function, **not** this unimplemented API composition.
2. **Offline output contract regression:** Verify unchanged comparator summary, JSON response validation, caller compatibility, whole-regimen and partner/indication/line negative controls, count/parity and latency/concurrency. Run the six observed Gilead Candidates against **55 actual existing Portfolio rows**, then all **53 active official source stable keys** if independently reconstructed, plus selected other-company canaries with same molecule/different indication, no assets, new assets and co-development. Do NOT claim 39-company validation from six cases.
3. **Separate Candidate-only controlled change proposal:** If the read-only output passes, review exactly how the existing Staging V4 maps optional diagnostics into \`Latest Staging Evidence\` and keeps \`Programme Reconciliation Gate = Evidence Captured – Scope Unresolved\`, while preserving current \`Discovery Classification\` as the original comparator result and existing reviewer decisions. Its current simplistic guard **must not silently convert an identity hit into \`POSSIBLE DUPLICATE\` or \`MATCHED\`**. A source with \`Established\` baseline requires a **bounded, deliberately authorised same-source replay** rather than changing the production baseline or enabling the recurring schedule. Do not turn on Staging V4 or any alternate staging/worker automation until this path is verified and separately approved.
4. **Authority and safety boundary:** Identity evidence alone never edits \`Existing Portfolio Match\`, Portfolio master rows, \`Cross-source Status\`, Evidence Families, Intelligence Update Queue or Pipeline Baseline Status. Preserve R1A held/new disposition, stable source keys, existing relation/review notes and original source version. All uncertain programme/indication/arm/company-role links remain HOLD. Any Candidate-only write must be an explicit approval decision and re-read exact records after application.
5. **Rollback and monitoring:** Before any approved live Candidate-only change, save all affected record IDs and pre-change field values, preserve original V1.6 results, recovery/base commits and adapter profile/version. Roll back by reverting only the approved comparator/staging change and restoring only the authorised Candidate fields where version/record checks permit; never use a blanket Portfolio update. Compare before/after counts, Source Watch changes and queue deltas. Stop on source mismatch, unexpected new Candidate, programme promotion, queue write or Portfolio master write. Restore original automation state/schedule unchanged.

### Acceptance and current status

The user-observed 73/73 passing R1C suite establishes a safe standalone **read-only asset-presence function**. The existing six×55 comparator preview establishes a live-data **identity false-negative** (\`V1.6: 6 NEW ASSET\`, \`R1C asset preflight: 6 known target IDs found\`). **Neither validates the unimplemented endpoint integration, actual Candidate persistence, full Gilead 53/53 reconciliation nor customer-report release**.

The next work item is a **single bounded additive comparator-output integration and test** on this existing recovery branch, not another source/clinical trial investigation or Airtable automation. Any production deployment or Candidate data edits require explicit user approval. R1C remains production HOLD.


## 2026-10-09 — Optional read-only asset-presence comparator response integrated (RECOVERY BRANCH ONLY)

**STATUS: CODE COMMITTED; NEW REGRESSION RUN PENDING. NO PRODUCTION DEPLOYMENT.**

Recovery branch commit: \`3d2517bdf9c8bd2470662f11f48b491bd21edcad\`. Files changed: \`portfolio_discovery_extension_v11.py\`, \`portfolio_discovery_extension_v16.py\` and \`test_r1c_shared_lineage.py\`. The existing R1C generic resolver, Source Watch, Adapter Registry, Airtable automations and production Portfolio data were **not changed**.

- The current authenticated \`POST /compare/portfolio-discovery\` request adds optional \`includeAssetPresence: bool = False\`. **Default is False; all existing clients retain the existing response**, classification, match targets and summary.
- With explicit \`includeAssetPresence: true\`, existing V1.6 classification executes **first and unmodified**. Only rows with original classification \`NEW ASSET\` receive a nested \`assetPresence\` diagnostic computed by the already-tested shared \`assess_asset_presence\` function. Excluded, unavailable, ownership-held and already-matched rows receive no diagnostic.
- The nested result can report exact whole name, whole regimen, development-code cross-field identity and weaker code-in-display review. It **never** changes \`classification\`, \`existingPortfolioRecordIds\`, \`matchMethod\`, \`matchConfidence\`, \`matchEvidence\`, \`fieldDeltas\`, \`reviewReason\` or \`summary\`. The nested \`programmeIdentity\` is always \`NOT_ASSESSED\`; \`canonicalPortfolioMatch\` and \`proposedDiscoveryClassification\` remain \`null\`; \`autoLink\`, Candidate writes, Queue and Portfolio writes remain false.
- Company ownership and mismatched route scopes fail closed; unknown Portfolio company attribution does not become a match. Duplicate in-scope Portfolio record IDs fail closed, not arbitrarily choose a first target. Output remains read-only; this code adds no route, automation, trigger, external network fetch, record update or queue mutation.
- Existing V1.7.2 shadow script is **OFF** and has hard-coded Regeneron/AstraZeneca diagnostics. Its tiered review intent is compatible with keeping selected matches separate from alternative/held possible identities. It has not been copied or activated.

**Regression status:** seven new tests added to the existing safety suite (73 previously passing + 8 new = **81 test methods**, subject to actual unittest discovery). New tests cover default response parity, opt-in 6 real Gilead Candidates versus 55 Portfolio rows, original comparator-field parity, already-MATCHED programme preservation, excluded/unavailable no-overlay, source/company mismatch ownership hold, foreign Portfolio exclusion and duplicate Portfolio IDs. **Do not claim 81/81 PASS until a Codespaces run actually confirms it.** The previously observed 73/73 PASS pertains to the standalone function, not this newly committed API integration.

**Bounded next gate:** Run once in the existing Codespaces environment:
\`git pull --ff-only && .venv/bin/python -m unittest -v test_r1c_shared_lineage\`.
Record exact output, fix any fail-closed regression on the recovery branch only. Then decide whether to run additional **read-only** cross-company API contract canaries or require fuller source snapshots. Do not activate the OFF Candidate staging automations, switch Gilead from Established baseline, merge, deploy, or write Candidate/Portfolio/master data without separate explicit approval. Full 53/53 Gilead source-key and commercial release gates remain unproven.
