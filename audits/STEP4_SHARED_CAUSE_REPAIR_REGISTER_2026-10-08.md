# Step 4 - Shared-Cause Repair Register

Date: 2026-10-08
Basis: Gilead Golden Company seven-gate assessment
Golden scorecard: 1 PASS / 1 BLOCKED / 5 GAP
Rule: repair shared reusable causes only. No company-specific Gilead fixes. No Portfolio master-data writes without explicit approval.

## Ranked shared causes

### R1 - Source-row disposition and cross-source evidence lineage
Priority: P0
Affected gates: Gate 3 Pipeline / Development Portfolio; Gate 7 Cross-Source Reconciliation; materially supports Gate 4 and Gate 6.
Observed evidence:
- GILD-SW-003 reports 53 official programme rows.
- 42 Candidate records are linked to the source.
- 13 Candidate records currently link to Portfolio; 29 do not.
- V2.61.3 row-level programme-grain holds are present and fail closed.
- All 55 Gilead Portfolio Cross-source Status values are blank and Evidence Families coverage is 0/55.
Root problem:
The platform does not expose one authoritative source-row disposition ledger from extraction through MATCHED / HELD / EXCLUDED / NEW / SUPERSEDED to canonical Portfolio and downstream evidence families.
Repair target:
Create one shared, company-agnostic disposition/lineage contract keyed by Source Watch + stable source row identity. Every extracted row must have one current disposition, provenance, canonical target where applicable, and explicit hold reason.
Exit proof:
For Gilead, all 53 source rows reconcile deterministically and Portfolio cross-source evidence can be derived from real lineage rather than inferred formulas.
Why first:
This is the highest-leverage integrity layer and prevents us fixing later modules on top of ambiguous identity/linkage.

### R2 - Company TA / franchise coverage reconciliation
Priority: P1
Affected gate: Gate 4; also improves client Company 360 and Gate 7.
Observed evidence:
- 5 current High-confidence TA Strategy records.
- 55 Portfolio rows span 8 controlled TA labels.
- 26/55 Portfolio rows have TA Strategy links; 29/55 do not.
Root problem:
TA Strategy and Portfolio therapeutic-area taxonomies are both populated but there is no complete shared reconciliation contract between strategic franchise scope and asset-level controlled TA.
Repair target:
Define a shared TA/franchise mapping contract and linkage resolver using controlled taxonomy, with explicit many-to-many support where justified.
Exit proof:
Every in-scope Portfolio row has a defensible TA/franchise relationship or explicit exception; TA Strategy coverage can be measured without inventing synthetic denominators.

### R3 - Company geographic / operating footprint builder
Priority: P1
Affected gate: Gate 5; feeds Gate 6 and customer-facing Company 360.
Observed evidence:
- 0 Company Market Presence records.
- 0 Company Operating Footprint Summary records.
- Gate 1 structural definitions proved the company-structure tables can be populated through shared logic.
Root problem:
There is no proven reusable flow from authoritative company geographic evidence into Market Presence and Footprint Summary.
Repair target:
Build/reuse one shared company operating-market resolver from authoritative geography/affiliate/commercial footprint evidence, distinct from product regulatory presence.
Exit proof:
Gilead has source-backed company operating presence by relevant market/region with idempotent refresh and no conflation with product approvals.

### R4 - Regulatory / market-access coverage denominator
Priority: P1
Affected gate: Gate 6; contributes to Gate 7 and client market cards.
Observed evidence:
- 47 Regulatory Product Coverage records linked to Portfolio; all 47 Matched.
- 13 Market Regulatory Status records; all Authorised and Verified.
- Reimbursement Status blank on all 13.
Root problem:
The regulatory layer contains strong evidence but lacks one declared denominator across major products x priority markets, and authorisation / reimbursement / commercial availability are not yet completed as separate evidence dimensions.
Repair target:
Define a shared product-market coverage contract and evidence states for authorisation, reimbursement and commercial availability.
Exit proof:
Coverage is measurable against an explicit product x market denominator, with unknown access facts remaining unknown rather than inferred from approval.

### R5 - Dynamic/browser-rendered source retrieval
Priority: P2
Affected gate: Gate 2; potentially any future dynamic HTML source.
Observed evidence:
- Direct server HTML returned navigation shell, not medicine cards.
- V1.3 and V1.4 read-only catalogue shadows correctly failed closed.
- Warm forced-browser probe returned 502 because browser fallback failed with upstream 429.
- Existing 29 catalogue rows remain untouched.
Root problem:
The shared dynamic-page route cannot currently guarantee rendered content for this source class.
Repair target:
Harden shared browser retrieval with explicit rendered-source routing, backoff/quota handling, and retrieval-fidelity checks before extraction.
Exit proof:
A read-only Gilead full-catalogue refresh returns a plausible complete product set and disappearance reconciliation remains fail closed.
Why not first:
It is important but isolated to one gate and should not block repair of broader lineage/coverage architecture.

## Repair order

1. R1 Source-row disposition and cross-source evidence lineage.
2. R2 TA / franchise coverage reconciliation.
3. R3 Company geographic / operating footprint builder.
4. R4 Regulatory / market-access coverage denominator.
5. R5 Dynamic/browser-rendered source retrieval.

## Control rule

After each repair batch:
1. Re-run only the affected Gilead acceptance gates.
2. Record PASS / GAP / BLOCKED.
3. Stop if the repair introduces a new regression.
4. Update Airtable audit, Monday, GitHub and the production framework.
5. Do not start the 39-company audit until Gilead is re-assessed after the ranked shared repairs.
