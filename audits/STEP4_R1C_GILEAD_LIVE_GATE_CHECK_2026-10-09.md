# Step 4 / R1C — Gilead live Airtable read-only gate check (2026-10-09)

**Gate decision: R1C BLOCKED (programme-scope evidence unproven); Golden Company Gate 3 GAP; Gate 7 GAP.** Preserve R1A/R1B pass and synthetic regression results; neither is a customer-facing production PASS.

## Scope and observed live facts
Base appzteNR0u0ywm9Zz; Gilead Company rec60nNJ7EvlHlt0v; official pipeline watch GILD-SW-003 / recCyELG6w7TZKwQZ. Read-only Airtable record-level fetch. No official-source extraction or independently current pipeline denominator rerun. Existing source watch says adapter Validated, binding Validated, baseline Established, monitoring Active, Last Checked 2026-10-02.

- Candidate table: 62 linked records; 55 not Superseded = 53 with nonempty official source-key field + **2 keyless older legacy**. 7 Superseded preserved.
- Within the 53 active keyed Candidates: 53 distinct keys, no duplicate active keyed identities. Across all Candidates, 53 distinct keyed values; seven groups retain historical identity overlap.
- 62 Candidate relationships to the expected Company/Source Watch inspected: zero mislinks. 13/62 Candidate records have at least one Portfolio match; all six focal R1C programme Candidates have **zero direct Portfolio links**.
- Candidate review statuses: 9 Resolved, 30 New, 16 Needs Review, 7 Superseded; classifications across all linked rows 31 NEW ASSET, 5 NEW INDICATION, 2 NEW PROGRAM, 24 EXCLUDED BY RULE. Note R1A disposition is a distinct 11 MATCHED / 16 HELD / 26 NEW baseline, not derivable from those Candidate classifications.
- Portfolio: 55 linked records; 13 have at least one linked Clinical Trial and 25 have at least one linked Treatment Landscape record. All 55 have empty *Cross-source Status* and *Evidence Families* fields; 48/55 have a Last Verified value (not proof of fresh-source success).
- Company linked Clinical Trials: 16 records. All eight NCTs specified in the framework's six cases are present and have linked Portfolio record(s): NCT05396885, NCT06413498, NCT06630286, NCT06630299, NCT06303505, NCT04989803, NCT05502341, NCT06333808.
- **0/8** required trial records have explicit linked *Clinical Trial Arms & Cohorts* children. Gilead Company has 0 directly linked Arms & Cohorts; separate CT.gov Arm Evidence table contains 15 records overall but 0 for these eight NCTs.
- Six-case dispositions remain **HOLD**: iMMagine-1, iMMagine-3, ISLEND-1/2, NAPISTAR 1-01, PALISADES-1, ARTISTRY-1/2. Parent NCT or asset names alone cannot prove exact programme, focal arm, population/line, combination or cross-company scope.
- Source Watch Source Snapshot Imports link is blank (no linked official snapshot import). Full current official 53-row source extraction is not verified by this direct read. Thus the 53 keyed Candidate identities cannot be described as independently current official-source completeness.

## Interpretation and bounded next action
R1B *Candidate stable-key uniqueness* independently reconfirmed, but R1C programme cross-source proof is **BLOCKED** by (a) missing independent current official-source row snapshot/disposition inputs, (b) unverified focal trial-arm/cohort relationships for all eight test NCTs, (c) unresolved Candidate-to-Portfolio programme link scope, and (d) empty master Cross-source Status/Evidence Families.

Do **not** turn ON or run Worker V1.15, modify Candidate/Portfolio/Queue/Source Watch records, infer missing clinical-arm semantics from a parent NCT, or create custom Gilead automation. The existing synthetic 81/81 test success remains a *code safety* result, not a production acceptance.

Park new Amgen/GSK Candidate upsert work and wider company audits. Next decision is whether existing approved source/arm evidence can satisfy these narrow R1C prerequisites in a bounded read-only pass; if not, keep BLOCKED and request a targeted evidence capture, without reopening every individual clinical study. Re-test original Golden Company Gates 3/7 only after meaningful new evidence. No company is thereby release approved.
