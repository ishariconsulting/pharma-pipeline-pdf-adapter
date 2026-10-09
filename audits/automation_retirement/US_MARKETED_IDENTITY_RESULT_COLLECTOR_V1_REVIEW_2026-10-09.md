# US Marketed Product Identity Result Collector V1 — first retirement approval review

**Assessment date:** 9 Oct 2026. **Automation:** `wflN5LyvqN8flQPkE` in Airtable base `appzteNR0u0ywm9Zz`. **Status:** OFF / undeployed, valid draft. **Action:** Retire *only after explicit user approval*. No actual removal or disable has taken place.

## Exact current functional contract

- Trigger: scheduled cron every 5 minutes, configured start `2026-09-28T18:55:00Z`. As the automation is OFF this trigger is not operating.
- Only action: custom script whose entire content is the throwing placeholder in the accompanying redacted JSON backup (not a collector). The script has no executable job-query or write actions.
- No recorded runs in retained Airtable history. This does not prove it never ran prior to retention.
- No executable implementation to recover from this draft. Its title/description describe a future collector; its actual code is an explicit instruction to paste an external text file.
- A credential binding exists in Airtable; its identifier and value are deliberately excluded from the GitHub backup. The credential should not be removed/revoked merely because this workflow is retired, as it may be shared.

## Current alternative and dependency check

- **US Marketed Product Identity Enrichment V1** `wflljMPBwKSMEEOwr`, ON. Its existing V1.5 script submits canonical catalogue batches to `/marketed/us-identity/jobs`, waits on `/wait`, reads bounded `/result?offset=0&limit=25` response pages and updates source-listed identity evidence. It does not call this separate collector; no independent collector is required for its demonstrated execution path.
- Live run history of this active enrichment: 47 retained runs = 20 success, 27 failure, latest recorded 2026-09-30 success. A successful run is NOT proof of complete identity evidence or current freshness; keep reliability assessment open.
- Explicit workflow-ID / collector-name references were **not found** in the inspected scripts for eight related *currently ON* marketed catalogue, identity, evidence, gap and queue workflows: `wflRFwBwq0pC8L5FJ`, `wfleGYsCrS6xOJHrf`, `wflgOP27vAZP6iDqH`, `wflzaQD8qAUu2a25b`, `wflcKUhCLedQRCyo0`, `wflfHMCgMxG6gSUb5`, `wfldxAK2QJ3uHB8QA` and `wflljMPBwKSMEEOwr`.
- This is a **bounded dependency check**. It does not claim a full search of all 96 action scripts, all off-platform consumers or past operator runbooks. The collector's actual OFF + throw-only state makes current execution dependence unlikely, but future intended use could have been documented elsewhere.

## Retirement acceptance & rollback

1. Preserve this redacted configuration backup and current automation ID in the GitHub recovery audit, retaining all historical project notes and evidence.
2. Before deletion, confirm no live operational owner intends to complete this as a separate scheduled collector and no pending uncollected background jobs rely on it. It has never implemented the job-resume path in its current script.
3. Ask the user for explicit approval to delete **only** `wflN5LyvqN8flQPkE`, not the active enrichment or adjacent marketed-product flows.
4. After approval, verify configuration/status one last time, remove only this workflow, and verify active enrichment and related workflows remain untouched.
5. Rollback: re-create the OFF stub from redacted metadata/script backup if needed, then restore necessary credential binding manually from Airtable. This is not an automatic perfect-restoration backup; deletion will not preserve the original automation ID or retained run history.

**Recommendation:** A low-functional-loss retirement candidate; approval required. Never auto-delete because its workflow name suggests duplication. Never disable or delete the active identity enrichment.