# Vertex Pharmaceuticals Portfolio Discovery Pilot — V1 Baseline

## Current-source baseline

Primary authoritative sources:
- Vertex Q2 2026 results, published 3 August 2026
- Vertex acquisition completion announcement for Crinetics, published September 2026

Source URLs:
- https://investors.vrtx.com/news-releases/news-release-details/vertex-reports-second-quarter-2026-financial-results
- https://investors.vrtx.com/news-releases/news-release-details/vertex-completes-acquisition-crinetics-pharmaceuticals-and

## Current Airtable baseline

Company: Vertex Pharmaceuticals
Company record: `recDmyFadiFqPaHzp`

Current Portfolio records: **13**

The current Portfolio already represents several major commercial and development programs, including:
- ALYFTREK
- TRIKAFTA / KAFTRIO
- CASGEVY in SCD and TDT
- JOURNAVX / suzetrigine
- povetacicept in IgAN, pMN and gMG
- inaxaplin in APOL1-mediated kidney disease
- zimislecel in type 1 diabetes
- PALSONIFY
- atumelnant in congenital adrenal hyperplasia

## Confirmed commercially relevant source gaps

### VX-993 — diabetic peripheral neuropathy
Vertex states that a **Phase 2** study of VX-993 in diabetic peripheral neuropathy is enrolling and is expected to complete enrollment in 2026.

Current Airtable Portfolio search for `VX-993`: **no record**.

Expected discovery outcome: `NEW ASSET` subject to normal identity/ownership QA.

### VX-407 — autosomal dominant polycystic kidney disease
Vertex states that AGLOW is a **Phase 2** study of VX-407 in ADPKD and enrollment is complete.

Current Airtable Portfolio search for `VX-407`: **no record**.

Expected discovery outcome: `NEW ASSET` subject to normal identity/ownership QA.

### atumelnant — Cushing's syndrome
Following completion of the Crinetics acquisition, Vertex describes atumelnant as:
- Phase 3 in congenital adrenal hyperplasia; and
- **Phase 2 in Cushing's syndrome**.

Current Airtable Portfolio contains atumelnant only for congenital adrenal hyperplasia.

Expected discovery outcome: `NEW INDICATION` for existing asset identity, subject to normal indication normalization/ownership QA.

## Important policy edge case exposed by Vertex

Vertex also has active integrated-stage programs such as:
- VX-670 — Phase 1/2 in myotonic dystrophy type 1
- zimislecel — Phase 1/2/3 in type 1 diabetes

`COMMERCIAL_PORTFOLIO_V1` says active Phase 2+ programs are in scope. Therefore the comparator must treat integrated `Phase 1/2`, `Phase 1/2/3` and `Phase 2/3` programs as commercially in scope when the active study includes a Phase 2 component; it must not reduce them to Phase 1 and exclude them.

This is a required comparator normalization fix before the Vertex pilot can be considered fully passed.

## Pilot conclusion

Vertex validates why the discovery layer is commercially useful even for a relatively well-curated biotech account:
- existing coverage is strong for headline assets;
- source-first discovery still identifies meaningful missing Phase 2 assets and new indications;
- acquisitions must feed the same reusable company onboarding/discovery workflow rather than require a manual rebuild.

No master-data writes should occur until comparator hybrid-phase handling is fixed and the pilot classifications are verified.
