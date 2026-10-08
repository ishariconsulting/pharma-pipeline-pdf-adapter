# Step 4 R1A - Gilead Source-Row Disposition Proof

Date: 2026-10-08
Mode: READ ONLY
Status: PASS

## Result

The shared V2.61.3 reconciliation logic produced one explicit disposition for every current Gilead official pipeline row.

- Official source rows: 53
- MATCHED: 11
- HELD: 16
- NEW: 26
- UNACCOUNTED: 0
- Duplicate stable source keys: 0
- Ledger rows: 53
- Source coverage balanced: true
- Existing development coverage balanced: true
- Held-row Candidate addressability ready: true
- Reconciliation status: PASS WITH ROW HOLDS
- Candidate writes: 0
- Queue writes: 0
- Source Watch writes: 0
- Portfolio writes: 0
- Master-data writes: 0

## Important persistence finding

The computed disposition contract passes, but durable Candidate addressability is not complete for every source row.

From the 53-row ledger:
- 33 source rows have at least one current Candidate record.
- 20 source rows have no current Candidate record.
- All 20 missing durable Candidate identities are disposition NEW.
- MATCHED rows missing Candidate identity: 0.
- HELD rows missing Candidate identity: 0.

This means R1A (deterministic source-row disposition) is proven, but R1 as a durable source-to-evidence lineage capability is not complete.

## Decision

R1A = PASS.

Next R1 proof is a read-only persistence preflight:
1. Establish a stable durable identity for all 53 source rows.
2. Reuse existing Candidate records where present.
3. Identify exact Candidate-only creates/updates needed to make every source row addressable.
4. Do not write Candidate records until the plan is reviewed.
5. Do not write Portfolio, Queue or Source Watch master state.

The temporary Airtable diagnostic automation was restored from backup commit 76953ce010eb07e66e5c6610ac642ad2591333e0 after the test.
