# Step 4 — Cross-company source-to-Candidate production readiness matrix (2026-10-09)

**Mode: LIVE AIRTABLE SCHEMA/RECORD READ-ONLY + EXISTING AUTOMATION SOURCE INSPECTION. No writes, deployment or activation.**

Scope: Airtable base `appzteNR0u0ywm9Zz`; 39 Companies, all 350 Source Watch records, all 33 Adapter Registry profiles; select 43 pipeline-related Source Watch records (by Source Type or Source Name containing “pipeline”). Snapshot obtained 9 October 2026. Counts represent **links/configuration**, not independently verified asset data accuracy, official-source freshness or successfully executed end-to-end refresh.

## Decision / outcomes

1. All **39 of 39** current Companies have `Customer Intelligence Release Gate = Blocked`. This reflects multiple product-coverage readiness gates; it cannot be attributed solely to Portfolio reconciliation. No customer-facing full-release PASS.
2. Among **43 pipeline-related** Source Watch records: pipeline adapter statuses **Review Required: 17; Validated: 25; Pending Validation: 1**; adapter bindings **Needs Review: 19; Validated: 23; Failed: 1**; baseline **Needs Review: 10; Not Established: 10; Established: 13; (blank): 10**; monitoring **Active: 34; Needs Review: 5; Retired: 2; Paused: 2**. All 43 link an Adapter Registry profile, but a linked profile does **not** mean validated.
3. **10 of 43** pipeline-related Source Watches have zero directly linked Discovery Candidates. This does not prove no official rows or no alternative-source fallback.
4. Company-linked Portfolio count is zero for **Chiesi (0 Candidates)** and **Ultragenyx Pharmaceutical (7 Candidates)**. Ultragenyx Candidate rows may originate via CT.gov fallback, not its primary Pipeline Source Watch. Avoid treating fallback rows as automatically equivalent to official company-pipeline programme confirmation.
5. **Candidate identity existence and programme readiness must remain independent.** The new optional `includeAssetPresence` comparator diagnostic is validated in recovery branch (81/81 tests); it is not deployed, and current automation requests do not opt in.

## Existing workflow choice, with explicit constraints

| Existing workflow | State | Real observed contract | Decision |
|---|---|---|---|
| `Portfolio Discovery Worker V1` (`wflWzZBSZDlaGYGpL`), draft script VERSION `PORTFOLIO_DISCOVERY_WORKER_V1.15_STRUCTURED_RECONCILIATION_STATES` | OFF / undeployed | Queue triggered. Requires Pipeline Page + adapter/binding Validated; accepts source baseline blank, Not Established, Needs Review, **Established**. Calls existing `/compare/portfolio-discovery` in batches of 24. Has Candidate create/update paths and Queue + Source Watch metadata writes; preserves reviewed statuses, human notes and some programme gates. | **Preferred existing path for a future controlled cross-company staging design, NOT approval to activate**. Must produce independent no-write preview first, compare exact fields against human holds and prove queue/date metadata will not mutate on preview. |
| `Portfolio Discovery Staging V4` (`wflzjmH2akEgSyL6s`), draft V4.4.8 | OFF / undeployed | Source Watch-driven cron; only blank, Not Established or Needs Review baseline; would reject Established sources. Candidate create/update and Source Watch metadata writes. | Not universal; do not switch ON or force Established→Needs Review to work around eligibility. Preserve until dependency review. |
| `Portfolio Cross-Source Fallback Staging Writer V1.0` (`wflBqDijJHpL8xYdF`) | OFF / undeployed | CT.gov fallback and Candidate writes, different source authority and grain; not interchangeable with validated primary pipeline route. | Keep as separate fallback capability; do not combine source authorities or activate automatically. |
| `Pipeline Source Watch - Recurring` (`wfl4harJ5tbxHZxMW`) | ON (published V2.61.2; draft V2.61.3 differs) | Source monitoring / delta and queue routing, **not** same as Candidate staging worker. | Leave unchanged. |

**Production staging go/no-go:** Gate 1 exact Source Watch↔Adapter Registry validation and approved source grain. Gate 2 official source retrieval and stable key completeness / all-batch parity. Gate 3 comparator default-contract parity + opt-in read-only asset identity, no false programme matches. Gate 4 Candidate upsert preflight of every proposed field, preserving existing stable Candidate ID, class/holds, human review, and active/historical Candidate selection. Gate 5 no duplicate current records, zero Portfolio masters, zero queues and zero Source Watch metadata writes during preview. Gate 6 explicit user approval of controlled Candidate-only changes and captured before-values / revert. Missing inputs FAIL CLOSED.

**Cross-company validation cohorts (NOT a claim tests were run):** Amgen — Validated/Validated/Established with Candidates and Portfolio; GSK — Validated/Validated/Needs Review with Candidates; Pfizer — Validated adapter but binding Needs Review / Not Established and zero Candidates (must hold); Chiesi — Review Required/Needs Review / Not Established and zero Portfolio/Candidates (must hold). These represent different architecture paths, not company-specific code branches. Ionis/Gilead retention holds remain separately protected. Use a bounded cross-company read-only fixture; do not require another Gilead deep dive.

## Company-level Airtable linkage inventory

| Company | Linked Portfolio rows | Linked Discovery Candidates | Linked Source Watch | Customer Release |
|---|---:|---:|---:|---|
| UCB | 18 | 17 | 5 | Blocked |
| Daiichi Sankyo | 16 | 2 | 5 | Blocked |
| Teva | 21 | 34 | 9 | Blocked |
| Regeneron Pharmaceuticals | 70 | 82 | 9 | Blocked |
| Gilead Sciences | 55 | 62 | 9 | Blocked |
| argenx SE | 15 | 16 | 4 | Blocked |
| Pfizer | 395 | 0 | 10 | Blocked |
| AstraZeneca | 240 | 353 | 6 | Blocked |
| Chiesi | 0 | 0 | 5 | Blocked |
| Roche | 111 | 65 | 4 | Blocked |
| Merck KGaA | 30 | 8 | 5 | Blocked |
| Menarini Group | 27 | 18 | 10 | Blocked |
| Johnson & Johnson | 84 | 70 | 9 | Blocked |
| Sanofi | 111 | 0 | 6 | Blocked |
| Vertex Pharmaceuticals | 19 | 9 | 6 | Blocked |
| Biogen | 26 | 20 | 6 | Blocked |
| BioNTech SE | 37 | 55 | 3 | Blocked |
| GSK | 59 | 53 | 5 | Blocked |
| Alnylam Pharmaceuticals | 41 | 0 | 4 | Blocked |
| Bayer | 35 | 11 | 8 | Blocked |
| Boehringer Ingelheim | 36 | 0 | 4 | Blocked |
| AbbVie | 63 | 22 | 9 | Blocked |
| Viatris | 21 | 0 | 9 | Blocked |
| Arrowhead Pharmaceuticals | 23 | 27 | 4 | Blocked |
| Takeda | 30 | 54 | 9 | Blocked |
| Novartis | 92 | 14 | 6 | Blocked |
| Sobi | 11 | 12 | 7 | Blocked |
| Dyne Therapeutics | 3 | 8 | 3 | Blocked |
| Astellas | 40 | 0 | 4 | Blocked |
| Wave Life Sciences | 5 | 10 | 3 | Blocked |
| Amgen | 60 | 51 | 9 | Blocked |
| Ionis Pharmaceuticals | 36 | 33 | 4 | Blocked |
| Recordati | 15 | 5 | 9 | Blocked |
| Verve Therapeutics | 5 | 2 | 3 | Blocked |
| Bristol Myers Squibb | 139 | 70 | 4 | Blocked |
| Ultragenyx Pharmaceutical | 0 | 7 | 7 | Blocked |
| Merck & Co. (MSD) | 70 | 14 | 9 | Blocked |
| Eli Lilly and Company | 93 | 95 | 5 | Blocked |
| Novo Nordisk | 33 | 3 | 9 | Blocked |

## Pipeline Source Watch inventory (43 rows)

| Company | Source Watch | Source | Adapter | Binding | Baseline | Candidate links | Last checked | Next check |
|---|---|---|---|---|---|---:|---|---|
| Menarini Group | `rec30WpNaPR8P2T31` | Stemline Oncology Pipeline | Review Required | Needs Review | Needs Review | 0 | 2026-08-26 | 2026-09-22 |
| AbbVie | `recBltwHhp2OyFs7O` | AbbVie Pipeline | Review Required | Needs Review | Needs Review | 22 | 2026-08-26 | 2026-09-22 |
| Pfizer | `recCCbwHiMqYzb3Mv` | Pfizer Drug Product Pipeline | Validated | Needs Review | Not Established | 0 | 2026-09-21 | 2026-09-28 |
| Gilead Sciences | `recCyELG6w7TZKwQZ` | Gilead Pipeline | Validated | Validated | Established | 62 | 2026-10-02 | 2026-10-09 |
| Novartis | `recCzXWgPfrLb3Auo` | Novartis Pipeline | Review Required | Needs Review | Not Established | 14 | 2026-08-25 | 2026-09-22 |
| Chiesi | `recEwVZeLX9Ao6mpf` | Chiesi Pipeline | Review Required | Needs Review | Not Established | 0 | — | — |
| Sanofi | `recF7MIL6YDPiuEGf` | Sanofi R&D Pipeline | Validated | Needs Review | Not Established | 0 | 2026-09-21 | 2026-09-28 |
| Amgen | `recFN86shiy1jOjow` | Amgen Pipeline | Validated | Validated | Established | 51 | 2026-10-03 | 2026-10-10 |
| Sobi | `recIxr1Li8RD0Jj31` | Sobi Pipeline | Validated | Validated | Established | 12 | 2026-10-03 | 2026-10-10 |
| Ultragenyx Pharmaceutical | `recKISbnSzaXbfenW` | Ultragenyx Pipeline | Review Required | Needs Review | Not Established | 0 | — | — |
| Ionis Pharmaceuticals | `recKiirjduvPu4pOe` | Ionis Pharmaceuticals — Pipeline | Validated | Validated | Established | 33 | 2026-09-25 | 2026-10-02 |
| Viatris | `recOWqONHi2YBj7xb` | Viatris Science / Innovative Pipeline | Review Required | Needs Review | Not Established | 0 | 2026-08-26 | 2026-09-22 |
| Johnson & Johnson | `recTGKParWvCXJuJM` | Johnson & Johnson 2026 Key Pipeline Events | Pending Validation | Failed | — | 0 | 2026-08-26 | 2026-09-02 |
| Verve Therapeutics | `recTTAiNfquZnXeC8` | Verve Therapeutics — Pipeline | Review Required | Needs Review | — | 2 | 2026-09-21 | — |
| GSK | `recU55utom8eVniqE` | GSK Pipeline | Validated | Validated | Needs Review | 53 | 2026-10-05 | 2026-10-12 |
| Biogen | `recUTvVgBEZCXGv2B` | Biogen Pipeline | Validated | Validated | Established | 20 | 2026-10-07 | 2026-10-14 |
| Johnson & Johnson | `recUaq5w669zo4Uyi` | Johnson & Johnson Development Pipeline | Validated | Validated | Not Established | 70 | 2026-09-21 | 2026-09-28 |
| Vertex Pharmaceuticals | `recXkXnavs5J3wUj9` | Vertex R&D Pipeline Snapshot — 2026-09-21 | Validated | Validated | — | 3 | 2026-09-21 | — |
| Astellas | `recY1nk7LGfgzatTs` | Astellas Product Pipeline | Validated | Needs Review | Not Established | 0 | 2026-08-25 | 2026-09-22 |
| Merck KGaA | `recbA1hFdzDrPgtyq` | Merck KGaA Healthcare R&D Pipeline | Validated | Validated | Established | 3 | 2026-10-03 | 2026-10-10 |
| UCB | `recbixdEl6Vd5K3D0` | UCB Pipeline | Validated | Validated | Needs Review | 17 | 2026-10-01 | 2026-10-03 |
| Menarini Group | `recbm36EjPQQjjPoM` | Menarini Pipeline & Products | Validated | Validated | Established | 18 | 2026-10-07 | 2026-10-14 |
| Vertex Pharmaceuticals | `rececZFW3IobI19Ei` | Vertex R&D Pipeline | Review Required | Needs Review | — | 6 | 2026-09-21 | — |
| Merck & Co. (MSD) | `recfX1QV7yqFHgHcY` | Merck Product Pipeline | Review Required | Needs Review | — | 14 | 2026-08-26 | 2026-09-22 |
| Takeda | `reci24wWuHyRzpkYm` | Takeda Pipeline | Validated | Validated | Needs Review | 54 | 2026-10-01 | 2026-10-03 |
| Teva | `recjYwATY35Oa96n0` | Teva Pipeline | Validated | Validated | Needs Review | 34 | 2026-10-01 | 2026-10-03 |
| Arrowhead Pharmaceuticals | `reck5oLWNoHuyMvAB` | Arrowhead Pharmaceuticals — Pipeline | Validated | Validated | Established | 27 | 2026-10-02 | 2026-10-09 |
| Novo Nordisk | `reckgEdv4ZdgkJGFU` | Novo Nordisk R&D Pipeline | Review Required | Needs Review | — | 3 | 2026-08-25 | 2026-09-22 |
| argenx SE | `reclEd7NX6JzIsW1F` | argenx SE — Pipeline | Validated | Validated | Established | 16 | 2026-10-07 | 2026-10-14 |
| Regeneron Pharmaceuticals | `recp4DqsZgkBkQYMo` | Regeneron Clinical Pipeline | Validated | Validated | Needs Review | 82 | 2026-10-01 | 2026-10-08 |
| Bristol Myers Squibb | `recpWwevfH8qDZ8yL` | BMS R&D Pipeline | Validated | Validated | — | 70 | 2026-08-25 | 2026-09-22 |
| Bayer | `recpYNnKjnaIg0UkV` | Bayer Pharmaceuticals Development Pipeline | Review Required | Needs Review | — | 4 | 2026-09-21 | — |
| Alnylam Pharmaceuticals | `rectZvXGriiGR5gcE` | Alnylam Pharmaceuticals — Pipeline | Review Required | Needs Review | — | 0 | — | 2026-09-22 |
| Recordati | `recth9XJ345XekVPe` | Recordati Research & Development Pipeline | Review Required | Needs Review | Not Established | 5 | 2026-08-26 | 2026-09-22 |
| Roche | `recuZBJ2HgLzrJKEU` | Roche Pipeline | Validated | Validated | Established | 65 | 2026-10-04 | 2026-10-11 |
| Boehringer Ingelheim | `recuuwc5o0cS6LGRF` | Boehringer Ingelheim Human Health Pipeline | Review Required | Needs Review | — | 0 | 2026-08-25 | 2026-09-01 |
| BioNTech SE | `recvRfl2remCgdDxW` | BioNTech SE — Pipeline | Validated | Validated | Established | 55 | 2026-10-07 | 2026-10-14 |
| Daiichi Sankyo | `recvWeM9VsrFILTed` | Daiichi Sankyo Pipeline | Review Required | Needs Review | Not Established | 2 | 2026-09-03 | 2026-09-22 |
| AstraZeneca | `recwIxfNqLhUOjG6q` | AstraZeneca R&D Pipeline | Validated | Validated | Needs Review | 353 | 2026-10-01 | 2026-10-03 |
| Wave Life Sciences | `recwLacs1eKjbAUIX` | Wave Life Sciences — Pipeline | Review Required | Validated | Established | 10 | 2026-09-26 | 2026-10-03 |
| Eli Lilly and Company | `recwqsoeBsyUjySKg` | Lilly R&D Pipeline | Validated | Validated | Established | 56 | 2026-09-26 | 2026-10-03 |
| Bayer | `recy1AYySIjSkOfhe` | Bayer Development Pipeline Snapshot — 2026-08-04 | Validated | Validated | Needs Review | 7 | 2026-09-21 | — |
| Dyne Therapeutics | `recz8m7O6wej0UgzN` | Dyne Therapeutics — Pipeline | Review Required | Needs Review | Needs Review | 8 | — | 2026-09-22 |

## Evidence boundaries

* These are **current Airtable link counts**, not independent verified clinical records or reliable regulatory/commercial completeness; Source Watch `Next Check` dates cannot establish that scheduled runs succeeded. Production statistics should be paired with Airtable run-history evidence before reporting a reliability PASS.
* Some companies have Portfolio rows without Discovery Candidates; this alone does not imply absence of a pipeline or error. Baseline/static imports may predate the Candidate system and require separate provenance checks.
* Historical Gilead six-source/55-Portfolio fixture and 81/81 recovery-branch regressions prove only the optional asset-presence API code contract. They do not validate 53/53 Gilead rows, all 39-company end-to-end reconciliation, or deployed access.
* Zero changes to Airtable Source Watch, Adapter Registry, automation triggers, Candidates, Portfolio master, Queue and customer release gates; no GH merge or deployment.

**Next technical action:** Build one source/Portfolio **read-only** cross-company fixture from existing Airtable data (Amgen, GSK, Pfizer, Chiesi), test comparator default and optional outputs against source-grain availability and hold conditions, and stop if official source input is unavailable. Do not create another automation or write until the controlled preview gate is approved.
