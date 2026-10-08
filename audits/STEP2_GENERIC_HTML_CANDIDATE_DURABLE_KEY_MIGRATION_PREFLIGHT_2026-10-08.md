# Step 2 — Generic HTML Candidate Durable-Key Migration Preflight

Date: 2026-10-08  
Phase: Production Reliability Recovery / Step 2  
Status: READ ONLY PREFLIGHT — NO AIRTABLE DATA WRITES / NO PRODUCTION DEPLOY

## Purpose

Prepare a controlled migration path from historical ordinal-style generic HTML source keys
(e.g. `phase_triplet_flow:16`, `sectioned_labelled_card:27`) to the new durable
generic HTML source-row identity contract introduced in
`GENERIC_PIPELINE_INTERPRETER_V1.3_DURABLE_SOURCE_KEYS_READ_ONLY`.

This preflight does **not** change Portfolio Discovery Candidates, Source Watch,
Portfolio, Queue, Adapter Registry, or any production automation.

## Proven upstream contract

The audit branch generic HTML interpreter now generates durable source identity using:

1. one source-native NCT ID when exactly one is available;
2. otherwise compact source-backed study/program identifier plus semantic programme identity;
3. otherwise canonical asset identity + indication;
4. phase, parser method and row ordinal are excluded;
5. generic scope-only identities such as `Liver` or `Muscle` fail closed;
6. duplicate durable identities within one current extraction fail closed.

GitHub Actions run 37702704532 passed on commit
`ffb9b77534a3a4db54fdc3cbb55e7a4184ad5638`.

Runtime canary:
- Sobi: 11 rows, PASS
- Ipsen: 10 rows, PASS
- Jazz Pharmaceuticals: 16 rows, PASS
- durable-key self-test: PASS
- Airtable writes: 0
- master-data writes: 0
- company-specific parser branches: 0

## Historical Candidate population in scope

Generic HTML Source Watch records linked through Adapter Registry: **20**

Portfolio Discovery Candidate records linked to those sources: **241**

Two distinct historical populations exist:

- **161 records** already have a nonblank `Source Record ID / Key`.
  These form the migration population below.
- **80 records** have a blank `Source Record ID / Key`.
  These predate the stable-key contract and are explicitly **out of scope for this
  migration**. They require a separate legacy-record audit and must not be silently
  folded into the ordinal-key migration.

## Nonblank legacy-key migration population

Nonblank Candidate records: **161**  
Legacy `(Source Watch, Source Record ID / Key)` groups: **144**

### Classification

| Migration class | Groups | Proposed handling |
|---|---:|---|
| SINGLETON_KEY_MIGRATION | 123 | Update the single active Candidate's Source Record ID / Key to the new durable key; preserve Discovery Candidate ID and reviewer state |
| DUPLICATE_CONSOLIDATION_CLEAR_SURVIVOR | 5 | Keep the single higher-review-state Candidate active; mark the other active historical duplicate Superseded; migrate survivor key |
| DUPLICATE_CONSOLIDATION_REVIEW_REQUIRED | 5 | Deterministic durable identity, but no automatic survivor because active rows have equally strong review state; reviewer decision required before any write |
| SUPERSEDED_HISTORY_ONLY | 1 | Do not auto-reactivate and do not create a replacement merely because the durable key is known |
| QUARANTINE_INSUFFICIENT_IDENTITY | 9 | No migration write; source/parser identity must be repaired or authoritative evidence supplied |
| QUARANTINE_LEGACY_KEY_SPLIT | 1 | No migration write; one legacy key maps to multiple materially different programmes |

Total: **144 groups**

### Identity result

- **134 / 144 groups** map to exactly one deterministic durable identity.
- **10 / 144 groups** are true identity-contract quarantines:
  - 9 insufficient identities
  - 1 legacy key split across different programmes

The 134 deterministic groups are **not all automatically writable**:
- 123 are simple singleton migrations;
- 5 have a clear survivor under current review-state evidence;
- 5 need reviewer choice;
- 1 is Superseded-only history.

Therefore the maximum migration set that could be prepared without resolving reviewer
ambiguity is **128 groups**, and even those require explicit approval before Candidate
writes.

## Clear-survivor duplicate groups

These have one active record with a stronger existing review state than the competing
active duplicate. The higher-review-state record is the proposed survivor; no write has
been made.

1. Regeneron — `sectioned_labelled_card:41` — proposed survivor `recB04zkI0KCCb87m` (Needs Review)
2. Regeneron — `sectioned_labelled_card:30` — proposed survivor `recGQZUn64ffX3qzm` (Needs Review)
3. Regeneron — `sectioned_labelled_card:26::indication:1` — proposed survivor `recNHK9cykQ77Q43C` (Resolved)
4. Regeneron — `sectioned_labelled_card:42::indication:2` — proposed survivor `recsOtjWZVSFJ4iCR` (Resolved)
5. Regeneron — `sectioned_labelled_card:32` — proposed survivor `recTRT00Xv6hphsVO` (Resolved)

These are **proposals only**. The rule must preserve the existing Discovery Candidate ID,
human review status, review decision, programme gate, reviewer narrative, and first-detected
provenance on the survivor.

## Deterministic identity but reviewer choice required

No automatic survivor may be selected for these five groups because both active rows have
equally strong review state.

1. Regeneron — `sectioned_labelled_card:26::indication:2`
2. Regeneron — `sectioned_labelled_card:47::indication:2`
3. Regeneron — `sectioned_labelled_card:43`
4. Regeneron — `sectioned_labelled_card:47::indication:1`
5. Regeneron — `sectioned_labelled_card:47`

Required action: retain both active until reviewer resolution. Do not guess based on
display-name preference alone.

## True identity quarantines

### Insufficient identity — 9 groups

Most are Arrowhead historical positional keys where one or more records were parsed as
generic scope labels such as `Liver` or `Muscle`. These must not be assigned a durable
programme identity automatically.

Known affected legacy keys include:

- `phase_triplet_flow:1`
- `phase_triplet_flow:2`
- `phase_triplet_flow:3`
- `phase_triplet_flow:4`
- `phase_triplet_flow:5`
- `phase_triplet_flow:15`
- `phase_triplet_flow:16`
- `phase_triplet_flow:17`
- `phase_triplet_flow:18`

Required action: fail closed. Repair the shared extraction identity or use authoritative
source evidence. Do not infer the missing asset from indication/phase similarity.

### Legacy key split — 1 group

Regeneron:

`sectioned_labelled_card:27::indication:3`

Historical records under the same legacy key resolve to two materially different
programme meanings:

- CEMIPLIMAB — Neoadjuvant NSCLC
- CEMIPLIMAB — BNT116 combination

Required action: keep quarantined. The source key cannot be migrated as one identity.

## Superseded-only history

Regeneron `sectioned_labelled_card:52` currently has Superseded history without an active
Candidate.

Required action: do not auto-reactivate; do not create a new active Candidate simply to
satisfy the new durable key contract. Current source evidence must independently justify
a new active row.

## Proposed write contract for a later approved migration

No writes are approved by this document.

If a controlled Candidate migration is later approved, the writer must:

1. preflight the entire requested source set before any writes;
2. abort that source if a current durable key collides with another active Candidate;
3. preserve existing `Discovery Candidate ID` on updates;
4. preserve human-reviewed status, decision, programme gate, reviewer narrative, and
   first-detected provenance;
5. update only the active survivor's `Source Record ID / Key` for migrated groups;
6. mark a displaced historical duplicate `Superseded` only when the survivor is
   explicitly approved;
7. never reactivate Superseded-only history automatically;
8. never migrate insufficient-identity or legacy-key-split groups;
9. never write Portfolio master data;
10. emit a complete planned-update / planned-supersede / quarantined / no-op ledger
    before execution;
11. require a second identical read-only preflight immediately before writes;
12. after any approved write, rerun the shared stable-key canary and require zero
    active-active collisions for the migrated keys.

## Production boundary

Not yet done:

- no generic HTML interpreter deployment;
- no production automation publish;
- no Candidate migration writes;
- no Portfolio writes;
- no cleanup of the 80 blank-key legacy records;
- no automatic resolution of the 10 identity quarantines;
- no reviewer decision on the 5 equal-review-state duplicate groups.

Next gate: build a **read-only executable migration plan** for the 128 currently
non-ambiguous groups, including exact Candidate record IDs, proposed durable keys,
proposed Superseded records, and zero-write validation against current Airtable state.
Only after that plan is stable should Candidate writes be considered.
