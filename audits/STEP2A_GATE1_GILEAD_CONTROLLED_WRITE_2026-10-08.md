# Step 2A Gate 1 — Gilead controlled structural write

Date: 2026-10-08
Status: WRITE SET APPLIED; IDEMPOTENCE PROVEN; COMPLETENESS STILL NEEDS REVIEW

## Approval scope

User-approved controlled structural write set:
- 6 Company Regional Definitions
- 5 Company Region Market Mapping records
- No updates
- No retirements
- No parent-link writes
- No Company Completeness Audit pass write as part of the approved structural set
- No Portfolio access or writes

Shared writer:
- Branch: `audit/company360-golden-company-gate1-2026-10-08`
- File: `airtable_scripts/company360_operating_structure_writer_v1_approval_gated.js`
- Version: `COMPANY360_OPERATING_STRUCTURE_WRITER_V1.0_APPROVAL_GATED`
- Commit: `f9425b9974327de53b01a3f25430523cb0d60827`
- Syntax check: PASS

## Created definitions

1. Global Patient Solutions — `recfHjQlfv8qhUeTX`
2. Liver Diseases Business Unit / Canada — `rec2rxo9ZlrwmHrGg`
3. HIV Business Unit / Canada — `reccwXfGDr5IYZWCC`
4. Oncology Business Unit / Canada — `recChWwcutPICl7Zb`
5. Virology Business Unit / Switzerland — `recaUGaGFZW0lPBmT`
6. Cell Therapy Business Unit / Switzerland — `recxUasga9yNwOzTa`

## Created market mappings

1. Canada / Liver Diseases Business Unit — `recoQniaQxIZhrnKi`
2. Canada / HIV Business Unit — `recHToEKKysdiEgi1`
3. Canada / Oncology Business Unit — `recx2yDuxWLh3EN7R`
4. Switzerland / Virology Business Unit — `rec8au5JWPhni7Gf3`
5. Switzerland / Cell Therapy Business Unit — `rec0c0T6xeD8NSBjD`

Markets master:
- Canada — `recdPT3DH7EKefjE3`
- Switzerland — `recOARV7Xw5jkh4rL`

## Evidence

Official Gilead sources:
- Global Patient Solutions: https://www.gilead.com/stories/breaking-down-barriers-to-access-in-hiv-and-beyond-a-perspective
- Canada leadership: https://www.gilead.com/en-ca/company/canadian-leadership-team
- Switzerland leadership: https://www.gilead.com/en-ch/unternehmen/unsere-geschaftsleitung

## Idempotence result

Immediate live reread:
- Active Gilead structural definitions: 6
- Gilead market mappings: 5
- Duplicate semantic identities: 0
- Second-pass planned definition creates: 0
- Second-pass planned market mapping creates: 0
- Portfolio writes: 0

## Completeness reassessment

`Gilead|Operating Structure & Business Units` was corrected from the stale pre-write state:
- Status: Needs Review
- Expected Count: 6
- Captured Count: 6
- Evidence Strength: High
- Last Checked: 2026-10-08

Reason: the captured set is current and source-backed, but the evidence contract is explicitly bounded / partial and does not establish an exhaustive worldwide internal hierarchy. Gate 1 therefore remains open under the current completeness semantics.

Next architectural decision: determine whether the shared completeness contract should support a scoped public-evidence pass, rather than requiring an exhaustive private hierarchy that public sources may never disclose.
