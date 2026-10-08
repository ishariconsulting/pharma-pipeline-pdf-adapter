# Step 2A - Gilead Golden Company - Gate 3 Pipeline / Development Portfolio

Date: 2026-10-08
Status: GAP
Mode: Assessment only. No Portfolio writes.

## Live evidence

Source Watch:
- Source Watch ID: GILD-SW-003
- Source: Gilead Pipeline
- URL: https://www.gilead.com/science/pipeline
- Monitoring Status: Active
- Pipeline Adapter Status: Validated
- Adapter Binding Status: Validated
- Adapter: PIPELINE_SITECORE_SXA_JSON_V1
- Retrieval Mode: EXTERNAL_HTTP
- Pipeline Baseline Status: Established
- Last Checked: 2026-10-02
- Next Check: 2026-10-09
- Source Watch notes report 53 official programmes parsed.

Portfolio:
- 55 Gilead Portfolio rows total.
- Portfolio Status: 16 Pipeline, 34 Marketed, 2 Approved / Pre-launch, 2 Filed / Registration, 1 Discontinued.
- 9 Portfolio rows are directly linked to GILD-SW-003.
- 14 Portfolio rows have Portfolio Discovery Candidate links.

Candidate ledger for GILD-SW-003:
- 42 linked Candidate records.
- Classification: 31 NEW ASSET, 5 NEW INDICATION, 4 EXCLUDED BY RULE, 2 NEW PROGRAM.
- Review status: 16 Needs Review, 15 New, 9 Resolved, 2 Superseded.
- 13 Candidate records currently link to Portfolio; 29 do not.
- V2.61.3_HOLD_PROGRAMME_GRAIN is present on ambiguous programme/indication rows and explicitly prevents false NEW PROGRAMME / SOURCE DISAPPEARANCE routing and Portfolio promotion.

## Assessment

The source, retrieval binding and adapter are healthy enough to assess. The platform also demonstrates the intended fail-closed programme-grain hold behavior.

However, the current live evidence does not provide a trustworthy one-to-one disposition ledger for all 53 source programme rows across MATCHED / HELD / EXCLUDED / NEW / SUPERSEDED states. Candidate count (42), Portfolio linkage, and source row count (53) cannot be reconciled into a defensible captured denominator without further shared lineage/reconciliation work.

Therefore Gate 3 cannot Pass.

This is a GAP, not an infrastructure BLOCK:
- extraction is working;
- adapter binding is validated;
- source is current;
- uncertainty is contained;
- but completeness and lineage to master Portfolio are not yet proven.

## Golden Company decision

Gate 3 = GAP.

Expected Count may be recorded as 53 official source programme rows.
Captured Count should remain unset until the shared source-row disposition contract can prove a complete denominator.

Do not repair during the seven-gate assessment. Park the shared reconciliation/lineage gap for the later repair step. No company-specific Gilead logic and no Portfolio master-data write.
