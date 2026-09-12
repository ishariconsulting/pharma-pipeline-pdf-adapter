# Pfizer Portfolio Discovery Pilot — V1 Baseline

## Scope

Purpose: establish a controlled regression baseline for `PORTFOLIO_DISCOVERY_V1` before any automated staging or master-data routing.

Authoritative source: Pfizer official pipeline PDF / website, **as of August 4, 2026**.

Source snapshot:
- Phase 1: 37
- Phase 2: 25
- Phase 3: 31
- Registration: 2
- Total pipeline rows: 95

Under `COMMERCIAL_PORTFOLIO_V1`, the default automatic development scope is:

- Phase 2: 25
- Phase 3: 31
- Registration: 2
- **Total default in-scope development rows: 58**

Phase 1 is not automatically included; only explicitly strategic Phase 1 programs should enter commercial scope after separate evidence/QA.

## Airtable read-only comparison baseline

A read-only review of the current Pfizer Portfolio snapshot shows that **all 58 current Pfizer Phase 2 / Phase 3 / Registration source program rows have an existing corresponding Portfolio representation**.

This is a useful regression oracle for the comparator: after deterministic identity/indication normalization, Pfizer should not generate genuine `NEW ASSET` outcomes for these 58 source rows.

This finding does **not** mean Pfizer Portfolio is globally exhaustive. It only establishes coverage against the current official Pfizer pipeline source for the default Phase 2+ / Registration development scope.

## Important edge cases discovered

### 1. Exact raw indication wording is too strict

Several existing Portfolio records represent the correct source program but use normalized/commercially readable wording rather than the exact Pfizer source string.

Examples include:
- atirmociclib: `1L HR+/HER2- Metastatic Breast Cancer (FourLight-3)` vs a normalized first-line HR-positive/HER2-negative Portfolio description.
- ELREXFIO programs where Portfolio wording may describe the patient setting without retaining the Pfizer study code such as MM-5/MM-6/MM-7/MM-32.
- TALZENNA + XTANDI where the source compound cell is TALZENNA/talazoparib and the combination partner appears in the source indication text.

Therefore `NEW INDICATION` must not be emitted solely because raw source-facing strings are not identical.

Required matching order should remain fail-closed but support deterministic clinical normalization:
1. exact asset identity;
2. exact source-facing indication where available;
3. exact controlled indication / verified indication alias;
4. deterministic treatment-line / biomarker / study-code qualifier reconciliation when needed;
5. unresolved cases to review, never an automatic new indication.

### 2. Combination-program identity needs component-aware matching

Example: source `TALZENNA (talazoparib)` with `Combo w/ XTANDI (enzalutamide)` in the indication versus Portfolio `TALZENNA + XTANDI` / `talazoparib + enzalutamide`.

This should be matched only when the source evidence contains all required exact regimen components. Substring/fuzzy-only matching is not sufficient.

### 3. Phase/status differences are deltas, not new assets

Known pilot example:
- Pfizer official source: `PF-07307405` Lyme disease vaccine — **Phase 3**.
- Current Airtable Portfolio representation: VLA15 / PF-07307405 exists, but its phase/status is currently represented as **Filed / Registration**.

The discovery layer should classify the identity as existing and surface a read-only **phase/status delta**. It must not misclassify this as a new asset or silently update Portfolio.

The existing source-monitoring / resolution architecture remains the correct downstream path for an approved field change after QA.

## Pilot pass criteria

Before Pfizer is marked comparator-pass:

1. All 58 Phase 2+ / Registration source rows are reconciled to an existing Portfolio representation or explicitly fail closed for a documented reason.
2. No known existing program is falsely labeled `NEW ASSET` because of naming differences.
3. No known existing indication is falsely labeled `NEW INDICATION` solely because of source wording normalization.
4. Combination regimens require exact component evidence.
5. Phase/status differences are emitted as read-only deltas, not identity failures.
6. No Portfolio, RPC, MRS or existing automation writes occur.

## Next engineering change

Comparator V1.1 should add:
- deterministic indication normalization / controlled-indication reconciliation;
- component-aware combination identity;
- explicit read-only `fieldDeltas` for phase/status differences;
- a review outcome for unresolved qualifier-level ambiguity without creating false new-asset/new-indication candidates.

Only after these checks pass should Pfizer discovery candidates be staged automatically in Airtable.
