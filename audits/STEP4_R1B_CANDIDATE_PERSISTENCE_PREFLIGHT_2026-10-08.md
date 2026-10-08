# Step 4 R1B - Candidate persistence preflight and duplicate-active reconciliation

Date: 2026-10-08
Status: PREWRITE REVIEW REQUIRED
Mode: Read-only evidence. No Candidate or Portfolio writes executed.

## R1B preflight result

- Official source rows: 53
- Current rows with exactly one active Candidate: 28
- Source rows missing active Candidate: 20
- Superseded-only rows missing active Candidate: 0
- Ambiguous active Candidate mappings: 5
- Planned Candidate CREATE previews: 20
- Comparator conflicts: 0
- Comparator: V1.6.0 PORTFOLIO DISCOVERY READ ONLY - DETERMINISTIC IDENTITY VARIANTS
- planReady: false
- Reason: five stable source identities currently have two active Candidate rows.

The 20 planned CREATE previews are conflict-free but MUST NOT be written while duplicate-active stable identities remain.

## Duplicate-active groups

Durable identity contract: (Source Watch, Source Record ID / Key). One stable source identity must not have two current active Candidate records.

1. Source key d288b28c-e786-41eb-bb26-f29a91d99621
   - Keep active/current: rec6qEGwtWwh9JEVi
     - Source Asset: Sacituzumab govitecan-hziy + pembrolizumab
     - Review Status: Resolved
     - Portfolio Match: recM5al4s7pERM8Lr
   - Supersede: recFsz6BKTXkX90XQ
     - Source Asset: Sacituzumab govitecan-hziy + pembrolizumab (ASCENT-04)
     - Review Status: New

2. Source key 1fb8db15-3ced-4895-bbcf-4b6bf3616069
   - Keep active/current: recq1K3UKStH9Oiq7
     - Source Asset: Sacituzumab govitecan-hziy + pembrolizumab
     - Review Status: Resolved
     - Portfolio Match: recvF1bKcqSsYbSSh
   - Supersede: recMfg6sqPVHRMU6k
     - Source Asset: Sacituzumab govitecan-hziy + pembrolizumab (ASCENT-05)
     - Review Status: New

3. Source key d6f4a858-8a80-4cb8-bf5c-23cd142d2f10
   - Keep active/current: recpupspQn9gcBtk4
     - Source Asset: Sacituzumab govitecan-hziy
     - Review Status: Resolved
     - Portfolio Match: recznalzdjDiOVbai
   - Supersede: recLJQkFmh7VB5Y7P
     - Source Asset: Sacituzumab govitecan-hziy (EVOKE-SCLC-04)
     - Review Status: New

4. Source key 10c9ce38-eb98-4a82-80eb-3e5dd0481a4b
   - Keep active/current: recCjmf8PeIUY8tHN
     - Source Asset: Sacituzumab govitecan-hziy
     - Review Status: Resolved
     - Portfolio Match: rec44n56qPnTnkzpr
   - Supersede: recTRyhqON1QaAoeS
     - Source Asset: Sacituzumab govitecan-hziy (ASCENT-GYN-01)
     - Review Status: New

5. Source key 9c6340d3-0bc8-4fc0-abdf-f1fc6f55ac52
   - Keep active/current: recewjV13r0AYn0lk
     - Source Asset: Sacituzumab govitecan-hziy
     - Review Status: Resolved
     - Portfolio Match: recDpccsFNVwHun92
   - Supersede: reclunMRLwdf5bAXF
     - Source Asset: Sacituzumab govitecan-hziy (ASCENT-03)
     - Review Status: New

## Proposed controlled Candidate-only mutation

For the five rows listed under Supersede:
- Change Review Status to Superseded.
- Preserve Source Watch, Source Record ID / Key, Discovery Candidate ID, source evidence and all historical text.
- Do not delete Candidate records.
- Do not create or update Portfolio.
- Do not create Queue items.
- Do not change Source Watch.

Then rerun R1B preflight. Required result:
- ambiguousActiveCandidateMappings = 0
- sourceRowsMissingActiveCandidate = 20
- plannedCandidateCreates = 20
- conflictCount = 0
- planReady = true

Only after that clean rerun may the separate 20-row Candidate CREATE plan be considered for approval.
