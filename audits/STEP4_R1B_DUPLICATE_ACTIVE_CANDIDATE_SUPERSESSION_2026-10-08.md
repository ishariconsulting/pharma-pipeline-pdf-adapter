# Step 4 R1B - Duplicate-active Candidate supersession

Date: 2026-10-08
Mode: Controlled Candidate-only write
Portfolio writes: 0
Queue writes: 0
Source Watch writes: 0

## Reason

The R1B read-only persistence preflight found five stable source keys with two active Candidate records. In each pair:
- the later Candidate is Review Status = Resolved;
- it is linked to the canonical Portfolio record;
- the earlier Candidate is Review Status = New;
- both share the same Source Watch + Source Record ID / Key.

The durable Candidate identity contract is Source Watch + Source Record ID / Key, so only one active Candidate may remain addressable for each source row.

## Approved supersessions

1. d288b28c-e786-41eb-bb26-f29a91d99621
   - Superseded: recFsz6BKTXkX90XQ
   - Retained canonical Candidate: rec6qEGwtWwh9JEVi

2. 1fb8db15-3ced-4895-bbcf-4b6bf3616069
   - Superseded: recMfg6sqPVHRMU6k
   - Retained canonical Candidate: recq1K3UKStH9Oiq7

3. d6f4a858-8a80-4cb8-bf5c-23cd142d2f10
   - Superseded: recLJQkFmh7VB5Y7P
   - Retained canonical Candidate: recpupspQn9gcBtk4

4. 10c9ce38-eb98-4a82-80eb-3e5dd0481a4b
   - Superseded: recTRyhqON1QaAoeS
   - Retained canonical Candidate: recCjmf8PeIUY8tHN

5. 9c6340d3-0bc8-4fc0-abdf-f1fc6f55ac52
   - Superseded: reclunMRLwdf5bAXF
   - Retained canonical Candidate: recewjV13r0AYn0lk

## Write scope

Only the five duplicate Candidate records were updated:
- Review Status -> Superseded
- Programme Review Next Action -> audit explanation
- Latest Staging Evidence -> deterministic supersession marker

No records were deleted. Canonical resolved Candidates were not changed. Portfolio, Intelligence Update Queue and Source Watch were not written.

## Verification

Post-write readback confirmed:
- all five duplicate records = Superseded;
- all five canonical counterparts = Resolved;
- each canonical counterpart retained its Portfolio link;
- no Portfolio write occurred.

## Next gate

Re-run the same R1B read-only persistence preflight.

Required result:
- ambiguousActiveCandidateMappings = 0
- sourceRowsMissingActiveCandidate = 20
- plannedCandidateCreates = 20
- conflictCount = 0
- planReady = true

No Candidate CREATE is authorised until that re-run passes.
