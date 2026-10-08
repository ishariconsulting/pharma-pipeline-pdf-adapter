# Step 2A Gate 1 — Company 360 operating-structure extension decision

Date: 2026-10-08  
Phase: Production Reliability Recovery  
Gate: Step 2A / Gate 1 — Operating Structure & Business Units  
Golden Company: Gilead Sciences  
Decision: BLOCKED pending shared Company 360 capability; no Gilead-specific fix.

## Evidence

### Airtable
- Gilead has 0 records in `Company Regional Definitions`.
- Gilead has 0 records in `Company Operating Footprint Summary`.
- Existing records in those tables are Takeda-only: 4 structural definitions and 5 footprint-summary rows.
- Gilead already has 9 Source Watch records, but none is explicitly contracted to populate operating-structure/business-unit definitions.
- `Company Completeness - New Company` correctly creates a mandatory `Operating Structure & Business Units` completeness check, but it is an audit control only and does not populate structural master data.

### Current Company 360 architecture
- `Company 360 Bootstrap - Production` is deployed and company-agnostic. It discovers/binds pipeline, products, investor-relations and news sources, then routes other bootstrap work. It does not write:
  - Company Regional Definitions
  - Company Market Presence
  - Company Region Market Mapping
  - Company Operating Footprint Summary
- `Company 360 - Company & TA Strategy Enrichment` is undeployed. It already performs official/primary-source Company 360 research and writes Companies + TA Strategy.
- Its current trigger requires TA Strategy to be empty. That means Gilead, which already has TA Strategy, cannot use it as-is for structure enrichment.
- No reusable writer for `Company Regional Definitions` or `Company Operating Footprint Summary` was found in the current GitHub default branch.

### Source contract
Existing Source Watch vocabulary is sufficient for Gate 1 without schema expansion:
- Source Type: Annual Report / 10-K, Investor Relations, or Other Public Source
- Monitor For: Strategy / Management
- Intelligence Domain: Commercial / Corporate
- Coverage Scope: existing company-specific scope
- Retrieval may use existing HTML/document routes.

`GENERIC_HTML_CONTENT_V1` is currently marked Validated and Fail Closed. Latest validation summary reports 5/5 PASS. Its Endpoint / Handler field still says `GENERIC_HTML_CONTENT_V1 — validation handler pending`; this is a metadata inconsistency and is not evidence that structural interpretation exists.

## Gilead structure evidence rule

Gilead's 2025 Form 10-K states that the company has **one operating segment**. The shared resolver must preserve that fact. It must not infer multiple operating/business units merely because Gilead describes therapeutic focus areas such as virology, oncology and inflammation.

Authoritative filing:
https://www.sec.gov/Archives/edgar/data/882095/000088209526000006/gild-20251231.htm

## Shared extension point

Preferred reuse point:
`Company 360 - Company & TA Strategy Enrichment`

Reason:
- It is already the Company 360 enrichment stage.
- It already restricts research to official/primary sources.
- It is undeployed, so it can be safely redesigned before production use.
- Reusing it avoids another normal-production automation.

Required refactor:
1. Make the automation multi-domain and idempotent.
2. Replace the current TA-empty-only trigger logic with domain-independent gating.
3. Keep TA Strategy creation behind an explicit "TA missing" branch.
4. Add a separate structural branch that can run when structure is missing even if TA Strategy already exists.
5. Structural output must upsert only evidenced `Company Regional Definitions`.
6. Preserve source URL, source name, verification state and effective dates.
7. Fail closed when no reliable company-defined hierarchy is disclosed.
8. Do not create therapeutic-area pseudo-business-units.
9. Do not write Portfolio.
10. Keep Geographic / Market Footprint as a separate completeness gate; do not mix worldwide-market mapping into Gate 1.

## Implementation gate

Do not enable writes yet.

Order:
1. Build a read-only structural preflight contract.
2. Run it against Gilead and Takeda.
3. Require Gilead result to resolve to a company-defined single operating segment unless stronger official evidence exists.
4. Require Takeda to preserve the existing U.S. Business Unit, International Business Unit, Japan Pharma Business Unit and Global Vaccines Business Unit structure without duplicate creation.
5. Confirm idempotent keys and no TA Strategy changes.
6. Only after review, prepare a controlled structural writer for explicit approval.

Gate 1 remains BLOCKED until the shared path is proven. A plausible AI output is not a PASS.
