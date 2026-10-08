# Step 2A Gate 2 — Browser Retrieval Block

Date: 2026-10-08
Scope: Gilead Golden Company — Marketed Product Catalogue
Mode: read-only / zero writes

## Decision

Gate 2 is BLOCKED by a shared browser-retrieval dependency. Do not alter the 29 current Gilead catalogue rows from the failed live retrieval.

## Evidence

- First forced-browser probe: HTTP 408 after ~30s while the non-production canary was still starting.
- Warm retry: canary responded in 376 ms with HTTP 502:
  - FORCED_BROWSER_REQUIRED
  - browser fallback failed (429: no detail)
- Browser worker application code does not intentionally emit HTTP 429 for /fetch/browser.
- No matching /fetch/browser application request was visible in the Render browser-service logs for the warm retry window.
- Existing catalogue safety controls remained fail-closed:
  - Airtable writes: 0
  - Portfolio writes: 0
  - Source Watch writes: 0
  - Discovery writes: 0
  - Completeness-audit writes: 0
- Existing Gilead marketed catalogue remains 29 current source-linked families, 26 assessed/matched, 3 Alias / Needs Review (Ranexa, Atripla, Hepsera).

## Interpretation

The current failure is not evidence that Gilead removed products and is not a parser-only defect. The browser hop is unavailable/rate-limited before a usable rendered catalogue reaches the shared parser. Exact infrastructure origin of the 429 remains unresolved; it must not be inferred as a Gilead source response.

## Recovery control

- The temporary Airtable diagnostic slot was restored from commit cfdff077753e037f3b227c9827abc24587c11ff4.
- Production Render and production Airtable automations were not changed.
- No Portfolio master write occurred.

## Next plan action

Park Gate 2 as a named shared blocker and continue the Golden Company acceptance sequence with Gate 3 — Pipeline / Development Portfolio. Return to this blocker under shared-cause remediation rather than continuing open-ended Gilead retrieval debugging.
