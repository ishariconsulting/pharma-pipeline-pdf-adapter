# R1C read-only snapshot contract — Framework v2.22

Full Gilead validation: **BLOCKED — INPUT SNAPSHOT REQUIRED**.

No credentials are needed. Supply a read-only export, not access tokens or a production automation change. Do not create or update records to fill missing fields. The exported JSON is an offline evidence contract, not a proposed Airtable schema. Map existing field IDs/names explicitly; label unavailable values as unavailable rather than inventing evidence. The machine-readable required-field contract is `R1C_SNAPSHOT_SCHEMA.json`, generated from the validator.

## Snapshot scope and metadata

Base: `appzteNR0u0ywm9Zz`. One consistent capture is needed for GILD-SW-003 and its full linked-record closure. Include export time with timezone, snapshot/batch ID, export criteria and completeness/pagination attestation per table. Historical Superseded rows must be distinguished from current active rows. Export actual record IDs and linked-record IDs, not display names alone.

Top-level fields: `schemaVersion=R1C_SNAPSHOT_V1`, `snapshotId`, `capturedAt`, `company`, `companyAliases` (verified only), `relatedCompanies` (explicit joint-development views), `sourceWatchRecordId`, `expectedSourceCount=53`, `expectedDispositionCounts={MATCHED:11,HELD:16,NEW:26}`, `completeTables`, `scopeDescription`, and arrays `sources`, `candidates`, `portfolio`, `trials`, `arms`, `relations`, `evidence`, `landscape`, `cases`. The expected totals come from the approved audit baseline; observed rows must be exported separately. Never construct 53 placeholder rows from these counts.

`completeTables` must attest complete in-scope exports for all eight record arrays except cases. An explicitly assessed-empty arms array is allowed and produces scope holds. Missing exports produce a BLOCKED result. Optional regulatory/signal families may be `NOT_ASSESSED`; an empty link must not be called `NO_MATCH` unless that family was actually assessed.

The historical 55-active-record / 53-active-key summaries do not define exact uniqueness semantics. Export the raw status/key evidence and explain any out-of-scope, blank-key or legacy records. Do not silently deduplicate them or convert aggregate status counts into official dispositions. Inputs that cannot represent a current identity safely remain blocked or held pending clarification.

## Exact record inputs

| Dataset / existing table | Fields needed |
|---|---|
| Official pipeline extraction / Source Watch GILD-SW-003 | All 53 **immutable stable source keys** and Source Record IDs, Source Watch record ID, company, official URL, original row text, original asset/molecule/development-code/brand/aliases, indication, phase/status, sponsor/partners, ownership evidence, source granularity, source as-of and retrieval dates, source/adapter/parser versions, per-key R1A disposition/reason/provenance, and authoritative NCT relationship references. The native extraction and R1A ledger are required; Candidate records alone are not an independent official denominator. |
| Portfolio Discovery Candidates `tblrHcZvAeJWGmY4t` | Airtable record ID; `Discovery Candidate ID`; `Source Record ID / Key`; `Source Watch`; `Company`; `Review Status`; active/superseded determination with its rule/provenance; `Discovery Classification`; `Programme Reconciliation Gate`; `Source Scope Granularity`; source version/grain evidence; `Existing Portfolio Match` linked IDs; `Exclusion / Review Reason`; `Evidence Summary`; `Latest Staging Evidence`; `Discovery Batch / Run ID`; `Last Checked`; `Source URL`; original source identity/indication/phase/status/sponsor/partner fields. Include persisted queue/write eligibility assertions if present in evidence; unknown flags must not be fabricated. R1A disposition is separate from Candidate classification: the 20 R1B NEW rows retain EXCLUDED BY RULE. |
| Portfolio `tblRCNY70YVbnKOoq` | Airtable record ID and Company record/name; existing immutable keys (read-only); asset, molecule, development code, brand, verified aliases; source and controlled indication; development phase/status; exact component/regimen identity; treatment line/setting; biomarker/patient segment; route/dose where material; owner/partner/co-developer role evidence; Candidate, Treatment Landscape and Clinical Trials link IDs in both directions; Evidence Families and Cross-source Status. Raw labels and nulls must be preserved. |
| Treatment Landscape `tblUK2IZ4jBaiiG6j` | Record ID; linked Portfolio, Indication and Clinical Segment IDs; exact asset or combination/treatment-option identity; disease/indication; segment/biomarker/patient population; treatment line/setting; route/dose when material; market/jurisdiction; owner vs competitor role; official source URL/text/date; confidence; readiness; Last Verified; actual linkage. A URL/High/Ready label is not semantic, market-availability or freshness proof. Missing direct links are coverage review, not confirmed defects. |
| Clinical Trials `tbl16dpQ6ZWqAbSCs` | Record ID; NCT; study name; registry URL; version/as-of/retrieval dates and status; phase; sponsor/collaborators; investigational and comparator intervention descriptions; disease/indication, line, segment/population, setting, route/dose; Portfolio link IDs; explicit arm/cohort child link IDs. Export all eight NCTs listed in `R1C_GILEAD_CASES.json` plus linked-record closure. |
| Existing Clinical Trial Arms & Cohorts / CT.gov Arm Evidence | Table and field mapping, record ID, parent Clinical Trial ID + NCT, named arm/cohort ref, independently supported cohort relationships, intervention role (experimental/comparator/placebo/background/supportive), focal component set, asset identity, indication, line/population/setting/route/dose, company-role evidence, official registry text/URL/version/date. Export existing links and actual absence of child records. No new arms table or records are requested. |
| Regulatory Product Coverage / Market Regulatory Status / Signals, when assessed | Existing table/field mapping and record IDs, exact Portfolio targets, source family, originating independent authority, official document URL/text/publication and retrieval dates, jurisdiction, exact asset/indication/regimen/population relationship and verification status. Signal republication is informational unless its originating authority is independently established. Unlinked titles cannot prove exact corroboration. |

Candidate field names above are read from the existing staging script. Field IDs/names for other tables must come from the export schema; they have not been inspected live. No required normalized field implies adding a field to Airtable.

## Normalized assertion fields (required by JSON schema)

Every provenance object contains `url`, `sourceRecordId`, `asOf`, `retrievedAt`, `version`, `authorityId`, `originalText`. `authorityId` identifies the **originating** authority (for registry evidence, its NCT), so duplicate company views or republished Signals cannot inflate independent-source counts.

Every programme scope contains `components`, `indication`, `line`, `population`, `setting`, `route`, `dose`, `proofReferences` for each dimension, `companyRole`, `roleProof`. Values are explicitly evidence-backed assertions retaining original text. Null means not assessed and holds the match. `NOT_APPLICABLE` requires a supporting reference; it is not a default. Prior-treatment counts must not be converted to treatment lines without an authoritative protocol reference. Exact canonical component aliases likewise need source-backed proof; no fuzzy or numeric-only normalization is introduced.

Each `relations` entry requires `recordId`, `stableKey`, `portfolioId`, `relationType`, `sharedStudyIdentity`, `companyRoleProof`, `sourceComparison`, `sourceScope`, `sourceProvenance`, `sourceProjectionVerified`, `sourceProjectionProof`, `evidenceIds`. Relationship types are read-only `CANONICAL_PROGRAMME`, `JOINT_DEVELOPMENT_VIEW`, or `INDICATION_RELATIONSHIP`. A company view is not an alias and does not create a new trial. Source projections may preserve a legitimately multi-indication grain with explicit evidence; they cannot substitute a different focal asset, phase or status. Source `trialReferences` maps each supported NCT to its official-source relationship proof.

Each `evidence` entry requires `recordId`, `family`, `portfolioIds`, `provenance`, `armId` (nullable outside registry), `comparison`, `scope`, `jurisdiction` (nullable outside regulatory), `independent`, `verified`. Registry evidence needs a linked focal experimental arm and intact parent/child NCT relation. Parent trial links alone remain held. The exporter must provide assessed/verified assertions backed by the included evidence; the code cannot independently adjudicate a protocol from a citation string.

Comparator source dictionaries use the existing `DiscoverySourceRow` fields: company, sourceFamily, sourceRecordId, sourceUrl, sourceWatchRecordId, asset, molecule, developmentCode, brand, indication, controlledIndicationCandidate, phase, programStatus, sponsorOwner, partners, sourceUnavailable, ownershipResolved and existing commercial-scope flags. Portfolio dictionaries use existing `PortfolioSnapshotRow` fields: recordId, company, asset, molecule, developmentCode, brand, aliases, indication, controlledIndication, indicationAliases, treatmentSettingLine, biomarkerPatientSegment, portfolioStatus, phase. Preserve unavailable source values; do not mark ownershipResolved or strategic flags true without evidence.

## Six-case oracle

Each case needs `name`, exact `sourceKeys`, `expectedNcts`, `expectedPortfolioIds`, `expectedLandscapeIds`, `expectedDisposition`, and `oracleProvenance`. Map actual immutable keys to the supplied programme names using authoritative evidence. Expected R1C dispositions are `SUPPORTED_EXACT`, `SUPPORTED_RELATIONSHIP_WITH_SCOPE_HOLD`, `HELD_AMBIGUOUS`, or `NOT_YET_CORROBORATED`; these are output concepts, not new Airtable statuses. Held/new baseline rows remain unpromoted even if new evidence is positive.

The attached framework currently reports no explicit arm/cohort children for the eight NCTs. That is historical evidence; the snapshot must establish current state. Do not invent arm records, source keys, Portfolio IDs or successful case outputs from that narrative.

## Run locally

From `/workspace/pharma-pipeline-pdf-adapter`, using the existing virtualenv:

```bash
PYTHONDONTWRITEBYTECODE=1 /workspace/.venvs/pharma-pipeline-pdf-adapter/bin/python r1c_regression.py
PYTHONDONTWRITEBYTECODE=1 /workspace/.venvs/pharma-pipeline-pdf-adapter/bin/python r1c_shared_lineage.py --schema
PYTHONDONTWRITEBYTECODE=1 /workspace/.venvs/pharma-pipeline-pdf-adapter/bin/python r1c_shared_lineage.py --snapshot /path/to/read-only-export.json --cases audits/R1C_GILEAD_CASES.json --expected-count 53
```

The first command runs synthetic safeguards and reports real Gilead cases as HOLD when no snapshot exists. Exit codes: 0 PASS, 1 FAIL, 2 HOLD/BLOCKED. Saving stdout does not change the meaning of that code. No service startup, credentials, network calls or Airtable access are needed.

## Framework boundaries

Requirements came from the supplied Framework v2.22 sections “shared evidence-to-programme resolver specification” and “R1C acceptance gate and execution sequence”. The document's instructions to update external control systems do not authorize communications or writes beyond this user's request. Production V2.61.2, the V2.61.3 diagnostic draft, existing automations, PFK1, ZZ System Programme Key, and all master tables remain untouched. Gates 3 and 7 stay GAP; TL readiness stays UNPROVEN; R2–R5 and the 39-company audit stay parked.
