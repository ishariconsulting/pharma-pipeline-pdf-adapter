"use strict";

/* Executes the *actual*, otherwise unpublished Airtable V4.4.4 candidate
 * preparation block against isolated record fixtures. No Airtable network/API
 * access; there are no real table writes. */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const full = fs.readFileSync(
    path.join(__dirname, "airtable_scripts/portfolio_discovery_staging_v4_4_4_draft.txt"),
    "utf8"
);
assert.ok(full.includes("DEFERRED_TRANSIENT_HTTP_503") === false); // dynamic HTTP code
const first = full.indexOf("function mappedMatchMethod(value) {");
const last = full.indexOf("\nconst createdIds = [];", first);
assert.ok(first >= 0 && last > first, "exact candidate preparation section must exist");
const candidateBlock = full.slice(first, last) +
    "\nglobalThis.__canary = { creates, updates, stageCandidates };\n";

const names = [
    "id", "company", "sourceWatch", "family", "classification", "reviewStatus",
    "asset", "molecule", "devCode", "brand", "indication", "canonicalIndication",
    "phase", "programStatus", "owner", "partners", "sourceRecord", "sourceUrl",
    "existingMatch", "matchMethod", "confidence", "decision", "basis",
    "reason", "evidence", "latestStagingEvidence", "batch", "firstDetected",
    "lastChecked", "sourceScope", "programmeGate",
];
const cf = Object.fromEntries(names.map(k => [k, { id: k }]));
const clean = v => String(v ?? "").trim();
const norm = v => clean(v).toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();

function existing(key, status, classification, gate, scope, marker) {
    return {
        id: "existing-" + key,
        values: {
            id: key,
            reviewStatus: status,
            classification,
            programmeGate: gate,
            sourceScope: scope,
            reason: marker + " CURATED REVIEW. Do not replace.",
            evidence: marker + " CROSS-SOURCE EVIDENCE. Do not replace.",
        },
    };
}
const previous = [
    existing("regn-trev", "Needs Review", "POSSIBLE DUPLICATE",
        "Evidence Captured – Scope Unresolved", "Asset / phase umbrella", "TREVOGRUMAB"),
    existing("regn-cenv", "Needs Review", "NEW INDICATION",
        "Evidence Captured – Scope Unresolved", "Asset / phase umbrella", "CENVACIBART"),
    existing("regn-odro", "Needs Review", "NEW INDICATION",
        "Evidence Captured – Scope Unresolved", "Asset / phase umbrella", "ODRONEXTAMAB"),
    existing("reviewed-exclusion", "Reviewed - Exclude", "EXCLUDED BY RULE",
        "Out of Programme Scope", "Uncertain", "ASTRAZENECA PARSER ARTEFACT"),
];
const snapshot = new Map(previous.map(r => [r.values.id, JSON.stringify(r.values)]));
const byId = new Map(previous.map(r => [r.values.id, r]));

function candidate(key, asset, sourceRecordId, classification, indication) {
    return {
        discoveryCandidateId: key, sourceRecordId,
        asset, molecule: asset, developmentCode: "", brand: "",
        indication, phase: "Phase 2", programStatus: "Active",
        sourceUrl: "https://example.org/official/pipeline",
        sponsorOwner: "Example Pharma", partners: [],
        existingPortfolioRecordIds: [], matchMethod: "No Match",
        matchConfidence: "Low", classification,
        commercialInclusionDecision: "Include",
        inclusionBasis: ["Active Phase 2+"],
        matchEvidence: ["Latest source comparison"],
        fieldDeltas: [], reviewReason: "Latest machine reason",
    };
}
const inputs = [
    candidate("regn-trev", "TREVOGRUMAB", "card-41", "NEW ASSET", "Obesity"),
    candidate("regn-cenv", "CENVACIBART", "card-30", "NEW INDICATION", "Thrombosis"),
    candidate("regn-odro", "ODRONEXTAMAB", "card-55", "NEW INDICATION", "Lymphoma multiple lines and settings"),
    candidate("reviewed-exclusion", "PARSER-ARTEFACT", "card-77", "NEW ASSET", "Synthetic title"),
    candidate("new-record", "FUTURE-ASSET", "card-99", "NEW ASSET", "Distinct condition"),
];

const context = {
    comparison: { version: "Comparator V1.6", candidates: inputs },
    cf,
    clean, norm,
    existingById: byId,
    selectName: (r, f) => r.values[f.id] ?? "",
    semanticReviewBySourceRecordId: new Map(),
    sourceContextByRecordId: new Map([
        ["card-41", { trialIds: [] }],
        ["card-30", { trialIds: [] }],
        ["card-55", { trialIds: [], description: "multiple lines and settings" }],
    ]),
    adapterProfile: "PIPELINE_GENERIC_HTML_V1",
    companyId: "recExampleCompany",
    sourceWatchRecordId: "recExampleSource",
    batchRunId: "READ_ONLY_CANARY",
    Date, JSON, Set, Map, Array,
};
vm.runInNewContext(candidateBlock, context, { timeout: 2000 });

const { creates, updates } = context.__canary;
assert.equal(updates.length, 4, "four existing rows must update, never create duplicates");
assert.equal(creates.length, 1, "one novel fixture gets a fresh candidate");
const upd = new Map(updates.map(u => [u.id, u.fields]));

for (const record of previous) {
    const changed = upd.get(record.id);
    assert.ok(changed, record.id + " must be restaged");
    assert.equal(Object.hasOwn(changed, cf.reason.id), false,
        record.id + ": curated review reason cannot be overwritten");
    assert.equal(Object.hasOwn(changed, cf.evidence.id), false,
        record.id + ": cross-source evidence cannot be overwritten");
    assert.equal(Object.hasOwn(changed, cf.sourceScope.id), false,
        record.id + ": existing source scope must be retained");
    assert.equal(Object.hasOwn(changed, cf.programmeGate.id), false,
        record.id + ": programme gate must not be changed by staging");
    assert.match(changed[cf.latestStagingEvidence.id], /Latest source comparison/);
    assert.equal(JSON.stringify(record.values), snapshot.get(record.values.id),
        "original fixture must remain untouched");
}

const trev = upd.get("existing-regn-trev");
assert.equal(trev[cf.classification.id].name, "POSSIBLE DUPLICATE",
    "known unresolved source/asset collision cannot revert to New Asset");
assert.equal(trev[cf.reviewStatus.id].name, "Needs Review");
for (const k of ["regn-cenv", "regn-odro"]) {
    const row = upd.get("existing-" + k);
    assert.equal(row[cf.reviewStatus.id].name, "Needs Review");
}
const excluded = upd.get("existing-reviewed-exclusion");
assert.equal(excluded[cf.reviewStatus.id].name, "Reviewed - Exclude",
    "reviewed exclusion must remain reviewed");
assert.equal(excluded[cf.classification.id].name, "EXCLUDED BY RULE",
    "parser artefact cannot become a new asset");
assert.notEqual(excluded[cf.decision.id].name, "Include",
    "reviewed out-of-programme source must not be marked commercially Include");
const fresh = creates[0].fields;
assert.ok(fresh[cf.reason.id] && fresh[cf.evidence.id]);
assert.ok(fresh[cf.latestStagingEvidence.id]);
assert.equal(fresh[cf.reviewStatus.id].name, "New");

// Isolate and execute the exact transient-HTTP request helper.
const requestStart = full.indexOf("async function jsonRequest(url, options = {}, maxAttempts = 2) {");
const requestEnd = full.indexOf("\nconst swf = {", requestStart);
assert.ok(requestStart >= 0 && requestEnd > requestStart);
const asyncRequestCode = full.slice(requestStart, requestEnd) +
    "\nglobalThis.__jsonRequest = jsonRequest;";
async function transientHttpTests() {
    for (const code of [429, 503]) {
        let called = 0;
        const ctx = {
            Set, Promise, Error, JSON,
            fetch: async () => {
                called++;
                return { status: code, headers: { get: () => "30" }, text: async () => "{}" };
            },
        };
        vm.runInNewContext(asyncRequestCode, ctx, { timeout: 2000 });
        let rejected = false;
        try {
            await ctx.__jsonRequest("https://example.org/", {}, 2);
        } catch (error) {
            rejected = true;
            assert.match(error.message, /DEFERRED_TRANSIENT_HTTP_/);
            assert.equal(called, 1, "429/503 must not immediately retry");
        }
        assert.ok(rejected, code + " was not deferred");
    }
}

transientHttpTests()
    .then(() => console.log(
        "PASS: existing notes/evidence/gates/scopes preserved, new candidate correctly prepared, transient HTTP deferred"
    ))
    .catch(err => {
        console.error(err);
        process.exitCode = 1;
    });
