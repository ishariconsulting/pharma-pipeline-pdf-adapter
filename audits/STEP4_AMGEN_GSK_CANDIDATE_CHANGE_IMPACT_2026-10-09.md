# Step 4: Amgen and GSK Candidate write-risk preflight
Date: 2026-10-09. Read-only Airtable inspection; zero writes or trigger changes.

## Scope
Amgen 51 and GSK 53 existing pipeline-linked Candidates (104 total), with stored Discovery batch, Source Record ID, classification, Portfolio matches, review state and programme gate. A current official-source extraction and comparator run have NOT been performed.

## Mutually exclusive write-risk strata

| Disposition | Amgen | GSK | Total |
|---|---:|---:|---:|
| Prior / keyless Completeness records: preserve | 5 | 10 | 15 |
| Reused Discovery source key: hold | 12 | 0 | 12 |
| Keyed NEW ASSET already linked to Portfolio: hold | 3 | 3 | 6 |
| Other human-reviewed or ready-gate records: preserve | 8 | 37 | 45 |
| Other singly keyed records: eligible for future no-write comparison only | 23 | 3 | 26 |
| Total | 51 | 53 | 104 |

The six Amgen repeated-key groups each contain TWO Candidate records with the SAME indication and source key, but a differently decorated asset label, yielding 12 records. This is a candidate-grain collision/duplicate-risk, NOT an indication difference. Never merge/delete using name only; confirm source stable identity and reviewed history first.

Across the two companies, 14 NEW ASSET Candidates already link to Portfolio: eight keyless legacy records and six keyed Discovery records. These links do not independently certify precise programme matches. Do not overwrite them with a new comparator result.

Amgen has no Candidate with populated Latest Staging Evidence; GSK has 30/53 populated. Existing last-checked timestamps and Stored Discovery source IDs do not prove official source freshness.

## Existing worker gate
OFF Portfolio Discovery Worker V1.15 can handle Established and Needs Review baselines, but directly writes Candidate create/update, Queue status and Source Watch dates. Its payload can write Discovery Classification, Existing Portfolio Match, Match Method, Match Confidence, candidate programme gate, structured scope, source fields and Latest Staging Evidence. Some reviewer values are preserved by its current code, but protection is not comprehensive enough to guarantee no history loss on bulk run. Turning it on is NOT a dry run.

Require prior to Candidate refresh: independently sourced official rows and all-batch parity, stable Candidate unique key including source programme/indication grain, complete before/after per-field diff, historical-record holds, identity collision quarantine, no-write execution mode covering Candidate/Queue/Source Watch, and explicit approval with rollback. Stage zero Portfolio masters and never promote programmes from asset identity alone.

Pfizer: binding Needs Review -> hold. Chiesi: adapter Review Required and binding Needs Review -> hold.

## Decision
No Candidate field changes are proposed because fresh official source inputs are not available. Retain the existing Worker V1.15 as the preferred reusable path but do NOT enable, publish or change production. Next work is a bounded shared offline no-write worker-diff contract for the 26 singly keyed, non-reviewed records, with collision and reviewer groups held. Full 39-company production acceptance is not claimed.
