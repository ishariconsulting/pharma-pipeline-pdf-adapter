# R1C shared source-evidence handoff — bounded code-only repair (2026-10-09)

**Scope:** approved bounded read-only recovery-branch change. No production deployment, new automation, Airtable record write, Candidate/Portfolio promotion, or change to six-case R1C HOLDs.

## Root-cause boundary
- Existing reusable `PIPELINE_SITECORE_SXA_JSON_V1` has proven structurally sound Source Watch keys and fields, but its normalised output omits the publisher's complete source item and hard-codes `study=""` and `trialIds=[]`.
- Existing ClinicalTrials.gov automation holds registry raw arm descriptions, but explicit focal clinical programme scope and source-to-NCT proof are not available as verified, joined evidence in current Gilead Portfolio rows.
- R1C's offline resolver already rejects unsupported programme and arm matches, and 55/55 Gilead read-only status derivations remain `Needs review` until authoritative evidence arrives.

## Implemented changes on the existing recovery branch
1. `source_evidence_contract.py` is a reusable, standard-library-only, **network-free, write-free** original-publisher-item evidence envelope. It stores the exact detached JSON source item (including the original HTML and any issuer metadata), readable original HTML text, stable source key and stable-key-present flag, provenance page URL, explicit retrieval timestamp, and SHA256 of canonically serialized original item.
2. `sitecore_sxa_pipeline_extension.py`: additive `include_source_evidence` flag on the existing authenticated **read-only** `GET /extract/generic/sitecore-sxa-pipeline`; defaults to false so current callers receive **unchanged existing row shape**. When opted in, each row carries `sourceEvidence`. Existing pipeline row IDs, comparator classifications, deduplication, phase, `study=""`, and `trialIds=[]` remain unchanged.
3. An explicit HTTPS ClinicalTrials.gov **anchor hyperlink on a source item** is retained only as `observedRegistryLinks[]` with `OBSERVED_LINK_NOT_VERIFIED`. A naked NCT text string, URL from an unrelated host, insecure HTTP or search URL is not converted into a structured trial relation. No `programmeToNctVerified`, `programmeScopeVerified`, `focalArmVerified` or write eligibility can be set true from this output.
4. `sourceAsOf` remains null even if arbitrary source metadata contains dates: retrieval time is not publication date. Exact source-issued publication date requires separate authoritative field contract review.
5. New offline synthetic tests: `test_source_evidence_contract.py` (nine pure Python tests, run locally and PASS), `test_sitecore_source_evidence.py` (three adapter-level mock-HTTP tests added; **not yet run against full Codespace import stack**). Do not represent synthetic fixtures as observed live pharma source results.

## Acceptance and next validation
- The nine pure helper tests passed offline. The three adapter tests plus existing **81-test** R1C suite require a proper repo environment on the recovery branch. Suggested read-only commands after pulling the branch:
```bash
git pull --ff-only
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest -v test_source_evidence_contract test_sitecore_source_evidence test_r1c_shared_lineage
```
- **Important:** even if these tests all PASS, the output merely preserves evidence. It does not establish that Gilead's current official items contain explicit NCT references, that the pipeline was refreshed, that an experimental arm is linked to Portfolio or that the full 53-key R1C matrix is validated. Gilead Gate 3 and Gate 7 remain GAP; R1C BLOCKED pending observed current source evidence + authorised clinical-scope assertions.
- After tests, any read-only evidence capture should be separately controlled, source-access safe (rate limits / IP reputation), and limited to already authorised sources. Do not turn on OFF audit scripts or deploy a new route without user approval.

**Only GitHub recovery branch files updated.** No master-data writes or production deployment were performed.
