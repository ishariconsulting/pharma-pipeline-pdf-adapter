# Step 4 R1B - Candidate Persistence Controlled Write

Date: 2026-10-08
Status: WRITE PASS
Scope: Gilead GILD-SW-003 only
Write scope: Candidate table only
Airtable create action: act6LeG8QBnXjSK5W

## Approved write

Created exactly 20 Portfolio Discovery Candidate records from the passed R1B preflight.

Common controls:
- Review Status = New
- Programme Reconciliation Gate = Unassessed
- Discovery Classification = EXCLUDED BY RULE (as returned by the existing V1.6.0 shared comparator)
- Existing Portfolio Match = blank
- Source Watch = GILD-SW-003
- Company = Gilead Sciences
- Candidate evidence explicitly states queueEligible=false and portfolioWriteEligible=false

No existing Candidate records were updated by this create action.
No Portfolio, Intelligence Update Queue or Source Watch records were written.

## Post-write verification

Official source rows / stable keys: 53
Official source keys with exactly one active Candidate: 53
Missing source keys: 0
Non-unique source keys: 0
Extra active stable keys outside the current 53: 0

Candidate ledger totals for GILD-SW-003 after write:
- 62 linked Candidate records including retained superseded history
- 55 active Candidate records
- 53 unique active stable source keys
- 0 ambiguous active stable keys
- 20 controlled-create rows
- controlled-create Review Status: New = 20
- controlled-create Programme Reconciliation Gate: Unassessed = 20
- controlled-create Portfolio links = 0

## Decision

R1B PASS.

The durable Candidate addressability objective is met: every current official Gilead source row has exactly one active stable-key Candidate identity.

R1 remains active. The next substep is R1C: prove that cross-source evidence/status can be derived from the now-clean source-row -> Candidate -> canonical Portfolio lineage without writing Portfolio master data.

Do not reopen the 20 Candidate create decision and do not promote these rows to Portfolio as part of R1C.
