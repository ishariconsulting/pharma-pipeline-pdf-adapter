/*
MARKETED PRODUCT CATALOGUE SNAPSHOT PARSER V1.1

Purpose
-------
Parse a trusted source-level snapshot when an authoritative marketed-product
catalogue cannot be retrieved reliably from production infrastructure.

Writes:
- Marketed Product Discovery
- Source Snapshot Imports audit/status fields
- Source Watch catalogue-run audit/status fields

Never writes directly to:
- Portfolio
- Intelligence Update Queue

Input variable:
snapshotRecordId = Airtable record ID from the trigger
*/

const { snapshotRecordId } = input.config();
if (!snapshotRecordId) throw new Error("Missing input variable: snapshotRecordId");

const VERSION = "MARKETED_CATALOGUE_SNAPSHOT_PARSER_V1.2_DISTINCT_SOURCE_FAMILY_NO_PORTFOLIO_REUSE";

const snapshots = base.getTable("tblrKyinUfYZYKP20");
const sourceWatch = base.getTable("tblnYjf3o2j114h5O");
const discovery = base.getTable("tblS4ssiZTa3lEwiC");
const portfolio = base.getTable("tblRCNY70YVbnKOoq");

const SF = {
    sourceWatch: snapshots.getField("fldfbBYQLq99VkKDQ"),
    company: snapshots.getField("fldbIwdVFVyfEfVXc"),
    sourceUrl: snapshots.getField("fld8PoUeiItO5Fe0k"),
    scope: snapshots.getField("fldzokqHOx8JEmK0X"),
    captureMethod: snapshots.getField("fld7J9DCNOdvoMIIX"),
    format: snapshots.getField("fldcf4jw3ixN7v24c"),
    sourceAsOf: snapshots.getField("fldTYo3Y1b9mFlUb8"),
    authoritative: snapshots.getField("fldTHOt4WiEHhwY3d"),
    expectedCount: snapshots.getField("fldgFwF1k9tYZXFlY"),
    raw: snapshots.getField("fldlqimFyi4MiUkxf"),
    fingerprint: snapshots.getField("fldU3I0dD8qOOMsyC"),
    requested: snapshots.getField("fldQNUotqachLZVI8"),
    state: snapshots.getField("fldFW8p9o9bHiAqPh"),
    parsedCount: snapshots.getField("fldAr64ihER5YnUsd"),
    createdCount: snapshots.getField("fldE6HelCwWqYifDQ"),
    updatedCount: snapshots.getField("fldWbHkvoCnRDzC2E"),
    result: snapshots.getField("fldKafJup3nUpCGt9"),
    active: snapshots.getField("fldrgekJ5P41xvzrG")
};

const SWF = {
    company: sourceWatch.getField("fldVFZ4V5UL5vC13u"),
    sourceUrl: sourceWatch.getField("fldwtcZXm6ep56O9h"),
    scanRequested: sourceWatch.getField("fldvP72d2TeoTNtWH"),
    runState: sourceWatch.getField("fldpKdAJEfhtnNyQD"),
    sourceScope: sourceWatch.getField("fldlGJXG15vfUVBwP"),
    lastRun: sourceWatch.getField("fldhbC9V5305jER2A"),
    candidateCount: sourceWatch.getField("fld9Cfkwy2rL8JPJN"),
    fingerprint: sourceWatch.getField("fldhFPwfBrNy8xBkw"),
    lastResult: sourceWatch.getField("fldCdxPOKsLoLHL8V")
};

const DF = {
    key: discovery.getField("fldp2RId6WjvlPvvC"),
    company: discovery.getField("fldOxEWqur73CYvyT"),
    brand: discovery.getField("fldK2qSbnqBqY5v5c"),
    molecule: discovery.getField("fldVD3yr2VNiOB8uH"),
    sourceType: discovery.getField("fldyE5erRcGKDHlPF"),
    sourceUrl: discovery.getField("fldrflitijlzm4oHq"),
    sourceAsOf: discovery.getField("fldZ9KS3QlnOinVHi"),
    catalogueStatus: discovery.getField("fld5obQHWSillzNrc"),
    matchStatus: discovery.getField("fld8QyysP0xuodwCh"),
    matchedPortfolio: discovery.getField("fldj0TBFU3tx37B8J"),
    evidenceNotes: discovery.getField("flderGBtQOMaCXmn0"),
    action: discovery.getField("fldYTbmfAzXaOVUTH"),
    lastChecked: discovery.getField("fldU8hvTUz1nlD3ZD"),
    criticalGap: discovery.getField("fldu7pxPiiwE0SR1g"),
    sourceWatch: discovery.getField("fldxITLPntDoLM6md"),
    segment: discovery.getField("fldijkc5B5OiJUbbT"),
    inclusion: discovery.getField("fldy4RmjGOUxXenmR"),
    scopeRationale: discovery.getField("fldjN28oKE1uWpbwe"),
    productUrl: discovery.getField("fldvzXvXRpC3BQbXd")
};

const PF = {
    company: portfolio.getField("fldjCKvEybJ3M1UlR"),
    brand: portfolio.getField("fldbWcJPf2MKTPd8d"),
    molecule: portfolio.getField("fldKWvXu9zHGcxXWr"),
    aliases: portfolio.getField("fld0alfywULann0AM"),
    status: portfolio.getField("fldFy6gdKyeEjAYps"),
    phase: portfolio.getField("fldvPdloS7fOAz4HP")
};

function linkedIds(record, field) {
    return (record.getCellValue(field) || []).map(x => x.id);
}

function selectName(record, field) {
    return record.getCellValue(field)?.name || null;
}

function norm(v) {
    return String(v || "")
        .toLowerCase()
        .replace(/[™®©]/g, "")
        .replace(/&/g, " and ")
        .replace(/[^a-z0-9]+/g, " ")
        .replace(/\s+/g, " ")
        .trim();
}

function slug(v) {
    return norm(v).replace(/\s+/g, "-").slice(0, 140);
}

function unique(values) {
    return [...new Set(values.filter(Boolean))];
}

function isoDate(v) {
    if (!v) return null;
    return String(v).slice(0, 10);
}

function parseProducts(raw) {
    let payload;
    try {
        payload = JSON.parse(raw);
    } catch (_) {
        throw new Error("Raw Snapshot is not valid JSON.");
    }

    const inputProducts = Array.isArray(payload) ? payload : payload?.products;
    if (!Array.isArray(inputProducts)) {
        throw new Error(
            "Canonical Product List V1 must be a JSON array or an object containing products[]."
        );
    }

    const out = [];
    const seen = new Set();

    for (const item of inputProducts) {
        const brand = String(
            item?.brand || item?.product || item?.name || ""
        ).trim();

        if (!brand) continue;

        const brandNorm = norm(brand);
        if (!brandNorm || seen.has(brandNorm)) continue;
        seen.add(brandNorm);

        out.push({
            brand,
            brandNorm,
            molecule: String(item?.molecule || item?.inn || "").trim() || null,
            productUrl: String(item?.productUrl || item?.url || "").trim() || null
        });
    }

    return out;
}

function isMarketedPortfolio(record) {
    const status = selectName(record, PF.status);
    const phase = selectName(record, PF.phase);
    return status === "Marketed" || phase === "Approved";
}

function portfolioAliases(record) {
    const values = [
        record.getCellValueAsString(PF.brand),
        record.getCellValueAsString(PF.molecule),
        ...(record.getCellValueAsString(PF.aliases) || "").split(/[\n;,|]+/)
    ];

    return unique(
        values.map(norm).filter(x => x.length >= 3)
    );
}

async function runBatches(items, size, fn) {
    for (let i = 0; i < items.length; i += size) {
        await fn(items.slice(i, i + size));
    }
}

async function writeFailClosed(stateName, detail, parsedCount = 0) {
    await snapshots.updateRecordAsync(snapshotRecordId, {
        [SF.requested.id]: false,
        [SF.state.id]: { name: stateName },
        [SF.parsedCount.id]: parsedCount,
        [SF.createdCount.id]: 0,
        [SF.updatedCount.id]: 0,
        [SF.result.id]: JSON.stringify(detail, null, 2)
    });
}

try {
    const snapshot = await snapshots.selectRecordAsync(snapshotRecordId, {
        fields: Object.values(SF)
    });

    if (!snapshot) throw new Error("Snapshot record not found.");

    // Safe even when the preceding automation preparation step already set Running.
    await snapshots.updateRecordAsync(snapshotRecordId, {
        [SF.state.id]: { name: "Running" }
    });

    const sourceIds = linkedIds(snapshot, SF.sourceWatch);
    const companyIds = linkedIds(snapshot, SF.company);

    if (sourceIds.length !== 1) {
        throw new Error("Snapshot must link exactly one Source Watch record.");
    }

    if (companyIds.length !== 1) {
        throw new Error("Snapshot must link exactly one Company.");
    }

    if (snapshot.getCellValue(SF.authoritative) !== true) {
        throw new Error("Authoritative Source Confirmed must be checked.");
    }

    if (snapshot.getCellValue(SF.active) !== true) {
        throw new Error("Snapshot must be Active.");
    }

    if (selectName(snapshot, SF.format) !== "Canonical Product List V1") {
        throw new Error("Snapshot Format must be Canonical Product List V1.");
    }

    const sourceId = sourceIds[0];
    const companyId = companyIds[0];

    const source = await sourceWatch.selectRecordAsync(sourceId, {
        fields: Object.values(SWF)
    });

    if (!source) {
        throw new Error("Linked Source Watch record not found.");
    }

    if (!linkedIds(source, SWF.company).includes(companyId)) {
        throw new Error(
            "Snapshot Company does not match the linked Source Watch company."
        );
    }

    const raw = snapshot.getCellValueAsString(SF.raw);
    const products = parseProducts(raw);
    const expected = Number(snapshot.getCellValue(SF.expectedCount) || 0);

    if (!products.length) {
        throw new Error("Snapshot contains zero distinct product families.");
    }

    // The expected-count gate prevents a partial capture from masquerading as
    // full catalogue coverage.
    if (expected > 0 && products.length !== expected) {
        const detail = {
            version: VERSION,
            snapshotRecordId,
            sourceWatchRecordId: sourceId,
            companyRecordId: companyId,
            expectedItemCount: expected,
            parsedDistinctCount: products.length,
            status: "NEEDS REVIEW - expected-count mismatch",
            discoveryWrites: 0,
            portfolioWrites: 0
        };

        await writeFailClosed("Needs Review", detail, products.length);

        output.set("status", "NEEDS_REVIEW");
        output.set(
            "message",
            "Expected-count mismatch; no Marketed Product Discovery or Portfolio writes made."
        );
        return;
    }

    const portfolioQ = await portfolio.selectRecordsAsync({
        fields: Object.values(PF)
    });

    const marketedPortfolio = portfolioQ.records.filter(
        record =>
            linkedIds(record, PF.company).includes(companyId) &&
            isMarketedPortfolio(record)
    );

    // Exact normalized alias index. No fuzzy matching is used here.
    const portfolioByAlias = new Map();

    for (const record of marketedPortfolio) {
        for (const alias of portfolioAliases(record)) {
            const ids = portfolioByAlias.get(alias) || [];
            ids.push(record.id);
            portfolioByAlias.set(alias, unique(ids));
        }
    }

    const discoveryQ = await discovery.selectRecordsAsync({
        fields: Object.values(DF)
    });

    const companyDiscovery = discoveryQ.records.filter(
        record => linkedIds(record, DF.company).includes(companyId)
    );

    const byKey = new Map();
    const byBrand = new Map();

    for (const record of companyDiscovery) {
        const key = record.getCellValueAsString(DF.key);
        if (key) byKey.set(key, record);

        const brandNorm = norm(record.getCellValueAsString(DF.brand));
        if (brandNorm && !byBrand.has(brandNorm)) {
            byBrand.set(brandNorm, record);
        }
    }

    const sourceAsOf =
        isoDate(snapshot.getCellValueAsString(SF.sourceAsOf)) ||
        new Date().toISOString().slice(0, 10);

    const sourceUrl =
        snapshot.getCellValueAsString(SF.sourceUrl) ||
        source.getCellValueAsString(SWF.sourceUrl);

    const snapshotFingerprint =
        snapshot.getCellValueAsString(SF.fingerprint);

    const nowDate = new Date().toISOString().slice(0, 10);
    const nowIso = new Date().toISOString();

    const creates = [];
    const updates = [];
    let directPortfolioMatchCount = 0;

    for (const product of products) {
        const sourceKey =
            "MKT1|company:" +
            companyId +
            "|product:" +
            slug(product.brand);

        const matchIds = unique([
            ...(portfolioByAlias.get(product.brandNorm) || []),
            ...(product.molecule
                ? (portfolioByAlias.get(norm(product.molecule)) || [])
                : [])
        ]);

        if (matchIds.length) directPortfolioMatchCount++;

        // Discovery identity is source-product-family identity, not Portfolio identity.
        // Distinct source-listed brands/presentations can legitimately map to the same
        // commercial Portfolio asset. Reuse a Discovery row only by exact source key
        // or exact normalized brand family; Portfolio matches remain links only.
        const existing =
            byKey.get(sourceKey) ||
            byBrand.get(product.brandNorm) ||
            null;

        if (existing) {
            const currentSourceLinks = linkedIds(existing, DF.sourceWatch);

            const fields = {
                [DF.key.id]: sourceKey,
                [DF.sourceType.id]: {
                    name: "Country Product Catalogue"
                },
                [DF.sourceUrl.id]: sourceUrl,
                [DF.sourceAsOf.id]: sourceAsOf,
                [DF.catalogueStatus.id]: {
                    name: "Current / Source-listed"
                },
                [DF.lastChecked.id]: nowDate,
                [DF.sourceWatch.id]: unique([
                    ...currentSourceLinks,
                    sourceId
                ]).map(id => ({ id }))
            };

            if (product.productUrl) {
                fields[DF.productUrl.id] = product.productUrl;
            }

            if (
                !existing.getCellValueAsString(DF.molecule) &&
                product.molecule
            ) {
                fields[DF.molecule.id] = product.molecule;
            }

            if (matchIds.length) {
                fields[DF.matchStatus.id] = { name: "Matched" };
                fields[DF.matchedPortfolio.id] = unique([
                    ...linkedIds(existing, DF.matchedPortfolio),
                    ...matchIds
                ]).map(id => ({ id }));

                const currentInclusion =
                    selectName(existing, DF.inclusion);

                if (
                    !currentInclusion ||
                    currentInclusion === "Needs Review"
                ) {
                    fields[DF.inclusion.id] = {
                        name: "Portfolio Required"
                    };
                }

                if (
                    !existing.getCellValueAsString(DF.scopeRationale)
                ) {
                    fields[DF.scopeRationale.id] =
                        "Direct marketed/approved Portfolio representation found for the source-listed product family.";
                }
            }

            // Do not overwrite an existing scope decision, catalogue segment,
            // evidence notes or manually curated brand-family label.
            updates.push({
                id: existing.id,
                fields
            });
        } else {
            const matched = matchIds.length > 0;

            creates.push({
                fields: {
                    [DF.key.id]: sourceKey,
                    [DF.company.id]: [{ id: companyId }],
                    [DF.brand.id]: product.brand,
                    ...(product.molecule
                        ? { [DF.molecule.id]: product.molecule }
                        : {}),
                    [DF.sourceType.id]: {
                        name: "Country Product Catalogue"
                    },
                    [DF.sourceUrl.id]: sourceUrl,
                    [DF.sourceAsOf.id]: sourceAsOf,
                    [DF.catalogueStatus.id]: {
                        name: "Current / Source-listed"
                    },
                    [DF.matchStatus.id]: {
                        name: matched
                            ? "Matched"
                            : "Alias / Needs Review"
                    },
                    ...(matched
                        ? {
                            [DF.matchedPortfolio.id]:
                                matchIds.map(id => ({ id }))
                        }
                        : {}),
                    [DF.evidenceNotes.id]:
                        "Source-listed in authoritative catalogue snapshot. The snapshot parser does not infer indication or Portfolio inclusion for unmatched products.",
                    [DF.action.id]: matched
                        ? "No structural action required; continue downstream indication/market enrichment."
                        : "Classify catalogue segment and Portfolio inclusion in batch; validate marketed identity before any Portfolio creation.",
                    [DF.lastChecked.id]: nowDate,
                    [DF.criticalGap.id]: false,
                    [DF.sourceWatch.id]: [{ id: sourceId }],
                    [DF.segment.id]: {
                        name: "Other / Needs Review"
                    },
                    [DF.inclusion.id]: {
                        name: matched
                            ? "Portfolio Required"
                            : "Needs Review"
                    },
                    [DF.scopeRationale.id]: matched
                        ? "Direct marketed/approved Portfolio representation found."
                        : "Source-listed product family requires scope classification before Portfolio gap routing.",
                    ...(product.productUrl
                        ? {
                            [DF.productUrl.id]:
                                product.productUrl
                        }
                        : {})
                }
            });
        }
    }

    await runBatches(
        creates,
        50,
        async batch => {
            await discovery.createRecordsAsync(batch);
        }
    );

    await runBatches(
        updates,
        50,
        async batch => {
            await discovery.updateRecordsAsync(batch);
        }
    );

    const result = {
        version: VERSION,
        snapshotRecordId,
        sourceWatchRecordId: sourceId,
        companyRecordId: companyId,
        sourceUrl,
        snapshotScope: selectName(snapshot, SF.scope),
        captureMethod: selectName(snapshot, SF.captureMethod),
        parsedDistinctCount: products.length,
        expectedItemCount: expected || null,
        createdDiscoveryCount: creates.length,
        updatedDiscoveryCount: updates.length,
        directPortfolioMatchCount,
        portfolioWrites: 0,
        queueWrites: 0,
        status: "COMPLETE"
    };

    await snapshots.updateRecordAsync(snapshotRecordId, {
        [SF.requested.id]: false,
        [SF.state.id]: { name: "Complete" },
        [SF.parsedCount.id]: products.length,
        [SF.createdCount.id]: creates.length,
        [SF.updatedCount.id]: updates.length,
        [SF.result.id]: JSON.stringify(result, null, 2)
    });

    const sourceWatchUpdate = {
        [SWF.scanRequested.id]: false,
        [SWF.runState.id]: { name: "Complete" },
        [SWF.lastRun.id]: nowIso,
        [SWF.candidateCount.id]: products.length,
        [SWF.lastResult.id]: JSON.stringify(
            {
                ...result,
                retrievalRoute: "SOURCE_SNAPSHOT_IMPORT",
                note:
                    "Catalogue reconciled from trusted source-level fallback. Portfolio and queue remained write-protected."
            },
            null,
            2
        )
    };

    if (selectName(snapshot, SF.scope) === "Full Catalogue") {
        sourceWatchUpdate[SWF.sourceScope.id] = {
            name: "Full Catalogue"
        };
    }

    if (snapshotFingerprint) {
        sourceWatchUpdate[SWF.fingerprint.id] =
            snapshotFingerprint;
    }

    await sourceWatch.updateRecordAsync(
        sourceId,
        sourceWatchUpdate
    );

    output.set("status", "COMPLETE");
    output.set("parsedCandidateCount", products.length);
    output.set("createdDiscoveryCount", creates.length);
    output.set("updatedDiscoveryCount", updates.length);
    output.set(
        "message",
        VERSION +
            ": snapshot parsed and reconciled; no Portfolio writes."
    );
} catch (err) {
    const message = String(
        err?.message || err || "Unknown snapshot parser error"
    ).slice(0, 8000);

    try {
        await snapshots.updateRecordAsync(snapshotRecordId, {
            [SF.requested.id]: false,
            [SF.state.id]: { name: "Error" },
            [SF.result.id]: JSON.stringify(
                {
                    version: VERSION,
                    snapshotRecordId,
                    error: message,
                    portfolioWrites: 0,
                    queueWrites: 0,
                    status: "ERROR - FAIL CLOSED"
                },
                null,
                2
            )
        });
    } catch (_) {}

    throw err;
}
