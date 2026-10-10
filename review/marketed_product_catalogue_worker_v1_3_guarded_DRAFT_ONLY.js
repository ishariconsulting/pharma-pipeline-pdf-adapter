/* REVIEW COPY ONLY. DO NOT PASTE, PUBLISH OR ENABLE IN AIRTABLE WITHOUT EXPLICIT APPROVAL.\nCaptured from published Marketed Product Catalogue Discovery Worker V1.2 in base appzteNR0u0ywm9Zz;\nunchanged production worker remains running. Opt-in PR8 router is separate and also unmerged.\n*/\n/*
Marketed Product Catalogue Discovery Worker V1.2
COMPANY-AGNOSTIC / SOURCE-WATCH-DRIVEN / FAIL-CLOSED

Purpose
-------
- Read one validated active Source Watch Product / Medicines Page.
- Extract source-listed marketed product families from deterministic product-detail links.
- Reconcile them against current MARKETED Portfolio baselines.
- Upsert one Marketed Product Discovery row per company x canonical product family.
- Preserve existing strategic/source evidence and human scope decisions.
- Never create or update Portfolio directly.
- Update the company's Marketed Product Catalogue completeness check so a top-product
  sample cannot masquerade as full catalogue coverage.

Input
-----
sourceWatchRecordId = triggering Source Watch record id

Secret
------
adapterApiKey = existing external HTML fallback secret
*/

const VERSION = "MARKETED_CATALOGUE_DISCOVERY_WORKER_V1.3_R5_VERIFIED_BASELINE_PREWRITE_DRAFT_ONLY";
const ADAPTER_BASE_URL = "https://pharma-pipeline-pdf-adapter.onrender.com";

const cfg = input.config();
const sourceWatchRecordId = String(cfg.sourceWatchRecordId || "").trim();
if (!sourceWatchRecordId) throw new Error("sourceWatchRecordId is blank.");

const sourceWatchTable = base.getTable("Source Watch");
const discoveryTable = base.getTable("Marketed Product Discovery");
const portfolioTable = base.getTable("Portfolio");
const companiesTable = base.getTable("Companies");
const auditTable = base.getTable("Company Completeness Audit");

function field(table, name, required = true) {
    let f = null;
    try { f = table.getField(name); } catch (_) {}
    if (!f && required) throw new Error(`Required field missing: ${table.name}.${name}`);
    return f;
}
function clean(v) {
    return v === null || v === undefined ? "" : String(v).replace(/\s+/g, " ").trim();
}
function norm(v) {
    return clean(v)
        .toLowerCase()
        .normalize("NFKD")
        .replace(/[\u0300-\u036f]/g, "")
        .replace(/[®™©]/g, "")
        .replace(/[–—‑−]/g, "-")
        .replace(/[^a-z0-9]+/g, " ")
        .replace(/\s+/g, " ")
        .trim();
}
function linkIds(record, f) {
    const v = record.getCellValue(f);
    return Array.isArray(v) ? v.map(x => x && x.id).filter(Boolean) : [];
}
function selectName(record, f) {
    const v = record.getCellValue(f);
    return v && v.name ? clean(v.name) : clean(record.getCellValueAsString(f));
}
function text(record, f) {
    try { return clean(record.getCellValueAsString(f)); } catch (_) { return ""; }
}
function fnv1a(str) {
    let h = 0x811c9dc5;
    const s = String(str || "");
    const limit = Math.min(s.length, 300000);
    for (let i = 0; i < limit; i++) {
        h ^= s.charCodeAt(i);
        h = Math.imul(h, 0x01000193);
    }
    return ("00000000" + (h >>> 0).toString(16)).slice(-8);
}
function decodeEntities(s) {
    return String(s || "")
        .replace(/&nbsp;/gi, " ")
        .replace(/&amp;/gi, "&")
        .replace(/&quot;/gi, '"')
        .replace(/&#39;/gi, "'")
        .replace(/&apos;/gi, "'")
        .replace(/&lt;/gi, "<")
        .replace(/&gt;/gi, ">");
}
function stripHtml(html) {
    return decodeEntities(String(html || "")
        .replace(/<!--[\s\S]*?-->/g, " ")
        .replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, " ")
        .replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi, " ")
        .replace(/<noscript\b[^>]*>[\s\S]*?<\/noscript>/gi, " ")
        .replace(/<svg\b[^>]*>[\s\S]*?<\/svg>/gi, " ")
        .replace(/<[^>]+>/g, " "))
        .replace(/\s+/g, " ")
        .trim();
}
function absoluteUrl(href, baseUrl) {
    const h = decodeEntities(clean(href));
    if (!h || h.startsWith("#") || /^(javascript:|mailto:|tel:)/i.test(h)) return "";
    try { return new URL(h, baseUrl).href; } catch (_) { return ""; }
}
function extractTitle(html) {
    const m = String(html || "").match(/<title[^>]*>([\s\S]*?)<\/title>/i);
    return m ? stripHtml(m[1]).slice(0, 300) : "";
}
function extractHeadingsFromHtml(html) {
    const out = [];
    const re = /<h([1-4])\b[^>]*>([\s\S]*?)<\/h\1>/gi;
    let m;
    while ((m = re.exec(String(html || ""))) && out.length < 200) {
        const value = stripHtml(m[2]).slice(0, 240);
        if (!value || /\{\{|\}\}/.test(value)) continue;
        out.push({level:Number(m[1]), text:value});
    }
    return out;
}
function classifyBlocked(html, title, visibleText) {
    const hay = `${title || ""} ${(visibleText || "").slice(0, 5000)} ${(html || "").slice(0, 12000)}`.toLowerCase();
    const indicators = [
        "verify you are human", "checking your browser", "access denied", "request blocked",
        "enable javascript and cookies to continue", "attention required! | cloudflare", "just a moment..."
    ];
    for (const x of indicators) if (hay.includes(x)) return x;
    const rawChallenge = hay.includes("cf-chl-") || hay.includes("challenge-platform");
    if (rawChallenge && clean(visibleText).length < 800) return "challenge shell";
    return "";
}
function canonicalBrand(label) {
    return clean(label)
        .replace(/[®™©]/g, "")
        .replace(/\s+for\s+injection\b.*$/i, "")
        .replace(/\s+(tablets?|capsules?|injection|injectable|solution|suspension|powder)\b.*$/i, "")
        .replace(/\s+/g, " ")
        .trim();
}
function brandKey(label) {
    return norm(canonicalBrand(label));
}
// R5_CATALOGUE_ADMISSION_START — isolated draft extension to the published worker.
// Markers come ONLY from the separately vetted, source-scoped snapshot.
// They help choose transport, but they never certify catalogue completeness.
function r5MarkerContract(snapshot) {
    if (!snapshot || snapshot.authoritative !== true || !Array.isArray(snapshot.products))
        throw new Error("R5_CATALOGUE_INTEGRITY_HOLD:AUTHORITATIVE_SNAPSHOT_REQUIRED");
    const unique = [];
    const seen = new Set();
    for (const row of snapshot.products) {
        const brand = clean(typeof row === "string" ? row : row && row.brand);
        const key = brand.toLowerCase();
        if (!brand || brand.length < 3 || brand.length > 80 || brand.includes(",")) continue;
        if (seen.has(key)) continue;
        seen.add(key);
        unique.push(brand);
    }
    if (unique.length < 3)
        throw new Error("R5_CATALOGUE_INTEGRITY_HOLD:INSUFFICIENT_SOURCE_MARKERS");
    // Distribute up to 12 markers across the declared source order, rather
    // than relying only on the first products in the snapshot.
    const count = Math.min(12, unique.length);
    const markers = Array.from({length:count}, (_,i) =>
        unique[Math.floor(i * (unique.length - 1) / (count - 1))]);
    return {markers, minHits:3};
}
function r5SourceMarkerHits(page, contract) {
    const content = [
        clean(page.visibleText),
        ...(page.headings || []).map(x => clean(x && x.text)),
        ...(page.anchors || []).map(x => clean(x && (x.label || x.text)))
    ].join(" ").toLowerCase();
    return contract.markers.filter(marker => {
        const escaped = marker.toLowerCase().replace(/[.*+?^${}()|[\]\\]/g, "\\// R5_CATALOGUE_ADMISSION_START — isolated draft extension to the published worker.
");
        return new RegExp("(^|\\W)" + escaped + "(?!\\w)").test(content);
    }).length;
}
// It does NOT establish official source truth; it prevents unverified page
// extraction from overwriting a previously reviewed source-level baseline.
function r5CatalogueAdmission(snapshot, candidates, finalUrl, watchedUrl) {
    function hold(code) { throw new Error("R5_CATALOGUE_INTEGRITY_HOLD:" + code); }
    if (!snapshot || snapshot.authoritative !== true) hold("AUTHORITATIVE_SNAPSHOT_REQUIRED");
    if (snapshot.scope !== "Full Catalogue" && snapshot.scope !== "Partial Catalogue") hold("SNAPSHOT_SCOPE_NOT_QUALIFIED");
    if (!sameHost(finalUrl || watchedUrl, watchedUrl)) hold("SOURCE_ORIGIN_MISMATCH");
    if (!Array.isArray(snapshot.products) || !snapshot.products.length) hold("BASELINE_PRODUCT_LIST_MISSING");
    if (!Number.isInteger(snapshot.expectedCount) || snapshot.expectedCount < 1
            || snapshot.expectedCount !== snapshot.products.length) hold("INDEPENDENT_BASELINE_COUNT_INVALID");
    const baseline = new Set();
    for (const p of snapshot.products) {
        const k = brandKey(typeof p === "string" ? p : p && p.brand);
        if (!k || baseline.has(k)) hold("BASELINE_PRODUCT_IDENTITY_MISSING_OR_DUPLICATE");
        baseline.add(k);
    }
    const current = new Set();
    for (const c of candidates) {
        const k = clean(c && c.key);
        if (!k || current.has(k)) hold("LIVE_PRODUCT_IDENTITY_MISSING_OR_DUPLICATE");
        current.add(k);
    }
    if (!current.size || current.size < snapshot.expectedCount) hold("LIVE_CATALOGUE_SHORTER_THAN_VERIFIED_BASELINE");
    for (const k of baseline) if (!current.has(k)) hold("VERIFIED_BASELINE_PRODUCT_ABSENT");
    if (current.size !== baseline.size) hold("NEW_PRODUCT_IDENTITIES_REQUIRE_SOURCE_REVIEW");
    // Scope is controlled by verified source evidence, not inferred from page
    // title, source brand name or current extracted count.
    return {
        status: "IDENTITY_PARITY_PREVIEW",
        scope: snapshot.scope,
        baselineAsOf: snapshot.asOf,
        baselineCount: snapshot.expectedCount,
        liveCount: current.size,
        fullCatalogueEligible: snapshot.scope === "Full Catalogue"
    };
}

async function r5GetQualifiedSnapshot(sw, sourceWatchTable) {
    const ids = linkIds(sw, field(sourceWatchTable, "Source Snapshot Imports"));
    if (!ids.length) throw new Error("R5_CATALOGUE_INTEGRITY_HOLD:AUTHORITATIVE_SNAPSHOT_REQUIRED");
    const table = base.getTable("Source Snapshot Imports");
    const f = {
        link: field(table, "Source Watch"),
        authoritative: field(table, "Authoritative Source Confirmed"),
        expected: field(table, "Expected Item Count"),
        raw: field(table, "Raw Snapshot"),
        scope: field(table, "Snapshot Scope"),
        asOf: field(table, "Source As Of")
    };
    const accepted = [];
    for (const id of ids) {
        const row = await table.selectRecordAsync(id);
        if (!row || !linkIds(row, f.link).includes(sw.id)) continue;
        if (row.getCellValue(f.authoritative) !== true) continue;
        const asOf = text(row, f.asOf);
        const scope = selectName(row, f.scope);
        let data;
        try { data = JSON.parse(text(row, f.raw)); }
        catch (_) { throw new Error("R5_CATALOGUE_INTEGRITY_HOLD:TRUSTED_SNAPSHOT_INVALID_JSON"); }
        accepted.push({
            id: row.id, asOf, scope, authoritative: true,
            expectedCount: Number(row.getCellValue(f.expected)),
            products: data.products
        });
    }
    if (!accepted.length) throw new Error("R5_CATALOGUE_INTEGRITY_HOLD:AUTHORITATIVE_SNAPSHOT_REQUIRED");
    accepted.sort((a,b)=> (b.asOf || "").localeCompare(a.asOf || ""));
    if (accepted.length > 1 && accepted[0].asOf === accepted[1].asOf)
        throw new Error("R5_CATALOGUE_INTEGRITY_HOLD:AMBIGUOUS_SAME_DATE_BASELINES");
    return accepted[0];
}
// R5_CATALOGUE_ADMISSION_END

function looksGenericNav(label) {
    return /^(products?|product list|medicines?|our medicines|all medicines|current medicines|prescription products|vaccines?|immunization|learn more|read more|view all|details?|home|contact|patient information|prescribing information|safety information)$/i.test(clean(label));
}
function pathDepth(url) {
    try { return new URL(url).pathname.split("/").filter(Boolean).length; } catch (_) { return 0; }
}
function sameHost(a, b) {
    try { return new URL(a).hostname.replace(/^www\./, "").toLowerCase() === new URL(b).hostname.replace(/^www\./, "").toLowerCase(); } catch (_) { return false; }
}
function brandLike(label) {
    const s = clean(label);
    if (!s || s.length < 2 || s.length > 120) return false;
    if (looksGenericNav(s)) return false;
    if (/[®™]/.test(s)) return true;
    const letters = s.replace(/[^A-Za-z]/g, "");
    if (letters.length >= 3 && letters === letters.toUpperCase()) return true;
    if (/^[A-Z][A-Za-z0-9+\-]*(?:\s+[A-Z][A-Za-z0-9+\-]*){0,4}$/.test(s) && !/^(Science|About|Products|Medicines|Patients|Pipeline|Research|News|Media|Careers)$/i.test(s)) return true;
    return false;
}
function productAnchorScore(a, sourceUrl) {
    const label = clean(a.label || a.text);
    const url = clean(a.url);
    if (!label || !url || looksGenericNav(label) || url === sourceUrl) return -999;
    if (!sameHost(url, sourceUrl)) return -999;
    const p = (() => { try { return new URL(url).pathname.toLowerCase(); } catch (_) { return ""; } })();
    if (/medicine-safety|how-drugs-are-made|product-contacts?|distributors?|clinical-trials?|stories?|newsroom|press-releases?|careers?|about|contact/.test(p)) return -999;
    let score = 0;
    if (/\/product-detail\//.test(p)) score += 12;
    if (/\/(products?|medicines?)\//.test(p) && pathDepth(url) > pathDepth(sourceUrl)) score += 5;
    if (/\/(brand|brands|treatments?)\//.test(p)) score += 4;
    if (brandLike(label)) score += 4;
    if (/[®™]/.test(label)) score += 2;
    if (brandKey(label).length < 2) score -= 10;
    return score;
}
function moleculeFromTail(tail) {
    const t = clean(tail);
    const m = t.match(/^\(([^()]{2,180})\)/);
    if (!m) return "";
    const x = clean(m[1]);
    if (/^(opens?|see|view|learn|read)\b/i.test(x)) return "";
    return x;
}
function extractAnchorsFromHtml(html, baseUrl) {
    const out = [];
    const re = /<a\b[^>]*href=["']([^"']+)["'][^>]*>([\s\S]*?)<\/a>/gi;
    let m;
    while ((m = re.exec(String(html || ""))) && out.length < 2500) {
        const url = absoluteUrl(m[1], baseUrl);
        const label = stripHtml(m[2]).slice(0, 180);
        if (!url || !label || /\{\{|\}\}/.test(label)) continue;
        const tail = stripHtml(String(html || "").slice(re.lastIndex, re.lastIndex + 360));
        out.push({label, url, molecule: moleculeFromTail(tail)});
    }
    return out;
}
function normalizeExternalAnchors(anchors) {
    return (Array.isArray(anchors) ? anchors : []).map(a => ({
        label: clean(a.label || a.text),
        url: clean(a.url),
        molecule: clean(a.molecule)
    })).filter(a => a.label && a.url);
}
function normalizeExternalHeadings(headings) {
    return (Array.isArray(headings) ? headings : []).map(h => ({
        level: Number(h && h.level || 0),
        text: clean(h && h.text)
    })).filter(h => h.text && h.level >= 1 && h.level <= 4);
}
function looksSectionHeading(label) {
    const n = norm(label);
    if (!n) return true;
    return /^(oncology|hematology|haematology|cardiovascular|cardiovascular renal and metabolism|respiratory and immunology|infectious disease|infectious diseases|rare disease|rare diseases|neurology|neuroscience|immunology|vaccines|vaccine products|prescription products|marketed products|legacy brands|our medicines|our products|medicines|products|diabetes|transplant|rare blood disorders|cardiovascular disease|patient support|medical resources|report side effects|report side effects or product quality complaints)$/.test(n);
}
function headingBrand(label) {
    let s = clean(label).replace(/[®™©]/g, "");
    s = s.replace(/\s*[\(\[][^\)\]]{1,220}[\)\]].*$/i, "").trim();
    const commaParts = s.split(/\s*,\s*/).map(clean).filter(Boolean);
    if (commaParts.length > 1) {
        const first = canonicalBrand(commaParts[0]);
        return first ? first + " family" : "";
    }
    s = s.replace(/\s+(XR|XL|CR|ER|SR|MR|pMDI|Respules|Turbuhaler)\s*$/i, "").trim();
    return canonicalBrand(s);
}
function moleculeFromHeading(label, followingText) {
    const raw = clean(label);
    let m = raw.match(/\(([^()]{2,180})\)/);
    if (!m) m = raw.match(/\[([^\[\]]{2,220})\]/);
    if (m) {
        const inside = clean(m[1]);
        if (inside && !/^(opens?|see|view|learn|read|including|boxed warning)/i.test(inside)) return inside;
    }
    let next = clean(followingText);
    next = next.split(/\b(?:U\.S\.\s+full\s+prescribing|Prescribing Information|Medication Guide|Patient Information|Product website|Pricing information|Instructions for use|HCP website|Patient website)\b/i)[0].trim();
    if (!next || next.length > 180) return "";
    if (/[.!?]\s/.test(next) || /^(please|below|for further|our |this |information|learn |report |healthcare )/i.test(next)) return "";
    if (/^(oncology|cardiovascular|respiratory|immunology|infectious|rare disease|vaccines?)\b/i.test(next)) return "";
    return next;
}
function headingCandidates(headings, visibleText, sourceUrl) {
    const hs = normalizeExternalHeadings(headings);
    const textValue = clean(visibleText);
    const positions = [];
    let cursor = 0;
    for (const h of hs) {
        let p = textValue.indexOf(h.text, cursor);
        if (p < 0) p = textValue.indexOf(h.text);
        positions.push(p);
        if (p >= 0) cursor = p + h.text.length;
    }
    const out = [];
    for (let i = 0; i < hs.length; i++) {
        const h = hs[i];
        if (h.level < 2 || h.level > 4 || looksGenericNav(h.text) || looksSectionHeading(h.text)) continue;
        const p = positions[i];
        let following = "";
        if (p >= 0) {
            let end = textValue.length;
            for (let j = i + 1; j < hs.length; j++) {
                if (positions[j] > p) { end = positions[j]; break; }
            }
            following = textValue.slice(p + h.text.length, end).trim();
        }
        const molecule = moleculeFromHeading(h.text, following);
        const strongBrand = /[®™]/.test(h.text) || /[\(\[]/.test(h.text) || brandLike(h.text);
        if (!strongBrand) continue;
        if (!/[®™]/.test(h.text) && !/[\(\[]/.test(h.text) && !molecule) continue;
        const display = headingBrand(h.text);
        const key = brandKey(display);
        if (!display || !key || looksSectionHeading(display)) continue;
        out.push({
            key, display, rawLabel:h.text, url:sourceUrl, molecule,
            score: molecule ? 10 : 8
        });
    }
    return out;
}
function dedupeCandidates(raw, sourceUrl) {
    const byKey = new Map();
    for (const a of raw) {
        const score = productAnchorScore(a, sourceUrl);
        if (score < 7) continue;
        const display = canonicalBrand(a.label);
        const key = brandKey(display);
        if (!key) continue;
        const candidate = {
            key,
            display,
            rawLabel: clean(a.label),
            url: clean(a.url),
            molecule: clean(a.molecule),
            score
        };
        const existing = byKey.get(key);
        if (!existing || candidate.score > existing.score || (!existing.molecule && candidate.molecule)) byKey.set(key, candidate);
    }
    return [...byKey.values()].sort((a,b) => a.display.localeCompare(b.display));
}
function inferSourceScope(sourceName, pageTitle, url) {
    const s = `${sourceName} ${pageTitle} ${url}`.toLowerCase();
    if (/vaccines?\s*&?\s*immuni[sz]ation|vaccine products?|oncology products?|rare disease products?|business unit|franchise/.test(s)) return "Franchise / Business Unit";
    if (/prescription products?/.test(s) && !/all prescription/.test(s)) return "Partial Catalogue";
    if (/product list|products list|all medicines|all products|current medicines|current products|our medicines catalogue|global medicines catalogue/.test(s)) return "Full Catalogue";
    return "Unknown / Needs Review";
}
function inferDiscoverySourceType(sourceName, url) {
    const s = `${sourceName} ${url}`.toLowerCase();
    if (/\/uk\/|\/us\/|united kingdom|\buk\b|united states|\bus\b/.test(s)) return "Country Product Catalogue";
    return "Other Official Source";
}
function inferSegment(candidate) {
    const b = norm(candidate.display);
    const m = norm(candidate.molecule);
    if (/vaccine|immuni[sz]ation/.test(m) || /vaccine/.test(b)) return "Vaccine / Immunisation";
    if (m && b === m) return "Commodity Generic / Utility";
    if (m && (b === m.replace(/\b(hydrochloride|sodium|sulfate|acetate|mesylate|tartrate|phosphate)\b/g, "").replace(/\s+/g, " ").trim())) return "Commodity Generic / Utility";
    return "Other / Needs Review";
}
function getSecret(name) {
    try { return clean(input.secret(name)); } catch (_) { return ""; }
}

const swf = {
    company: field(sourceWatchTable, "Company"),
    name: field(sourceWatchTable, "Source Name"),
    type: field(sourceWatchTable, "Source Type"),
    url: field(sourceWatchTable, "Source URL"),
    monitoring: field(sourceWatchTable, "Monitoring Status"),
    binding: field(sourceWatchTable, "Adapter Binding Status"),
    retrieval: field(sourceWatchTable, "Retrieval Mode", false),
    requested: field(sourceWatchTable, "Marketed Catalogue Scan Requested"),
    runState: field(sourceWatchTable, "Marketed Catalogue Run State"),
    scope: field(sourceWatchTable, "Marketed Catalogue Source Scope"),
    lastRun: field(sourceWatchTable, "Marketed Catalogue Last Run"),
    count: field(sourceWatchTable, "Marketed Catalogue Candidate Count"),
    fingerprint: field(sourceWatchTable, "Marketed Catalogue Content Fingerprint"),
    result: field(sourceWatchTable, "Marketed Catalogue Last Result")
};

const df = {
    id: field(discoveryTable, "Discovery Record"),
    company: field(discoveryTable, "Company"),
    brand: field(discoveryTable, "Brand / Product Family"),
    molecule: field(discoveryTable, "Molecule / INN"),
    sourceType: field(discoveryTable, "Source Type"),
    sourceUrl: field(discoveryTable, "Source URL"),
    sourceAsOf: field(discoveryTable, "Source As Of"),
    catalogueStatus: field(discoveryTable, "Catalogue Status"),
    matchStatus: field(discoveryTable, "Portfolio Match Status"),
    matchedPortfolio: field(discoveryTable, "Matched Portfolio Records"),
    evidence: field(discoveryTable, "Evidence Notes"),
    action: field(discoveryTable, "Action"),
    lastChecked: field(discoveryTable, "Last Checked"),
    critical: field(discoveryTable, "Critical Gap"),
    sourceWatch: field(discoveryTable, "Source Watch"),
    segment: field(discoveryTable, "Catalogue Segment"),
    inclusion: field(discoveryTable, "Portfolio Inclusion"),
    scopeRationale: field(discoveryTable, "Scope Rationale"),
    detailUrl: field(discoveryTable, "Product Detail URL"),
    sourceProductKey: field(discoveryTable, "Source Product Key")
};

const pf = {
    company: field(portfolioTable, "Company"),
    brandAsset: field(portfolioTable, "Brand / Asset"),
    brand: field(portfolioTable, "Brand", false),
    molecule: field(portfolioTable, "Molecule / INN"),
    aliases: field(portfolioTable, "Asset Aliases / Former Codes", false),
    status: field(portfolioTable, "Portfolio Status")
};

const af = {
    company: field(auditTable, "Company"),
    checkType: field(auditTable, "Check Type"),
    status: field(auditTable, "Status"),
    expected: field(auditTable, "Expected Count"),
    captured: field(auditTable, "Captured Count"),
    evidenceUrls: field(auditTable, "Evidence URLs"),
    notes: field(auditTable, "Gap / Reconciliation Notes"),
    nextAction: field(auditTable, "Next Action"),
    lastChecked: field(auditTable, "Last Checked")
};

const sw = await sourceWatchTable.selectRecordAsync(sourceWatchRecordId);
if (!sw) throw new Error(`Source Watch record not found: ${sourceWatchRecordId}`);

const sourceName = text(sw, swf.name);
const sourceType = selectName(sw, swf.type);
const monitoring = selectName(sw, swf.monitoring);
const binding = selectName(sw, swf.binding);
const sourceUrl = text(sw, swf.url);
const retrievalMode = swf.retrieval ? selectName(sw, swf.retrieval) : "";
const companyIds = linkIds(sw, swf.company);

if (sourceType !== "Product / Medicines Page") throw new Error("Source Type is not Product / Medicines Page.");
if (monitoring !== "Active") throw new Error("Source Watch is not Active.");
if (binding !== "Validated") throw new Error("Adapter Binding Status is not Validated.");
if (!sourceUrl) throw new Error("Source URL is blank.");
if (companyIds.length !== 1) throw new Error("Source Watch must link exactly one Company.");
const companyId = companyIds[0];

const company = await companiesTable.selectRecordAsync(companyId);
if (!company) throw new Error("Company record not found.");
const companyName = text(company, field(companiesTable, "Name"));
const now = new Date();
const nowIso = now.toISOString();
const today = nowIso.slice(0,10);

await sourceWatchTable.updateRecordAsync(sw.id, {
    [swf.runState.id]: {name:"Running"},
    [swf.lastRun.id]: nowIso,
    [swf.requested.id]: false
});

async function fetchExternal(url, markerContract) {
    const key = getSecret("adapterApiKey");
    if (!key) throw new Error("adapterApiKey secret is unavailable for external HTML retrieval.");
    try {
        await fetch(ADAPTER_BASE_URL + "/health", {method:"GET", headers:{"x-adapter-key":key,"Accept":"application/json"}});
    } catch (_) {}
    const terms = "&required_content_terms=" + encodeURIComponent(markerContract.markers.join(","))
        + "&min_required_hits=" + markerContract.minHits;
    const res = await fetch(ADAPTER_BASE_URL + "/fetch/routed-html?url=" + encodeURIComponent(url) + terms, {
        method:"GET", headers:{"x-adapter-key":key,"Accept":"application/json"}
    });
    const bodyText = await res.text();
    let body = null;
    try { body = JSON.parse(bodyText); } catch (_) {}
    if (!res.ok || !body) throw new Error(`Routed HTML retrieval failed HTTP ${res.status}.`);
    return {
        mode:"External HTML Fallback",
        ok:Number(body.httpStatus || 0) >= 200 && Number(body.httpStatus || 0) < 400,
        status:Number(body.httpStatus || 0),
        finalUrl:clean(body.finalUrl || url),
        title:clean(body.title),
        visibleText:clean(body.visibleText),
        headings:normalizeExternalHeadings(body.headings),
        anchors:normalizeExternalAnchors(body.anchors),
        html:""
    };
}
async function fetchDirect(url) {
    const res = await fetch(url, {method:"GET", headers:{"Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}});
    const html = await res.text();
    const visibleText = stripHtml(html);
    const title = extractTitle(html);
    return {
        mode:"Airtable Direct", ok:res.ok, status:res.status,
        finalUrl:clean(res.url || url), title, visibleText,
        headings:extractHeadingsFromHtml(html),
        anchors:extractAnchorsFromHtml(html, clean(res.url || url)), html,
        blocked:classifyBlocked(html,title,visibleText)
    };
}
async function fetchPage(url, markerContract) {
    if (retrievalMode === "EXTERNAL_HTTP") return await fetchExternal(url, markerContract);
    if (retrievalMode === "BROWSER_REQUIRED") throw new Error("BROWSER_REQUIRED product catalogue cannot be processed by V1 worker.");
    if (retrievalMode === "STATIC_DOCUMENT") throw new Error("STATIC_DOCUMENT product catalogue requires a document adapter; V1 handles HTML only.");
    try {
        const direct = await fetchDirect(url);
        const unusable = !direct.ok || !!direct.blocked || direct.visibleText.length < 700
            || r5SourceMarkerHits(direct, markerContract) < markerContract.minHits;
        if (!unusable) return direct;
    } catch (e) {
        const msg = clean(e && e.message || e);
        if (!/redirect|301|302|403|408|429|500|502|503|504|timeout|timed out|failed to fetch|network/i.test(msg)) throw e;
    }
    return await fetchExternal(url, markerContract);
}

try {
    const r5Baseline = await r5GetQualifiedSnapshot(sw, sourceWatchTable);
    const markerContract = r5MarkerContract(r5Baseline);
    const page = await fetchPage(sourceUrl, markerContract);
    if (!page.ok) throw new Error(`Catalogue retrieval HTTP ${page.status || "unknown"}.`);
    if (!page.visibleText || page.visibleText.length < 300) throw new Error("Catalogue page has insufficient usable content.");

    const anchorCandidates = dedupeCandidates(page.anchors, page.finalUrl || sourceUrl);
    const cardCandidates = headingCandidates(page.headings || [], page.visibleText, page.finalUrl || sourceUrl);
    const candidateMap = new Map();
    for (const c of [...anchorCandidates, ...cardCandidates]) {
        const existing = candidateMap.get(c.key);
        if (!existing || c.score > existing.score || (!existing.molecule && c.molecule)) candidateMap.set(c.key, c);
    }
    const candidates = [...candidateMap.values()].sort((a,b) => a.display.localeCompare(b.display));
    if (!candidates.length) {
        throw new Error("No deterministic product-family links or product-card headings were extracted. Source requires a source-pattern adapter or scope review.");
    }

    // Validate SOURCE identity + trusted scope before any Marketed Product Discovery
    // or catalogue completeness audit writes. This is deliberately conservative.
    const r5Admission = r5CatalogueAdmission(r5Baseline, candidates, page.finalUrl || sourceUrl, sourceUrl);
    const scope = r5Admission.scope;
    const fingerprint = fnv1a(candidates.map(c => `${c.key}|${c.molecule}|${c.url}`).join("\n"));

    const portfolioQ = await portfolioTable.selectRecordsAsync({fields:[pf.company,pf.brandAsset,pf.brand,pf.molecule,pf.aliases,pf.status].filter(Boolean)});
    const companyPortfolio = portfolioQ.records.filter(r => linkIds(r,pf.company).includes(companyId));

    const directBrandMap = new Map();
    const aliasMap = new Map();
    const moleculeMap = new Map();
    function pushMap(map,key,record) {
        if (!key) return;
        if (!map.has(key)) map.set(key,[]);
        map.get(key).push(record);
    }
    for (const r of companyPortfolio) {
        const status = selectName(r,pf.status);
        const brandAsset = text(r,pf.brandAsset);
        const formulaBrand = pf.brand ? text(r,pf.brand) : "";
        const isCombo = /\+|\bplus\b/i.test(brandAsset);
        if (status === "Marketed" && !isCombo) {
            pushMap(directBrandMap, brandKey(brandAsset), r);
            pushMap(directBrandMap, brandKey(formulaBrand), r);
        }
        if (pf.aliases) {
            for (const a of text(r,pf.aliases).split(/[\n;|]+/).map(clean).filter(Boolean)) pushMap(aliasMap, brandKey(a), r);
        }
        pushMap(moleculeMap, norm(text(r,pf.molecule)), r);
        if (brandAsset) pushMap(aliasMap, brandKey(brandAsset), r);
        if (formulaBrand) pushMap(aliasMap, brandKey(formulaBrand), r);
    }

    const discoveryQ = await discoveryTable.selectRecordsAsync({fields:[
        df.id,df.company,df.brand,df.molecule,df.sourceType,df.sourceUrl,df.sourceAsOf,
        df.catalogueStatus,df.matchStatus,df.matchedPortfolio,df.evidence,df.action,df.lastChecked,
        df.critical,df.sourceWatch,df.segment,df.inclusion,df.scopeRationale,df.detailUrl,df.sourceProductKey
    ]});
    const companyDiscovery = discoveryQ.records.filter(r => linkIds(r,df.company).includes(companyId));
    const discoveryByBrand = new Map();
    const discoveryByKey = new Map();
    const discoveryByMolecule = new Map();
    for (const r of companyDiscovery) {
        const k = brandKey(text(r,df.brand));
        if (k && !discoveryByBrand.has(k)) discoveryByBrand.set(k,r);
        const sk = text(r,df.sourceProductKey);
        if (sk) discoveryByKey.set(sk,r);
        const mk = norm(text(r,df.molecule)).replace(/\band\b/g, " ").replace(/\s+/g, " ").trim();
        if (mk) {
            if (!discoveryByMolecule.has(mk)) discoveryByMolecule.set(mk,[]);
            discoveryByMolecule.get(mk).push(r);
        }
    }
    function brandFamilyCompatible(a,b) {
        const na = brandKey(a), nb = brandKey(b);
        if (!na || !nb) return false;
        if (na === nb || na.startsWith(nb + " ") || nb.startsWith(na + " ")) return true;
        const fa = na.split(" ")[0], fb = nb.split(" ")[0];
        return fa.length >= 4 && fa === fb;
    }

    const creates = [];
    const updates = [];
    const resolved = [];
    let assessedCount = 0;
    let matchedCount = 0;
    let missingCount = 0;
    let aliasReviewCount = 0;

    for (const c of candidates) {
        const sourceProductKey = `MPD1|${companyId}|${c.key}`;
        const exactExisting = discoveryByKey.get(sourceProductKey) || discoveryByBrand.get(c.key) || null;
        const cmk = norm(c.molecule).replace(/\band\b/g, " ").replace(/\s+/g, " ").trim();
        const moleculeDiscovery = cmk ? (discoveryByMolecule.get(cmk) || []) : [];
        const compatibleMoleculeExisting = !exactExisting && moleculeDiscovery.length === 1 &&
            brandFamilyCompatible(text(moleculeDiscovery[0],df.brand), c.display)
            ? moleculeDiscovery[0] : null;
        const existing = exactExisting || compatibleMoleculeExisting || null;
        const direct = directBrandMap.get(c.key) || [];
        const alias = aliasMap.get(c.key) || [];
        const moleculeMatches = c.molecule ? (moleculeMap.get(norm(c.molecule)) || []) : [];

        let matchStatus = "Missing from Portfolio";
        let matched = [];
        if (direct.length) {
            matchStatus = "Matched";
            matched = direct;
            matchedCount++;
        } else if (alias.length || moleculeMatches.length) {
            matchStatus = "Alias / Needs Review";
            matched = [...new Map([...alias,...moleculeMatches].map(r => [r.id,r])).values()];
            aliasReviewCount++;
        } else {
            missingCount++;
        }

        const existingInclusion = existing ? selectName(existing,df.inclusion) : "";
        const existingSegment = existing ? selectName(existing,df.segment) : "";
        const inclusion = existingInclusion || (matchStatus === "Matched" ? "Portfolio Required" : "Needs Review");
        const segment = existingSegment || inferSegment(c);
        const explicitlyOut = inclusion === "Explicitly Out of Scope";
        if (matchStatus === "Matched" || explicitlyOut) assessedCount++;

        const existingSources = existing ? linkIds(existing,df.sourceWatch) : [];
        const sourceLinks = [...new Set([...existingSources, sw.id])].map(id => ({id}));
        const priorEvidence = existing ? text(existing,df.evidence) : "";
        const retainedEvidence = priorEvidence
            .split(/\n+/)
            .filter(line => !line.includes("MARKETED_CATALOGUE_DISCOVERY_WORKER_V1"))
            .join("\n")
            .trim();
        const workerEvidence = `${VERSION}: source-listed current product; detail=${c.url || "none"}; sourceLabel=${c.rawLabel}; molecule=${c.molecule || "unresolved"}; liveMarketedMatch=${matchStatus}; source=${sourceName}.`;

        const f = {};
        f[df.company.id] = [{id:companyId}];
        if (!compatibleMoleculeExisting) f[df.brand.id] = c.display;
        if (c.molecule && (!existing || !text(existing,df.molecule))) f[df.molecule.id] = c.molecule;
        if (!existing || !selectName(existing,df.sourceType)) f[df.sourceType.id] = {name:inferDiscoverySourceType(sourceName,page.finalUrl || sourceUrl)};
        f[df.sourceUrl.id] = page.finalUrl || sourceUrl;
        f[df.detailUrl.id] = c.url || null;
        f[df.sourceProductKey.id] = sourceProductKey;
        f[df.sourceAsOf.id] = today;
        f[df.catalogueStatus.id] = {name:"Current / Source-listed"};
        f[df.matchStatus.id] = {name:matchStatus};
        f[df.matchedPortfolio.id] = matched.map(r => ({id:r.id}));
        f[df.evidence.id] = (retainedEvidence ? retainedEvidence + "\n" : "") + workerEvidence;
        f[df.action.id] = matchStatus === "Matched"
            ? "No structural action required; continue indication/market enrichment."
            : matchStatus === "Alias / Needs Review"
                ? "Review whether the existing Portfolio identity is only an alias/combination/development representation. A direct marketed baseline may still be required."
                : "Classify catalogue segment and Portfolio inclusion. If in scope, validate authoritative label/SmPC indications before creating the marketed baseline.";
        f[df.lastChecked.id] = today;
        f[df.sourceWatch.id] = sourceLinks;
        if (!existing || !existingSegment) f[df.segment.id] = {name:segment};
        if (!existing || !existingInclusion) f[df.inclusion.id] = {name:inclusion};
        if (!existing) f[df.critical.id] = false;
        if (!existing && inclusion === "Needs Review") f[df.scopeRationale.id] = "Official source-listed product family. Inclusion decision remains fail-closed until commercial scope is classified.";

        if (existing) {
            updates.push({id:existing.id,fields:f});
        } else {
            f[df.id.id] = sourceProductKey;
            creates.push({fields:f});
        }
        resolved.push({brand:c.display,molecule:c.molecule || null,matchStatus,matchedPortfolioIds:matched.map(r=>r.id),sourceProductKey});
    }

    for (let i=0;i<updates.length;i+=50) await discoveryTable.updateRecordsAsync(updates.slice(i,i+50));
    for (let i=0;i<creates.length;i+=50) await discoveryTable.createRecordsAsync(creates.slice(i,i+50));

    // Recompute current company catalogue assessment after writes.
    const refreshed = await discoveryTable.selectRecordsAsync({fields:[df.company,df.catalogueStatus,df.matchStatus,df.inclusion,df.sourceProductKey,df.brand]});
    const currentCompanyRows = refreshed.records.filter(r =>
        linkIds(r,df.company).includes(companyId) && selectName(r,df.catalogueStatus) === "Current / Source-listed"
    );
    const uniqueCurrent = new Map();
    for (const r of currentCompanyRows) {
        const k = text(r,df.sourceProductKey) || `LEGACY|${brandKey(text(r,df.brand))}`;
        if (k && !uniqueCurrent.has(k)) uniqueCurrent.set(k,r);
    }
    let companyAssessed = 0;
    for (const r of uniqueCurrent.values()) {
        if (selectName(r,df.matchStatus) === "Matched" || selectName(r,df.inclusion) === "Explicitly Out of Scope") companyAssessed++;
    }

    await sourceWatchTable.updateRecordAsync(sw.id, {
        [swf.runState.id]: {name:"Complete"},
        [swf.scope.id]: {name:scope},
        [swf.lastRun.id]: nowIso,
        [swf.count.id]: candidates.length,
        [swf.fingerprint.id]: fingerprint,
        [swf.result.id]: JSON.stringify({
            version:VERSION,company:companyName,sourceWatchRecordId:sw.id,sourceName,
            retrievalMode:page.mode,sourceScope:scope,candidates:candidates.length,
            matched:matchedCount,aliasNeedsReview:aliasReviewCount,missing:missingCount,
            created:creates.length,updated:updates.length,companyCurrentFamilies:uniqueCurrent.size,
            companyAssessedFamilies:companyAssessed,portfolioWrites:0,status:"COMPLETE - discovery/reconciliation only"
        },null,2).slice(0,10000)
    });

    // Company completeness gate: only a Full Catalogue source can establish the denominator.
    const auditQ = await auditTable.selectRecordsAsync({fields:[af.company,af.checkType,af.status,af.expected,af.captured,af.evidenceUrls,af.notes,af.nextAction,af.lastChecked]});
    const audit = auditQ.records.find(r =>
        linkIds(r,af.company).includes(companyId) && selectName(r,af.checkType) === "Marketed Product Catalogue"
    );
    if (audit) {
        const expected = scope === "Full Catalogue" ? candidates.length : uniqueCurrent.size;
        const captured = scope === "Full Catalogue"
            ? resolved.filter(x => x.matchStatus === "Matched").length + candidates.filter(c => {
                const ex = discoveryByKey.get(`MPD1|${companyId}|${c.key}`) || discoveryByBrand.get(c.key);
                return ex && selectName(ex,df.inclusion) === "Explicitly Out of Scope";
              }).length
            : companyAssessed;
        const remaining = Math.max(0, expected - captured);
        const status = scope === "Full Catalogue" && remaining === 0 ? "Pass" : "Gap";
        const scopeNote = scope === "Full Catalogue"
            ? `Full authoritative catalogue extraction found ${expected} distinct source-listed product families; ${captured} are represented by a direct marketed Portfolio baseline or explicitly out of scope; ${remaining} still require classification/repair.`
            : `Catalogue extraction succeeded for ${candidates.length} product families, but source scope is ${scope}; this source cannot by itself prove full marketed-catalogue completeness.`;
        await auditTable.updateRecordAsync(audit.id, {
            [af.status.id]: {name:status},
            [af.expected.id]: expected,
            [af.captured.id]: captured,
            [af.evidenceUrls.id]: page.finalUrl || sourceUrl,
            [af.notes.id]: `${scopeNote} This supersedes any earlier top-product-only denominator; pipeline coverage cannot substitute for commercial catalogue completeness.`,
            [af.nextAction.id]: remaining > 0
                ? `Batch-classify the ${remaining} unresolved source-listed families by Catalogue Segment and Portfolio Inclusion; route only in-scope marketed gaps to label/SmPC validation and the Marketed Product Gap Resolver.`
                : "Maintain the catalogue source on its recurring schedule and investigate any future source-list delta.",
            [af.lastChecked.id]: today
        });
    }

    output.set("summary", JSON.stringify({
        version:VERSION,company:companyName,sourceWatchRecordId:sw.id,sourceScope:scope,
        candidateCount:candidates.length,matchedCount,aliasReviewCount,missingCount,
        created:creates.length,updated:updates.length,fingerprint,portfolioWrites:0
    },null,2));

} catch (e) {
    const message = clean(e && e.message || e || "Unknown error").slice(0,1600);
    const deterministic = /No deterministic product-family links|requires a source-pattern adapter|BROWSER_REQUIRED|STATIC_DOCUMENT|not Product \/ Medicines Page|not Active|not Validated|exactly one Company|blank/.test(message);
    try {
        await sourceWatchTable.updateRecordAsync(sw.id, {
            [swf.runState.id]: {name:deterministic ? "Needs Review" : "Error"},
            [swf.lastRun.id]: nowIso,
            [swf.requested.id]: false,
            [swf.result.id]: JSON.stringify({
                version:VERSION,company:companyName,sourceWatchRecordId:sw.id,error:message,
                deterministic,portfolioWrites:0,status:"FAIL CLOSED - no discovery master assumptions made"
            },null,2).slice(0,10000)
        });
    } catch (_) {}
    output.set("summary", JSON.stringify({version:VERSION,company:companyName,error:message,portfolioWrites:0,status:"FAIL CLOSED"},null,2));
}
