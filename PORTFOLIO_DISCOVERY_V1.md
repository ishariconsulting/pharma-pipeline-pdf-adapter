# Portfolio Discovery & Completeness — READ ONLY V1

## Purpose

Provide one reusable, company-agnostic discovery contract that compares authoritative external asset/program evidence against the existing Airtable Portfolio without modifying master intelligence.

This layer exists to make company onboarding and Portfolio completeness scalable from the current company set toward a commercial universe of ~125 innovative pharma/biotech companies.

## Non-negotiable guardrails

- READ ONLY against Portfolio, Regulatory Product Coverage and Market Regulatory Status.
- Do not alter or repurpose existing Airtable automations.
- No direct master-data writes from V1.
- No fuzzy-only identity resolution.
- Ambiguous ownership, identity or indication mapping fails closed to review.
- Preserve exact source wording and provenance.
- Generics/commodity products are outside the commercial product scope by default.
- Formulation/strength/presentation rows belong in regulatory/product evidence layers, not as separate commercial Portfolio assets.

## Commercial Portfolio inclusion policy — `COMMERCIAL_PORTFOLIO_V1`

### Include

A discovered asset/indication is in commercial scope when at least one of the following is supported by authoritative evidence:

1. Active strategic marketed prescription brand.
2. Filed / registration-stage asset.
3. Active Phase 2, Phase 2/3 or Phase 3 development program.
4. Important active label-expansion program for a strategic marketed asset.
5. Phase 1 only when explicitly strategically important, for example a company-designated priority platform/program, major first-in-class program or otherwise clearly commercially material asset.

### Exclude by default

1. Generic/commodity products.
2. Inactive, discontinued, terminated or withdrawn programs.
3. Commodity mature/legacy products with no meaningful strategic or commercial activity.
4. Duplicate dosage forms, strengths or presentations as separate Portfolio records.
5. Exploratory Phase 1 programs without evidence of strategic importance.

### Review rather than infer

- Ownership/licensing rights unclear.
- Source company name resolves to a subsidiary/former name but parent ownership is uncertain.
- Asset identity cannot be established by exact molecule, brand, development code or verified alias.
- Source indication is materially more specific than the controlled taxonomy and cannot be safely normalized.
- Phase/status is incomplete or conflicting across authoritative sources.

## V1 source families

Initial discovery should use three source families:

1. Official company pipeline sources.
2. ClinicalTrials.gov.
3. FDA / official US regulatory evidence.

Additional regulatory authorities and company IR/investor materials can plug into the same contract later.

## Input contract

Every source adapter should preserve, where available:

- `company`
- `sourceFamily`
- `sourceRecordId`
- `sourceUrl`
- `sourceWatchRecordId`
- `asset`
- `molecule`
- `developmentCode`
- `brand`
- `indication`
- `phase`
- `programStatus`
- `sponsorOwner`
- `partners`
- explicit commercial-scope flags only when source-backed, e.g. `strategicPhase1`, `importantLabelExpansion`, `marketedStrategicRx`

Portfolio comparison snapshot should expose:

- Airtable Portfolio record ID
- company
- Brand / Asset
- Molecule / INN
- Development Code
- Asset Aliases / Former Codes
- source-facing Indication
- controlled Indication
- Development Phase
- Portfolio Status

## Exact identity precedence

Identity matching is deterministic and source-backed. Recommended precedence:

1. Exact Development Code.
2. Exact Molecule / INN.
3. Exact commercial Brand / current Asset name.
4. Exact verified alias/former code.
5. Composite agreement across two or more exact identity fields.

Do not resolve by fuzzy text similarity alone.

## Discovery classifications — `PORTFOLIO_DISCOVERY_V1`

### `MATCHED`
Exact asset identity and indication are already represented in Portfolio.

### `NEW ASSET`
Commercially relevant source-backed asset has no exact Portfolio identity match.

### `NEW INDICATION`
Asset identity already exists, but the source-backed indication is not represented by an existing Portfolio asset-indication record.

### `POSSIBLE DUPLICATE`
More than one existing Portfolio record represents the same exact asset identity and same indication at the intended Portfolio grain, or exact identity evidence conflicts across multiple records.

### `OWNERSHIP REVIEW`
The asset/program may be relevant but target-company ownership, licence rights, acquisition/subsidiary mapping or alliance responsibility is not safe to resolve automatically.

### `EXCLUDED BY RULE`
Source evidence is valid but the item falls outside `COMMERCIAL_PORTFOLIO_V1`.

### `SOURCE UNAVAILABLE`
The expected authoritative discovery source cannot be retrieved or parsed reliably. This is a coverage warning, never evidence that the company has no relevant assets.

## Match confidence

- **High** — exact development code, exact molecule/INN, exact brand/current asset, or multiple exact identity fields agree.
- **Medium** — verified alias/former code is the decisive identity evidence.
- **Low** — unresolved/conflicting evidence; must remain in review and cannot be treated as matched.

## Staging destination

Airtable table: **Portfolio Discovery Candidates**.

One row represents one source-discovered asset/indication candidate and stores source-native identity, comparison result, inclusion decision, evidence and any existing Portfolio match.

V1 may create/update staging rows only after the read-only comparator is validated. It must not route into Portfolio or the existing Intelligence Update Queue automatically.

## Pilot acceptance test

Pilot companies:

1. Pfizer — broad large-pharma portfolio.
2. AstraZeneca — deep multi-TA / indication complexity.
3. Vertex — smaller innovative-biopharma profile.

For each pilot, validate:

- source row count and retrieval integrity;
- exact identity resolution;
- indication-level comparison;
- duplicate handling;
- ownership/licence edge cases;
- commercial inclusion/exclusion decisions;
- no master writes;
- reproducible run/version identifiers.

## Scale path

1. Validate V1 on the three pilots.
2. Batch-run current companies.
3. Add new target companies in batches toward 75-company product testing.
4. Expand toward ~125-company commercial MVP.
5. Only after QA, allow reviewed discovery candidates to enter the existing controlled resolver/write architecture.
6. New regulatory market adapters should enrich the shared company/Portfolio universe rather than creating country-specific duplicate portfolios.
