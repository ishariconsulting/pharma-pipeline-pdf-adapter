# Retrieval Scalability Gate V1

## Purpose

Freeze the downstream intelligence architecture and solve the remaining source-retrieval bottleneck as a reusable transport layer.

The canonical flow remains:

`Source Watch -> retrieval router -> source adapter/parser -> staging -> resolver -> Intelligence Update Queue -> canonical data`

This change is additive and read-only. It does not add any Airtable or master-data write path.

## Transport policy

The router attempts each source through normal HTTP exactly once.

- `200 + usable content` -> `DIRECT_HTTP`
- `403`, `408`, or `429` -> `BROWSER_REQUIRED`
- `200 + sparse server HTML` -> `BROWSER_REQUIRED`
- other `4xx/5xx` -> fail closed; do not hide a dead/moved source behind browser retry

The browser worker uses headless Chromium through Playwright. It executes JavaScript and returns the same normalized HTML evidence fields used by the direct fetcher: source/final URL, status, title, metadata, visible text, headings, and anchors.

## Guardrails

- Public `http/https` sources only.
- DNS/IP checks reject localhost, private, link-local, reserved, multicast, and unspecified destinations.
- Browser requests are read-only and block media/image/font assets to limit resource use.
- No Airtable, Portfolio, Clinical Trials, Indications, Source Watch, staging, or queue write code exists in the worker.
- Browser escalation is bounded to known retrieval failure classes.
- Browser output must meet a minimum usable-text threshold or the router fails closed.
- Existing `/fetch/html` stays unchanged during validation. New path: `/fetch/routed-html`.

## Production validation

Use two fixed public canaries before switching any production binding:

1. Lilly pipeline: `https://www.lilly.com/science/research-development/pipeline`
2. Bayer pharmaceutical development pipeline: `https://www.bayer.com/en/pharma/development-pipeline`

Acceptance:

- Browser worker health is `200`.
- Lilly canary succeeds with rendered content and expected pipeline terms.
- Bayer canary succeeds through the same worker without company-specific retrieval code.
- Routed HTML returns direct content for an already-working HTML source and browser content only when direct retrieval is blocked/sparse.
- No existing adapter/master-data write path changes.

Only after those gates pass should Source Watch/Adapter Registry bindings be moved from the old direct HTML path to the routed path.
