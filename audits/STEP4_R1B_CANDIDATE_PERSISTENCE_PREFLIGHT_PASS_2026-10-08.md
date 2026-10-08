# Step 4 R1B - Candidate Persistence Prewrite PASS

Date: 2026-10-08
Company: Gilead Sciences
Source Watch: GILD-SW-003
Mode: Controlled Candidate-ledger repair; no Portfolio writes.

## R1A disposition proof remains PASS
- Official source rows: 53
- MATCHED: 11
- HELD: 16
- NEW: 26
- Duplicate source stable keys: 0
- Unaccounted source rows: 0
- Source coverage balanced: true
- Existing-development coverage balanced: true
- Hold-ledger addressability ready: true

## R1B rerun result
- Current source rows with exactly one active Candidate: 33
- Source rows missing active Candidate: 20
- Superseded-only missing active Candidate: 0
- Ambiguous active Candidate mappings: 0
- Planned Candidate CREATEs: 20
- Planned Candidate UPDATEs: 0
- Comparator: V1.6.0 PORTFOLIO DISCOVERY READ ONLY - DETERMINISTIC IDENTITY VARIANTS
- Conflicts: 0
- planReady: true
- Status: PASS - EXACT CANDIDATE-ONLY PERSISTENCE PLAN READY

## Schema verification
The live Portfolio Discovery Candidates schema supports every proposed field/value in the 20-row create plan:
- Discovery Source Family = Company Pipeline
- Discovery Classification = EXCLUDED BY RULE
- Review Status = New
- Programme Reconciliation Gate = Unassessed
- Existing Portfolio Match = blank
- Source Watch / Company linked records resolve to GILD-SW-003 / Gilead Sciences.

## Safety
The preflight performed zero Candidate, Queue, Source Watch, Portfolio or master-data writes.
The temporary diagnostic automation was restored to its original OFF Regeneron single-call diagnostic after the rerun.
No Candidate CREATE is recorded by this evidence file. Execution of the exact 20-row Candidate-only create plan is a separate controlled action.
