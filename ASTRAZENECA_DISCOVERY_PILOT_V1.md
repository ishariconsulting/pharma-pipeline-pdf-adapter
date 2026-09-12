# AstraZeneca Portfolio Discovery Pilot — V1 Baseline

## Source baseline

Authoritative source: AstraZeneca official pipeline page, updated **27 July 2026**.

Source URL: https://www.astrazeneca.com/our-therapy-areas/pipeline.html

AstraZeneca reports:
- **183** projects in the pipeline
- **116** new molecular entity or major life-cycle-management projects in Phase II or Phase III
- **21** new molecular entities in late-stage development
- **4** new molecular entities under review

The company page organizes programs across Oncology; Cardiovascular, Renal & Metabolism; Respiratory & Immunology; Rare Disease; Infectious Disease; and Other.

## Current Airtable baseline

Company: AstraZeneca
Company record: `rec97SzilVQ4cccVl`

Current Portfolio records: **70**

Current Portfolio records explicitly carrying `Portfolio Status = Pipeline`: **14**
- Phase 2: 1
- Phase 3: 13

The remaining current AstraZeneca Portfolio rows are primarily marketed or approved/pre-launch asset-indication records.

## Pilot conclusion

**Coverage is materially partial.**

The official current pipeline contains 116 Phase II/III NME or major LCM projects, while Airtable currently contains only 14 records explicitly represented as pipeline programs. Some official LCM projects may correctly reconcile to marketed assets already in Portfolio, so the gap must not be calculated as a simple 116 minus 14 count. However, the current Portfolio cannot represent the full source universe at asset × indication grain.

This is exactly the breadth gap the source-to-Portfolio discovery layer is intended to detect.

## Engineering implications

1. AstraZeneca is the correct broad-pharma stress test for source-first discovery.
2. The official pipeline page is already structured by phase and therapy area and should become a reusable official-company-pipeline source adapter.
3. Discovery must distinguish:
   - genuinely new assets;
   - new indications / LCM projects for existing marketed assets;
   - exact existing Portfolio matches;
   - phase/status deltas;
   - qualifier-level ambiguities.
4. Do not create 116 records automatically. Every source project must first be reconciled against existing Portfolio and `COMMERCIAL_PORTFOLIO_V1`.
5. No Portfolio/RPC/MRS writes during the pilot.

## Pilot pass condition

AstraZeneca passes when the official Phase II/III + under-review source universe can be parsed deterministically and every in-scope source project is classified as MATCHED, NEW ASSET, NEW INDICATION, documented fail-closed review, or EXCLUDED BY RULE without false master-data writes.

The expected output is deliberately likely to include real NEW ASSET and NEW INDICATION candidates, unlike the Pfizer regression baseline.
