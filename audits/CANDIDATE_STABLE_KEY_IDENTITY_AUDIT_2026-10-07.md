# Candidate Stable-Key Identity Audit — 2026-10-07

## Step 2 purpose

Production Reliability Recovery, Step 2. This audit was triggered by the Amgen read-only cohort canary and is a shared platform-level identity review, not a company-specific repair.

## Base-wide read-only scan

Portfolio Discovery Candidates scanned: **1,282**

Duplicate groups using the durable composite key `(Source Watch, Source Record ID / Key)`: **92**

- **37** groups have more than one non-Superseded Candidate and therefore remain active identity conflicts.
- **55** groups have exactly one active Candidate plus Superseded history.
- **0** groups contain only Superseded history.
- Active conflicts span **7 companies**: Amgen, Gilead Sciences, Biogen, Roche, Regeneron Pharmaceuticals, Arrowhead Pharmaceuticals, and Merck KGaA.

No Airtable writes were made by this audit.

## Proven root cause

The shared Portfolio Discovery comparator generates `Discovery Candidate ID` from company + source family + source record ID + normalized asset + normalized indication.

The current Portfolio Discovery Staging V4.4.8 writer upserts by `Discovery Candidate ID`.

Therefore, when the official/extracted display text for asset or indication changes while the stable source key remains unchanged, the generated Candidate ID changes and the staging writer can create a second Candidate for the same durable source row.

Amgen demonstrates this directly: the same `amgen:8:*:1` stable keys were staged on 22 Sep with the fuller MariTide / former AMG 133 label and again on 25 Sep with the stripped maridebart cafraglutide label.

## Shared identity contract

1. Durable Candidate source identity is `(Source Watch record ID, Source Record ID / Key)`.
2. At most one non-Superseded Candidate may exist for that durable key.
3. `Discovery Candidate ID` is an immutable audit identifier assigned on first creation; it is not the upsert key.
4. A later display-name, alias, indication-text, or phase-text change updates the existing Candidate identified by the durable key and does not create a second Candidate.
5. Superseded history remains audit history and does not count as active.
6. Superseded history with no active Candidate fails closed; the worker does not silently recreate a row.
7. Multiple active Candidates for one durable key fail closed; the worker never chooses one automatically.
8. A single current extraction may not emit the same stable source key more than once after deterministic split logic. Duplicate current keys fail closed as an adapter/source-key contract defect.
9. Portfolio master writes remain outside this contract and remain disabled unless separately approved.

## Shadow implementation

GitHub-only shadow: `airtable_scripts/portfolio_discovery_staging_v4_4_8_stable_key_identity_shadow_2026-10-07.txt`

The shadow was extracted from the exact current Airtable `Portfolio Discovery Staging V4` draft and adds:
- current-extraction stable-key uniqueness validation;
- active vs Superseded stable-key indexes;
- stable-key-authoritative Candidate lookup;
- fail-closed duplicate-ID / duplicate-stable-key / superseded-only checks;
- preservation of the existing Candidate ID on updates.

The shadow has passed JavaScript syntax parsing.

It has **not** been loaded into Airtable, published, or executed.
