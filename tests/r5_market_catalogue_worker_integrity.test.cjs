"use strict";
// Offline regression of guard EXTRACTED FROM exact published-worker draft copy.
// Never evaluates Airtable worker side effects, never uses credentials, HTTP, or writes.
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const workerPath = path.join(__dirname, "../review/marketed_product_catalogue_worker_v1_3_guarded_DRAFT_ONLY.js");
const worker = fs.readFileSync(workerPath, "utf8");
function section(start, end) {
    const a = worker.indexOf(start), b = worker.indexOf(end, a);
    assert.ok(a >= 0 && b > a, "Missing published-worker section " + start);
    return worker.slice(a, b);
}
const code = [
    section("function clean(", "function linkIds("),
    section("function canonicalBrand(", "function looksGenericNav("),
    section("function sameHost(", "function brandLike("),
    section("// R5_CATALOGUE_ADMISSION_START", "// R5_CATALOGUE_ADMISSION_END"),
].join("\n");
const {assess, brandKey, markerContract, markerHits} = new Function(code + "\nreturn {assess:r5CatalogueAdmission, brandKey, markerContract:r5MarkerContract, markerHits:r5SourceMarkerHits};")();

const GILEAD = [
"Atripla","Biktarvy","Complera","Descovy","Emtriva","Genvoya","Hepsera",
"Odefsey","Ranexa","Stribild","Truvada","Vemlidy","Viread","Epclusa",
"Harvoni","Sovaldi","Vosevi","Bixlenvo","Cayston","Hepcludex","Letairis",
"Livdelzi","Sunlenca","Trodelvy","Veklury","Yeztugo","Zydelig","Yescarta","Tecartus"
];
const ASTELLAS = [
"Lexiscan","ASTAGRAF XL","Prograf","AmBisome","CRESEMBA","MYCAMINE","XTANDI",
"XOSPATA","PADCEV","VYLOY","IZERVAY","Myrbetriq","Myrbetriq Granules",
"VESIcare","VESIcare LS","VEOZAH"
];
function baseline(names, scope, date="2026-09-30") {
    return {authoritative:true,scope,asOf:date,expectedCount:names.length,
        products:names.map(brand=>({brand}))};
}
function candidates(names) { return names.map(display=>({display,key:brandKey(display)})); }
const full=baseline(GILEAD,"Full Catalogue");
const partial=baseline(ASTELLAS,"Partial Catalogue");
const src="https://www.gilead.com/science-and-medicine/medicines";
const gpage="https://www.gilead.com/medicines";
const asrc="https://www.astellas.com/en/science/medicines-and-disease-areas/medicines-by-location";
const requireHold=(fn,reason)=>assert.throws(fn,new RegExp("R5_CATALOGUE_INTEGRITY_HOLD:"+reason));

test("Gilead verified 29-family exact identity parity preserves FULL scope",()=>{
    const out=assess(full,candidates(GILEAD),gpage,src);
    assert.equal(out.status,"IDENTITY_PARITY_PREVIEW");
    assert.equal(out.baselineCount,29);
    assert.equal(out.liveCount,29);
    assert.equal(out.fullCatalogueEligible,true);
});
test("Gilead long navigation-only seven-item extract held",()=>{
    requireHold(()=>assess(full,candidates(["Home","About","News","Careers","Science","Patients","Medicines"]),gpage,src),
        "LIVE_CATALOGUE_SHORTER_THAN_VERIFIED_BASELINE");
});
test("Gilead same-count contamination never passes",()=>{
    const contaminated=[...GILEAD.slice(1),"News"];
    assert.equal(contaminated.length,29);
    requireHold(()=>assess(full,candidates(contaminated),gpage,src),"VERIFIED_BASELINE_PRODUCT_ABSENT");
});
test("Gilead cannot silently drop Hepcludex even with a full-sized page",()=>{
    const altered=GILEAD.map(p=>p==="Hepcludex"?"Media Centre":p);
    requireHold(()=>assess(full,candidates(altered),gpage,src),"VERIFIED_BASELINE_PRODUCT_ABSENT");
});
test("Gilead new family goes to HOLD not immediate discovery upsert",()=>{
    requireHold(()=>assess(full,candidates([...GILEAD,"Unknown New Brand"]),gpage,src),
        "NEW_PRODUCT_IDENTITIES_REQUIRE_SOURCE_REVIEW");
});
test("Astellas independently verified 16-family snapshot remains PARTIAL",()=>{
    const out=assess(partial,candidates(ASTELLAS),asrc,asrc);
    assert.equal(out.baselineCount,16);assert.equal(out.scope,"Partial Catalogue");
    assert.equal(out.fullCatalogueEligible,false);
});
test("Astellas one missing specialty presentation is held",()=>{
    requireHold(()=>assess(partial,candidates(ASTELLAS.filter(x=>x!=="Myrbetriq Granules")),asrc,asrc),
        "LIVE_CATALOGUE_SHORTER_THAN_VERIFIED_BASELINE");
});
test("Current page cannot escape official source host",()=>{
    requireHold(()=>assess(full,candidates(GILEAD),"https://not-gilead.example/medicines",src),
        "SOURCE_ORIGIN_MISMATCH");
});
test("Unverified/no authoritative snapshot is held",()=>{
    requireHold(()=>assess(null,candidates(GILEAD),gpage,src),"AUTHORITATIVE_SNAPSHOT_REQUIRED");
    requireHold(()=>assess({...full,authoritative:false},candidates(GILEAD),gpage,src),
        "AUTHORITATIVE_SNAPSHOT_REQUIRED");
});
test("Self-referential expected count is rejected independently",()=>{
    requireHold(()=>assess({...full,expectedCount:7},candidates(GILEAD),gpage,src),
        "INDEPENDENT_BASELINE_COUNT_INVALID");
});
test("Unknown baseline scope cannot be promoted to full",()=>{
    requireHold(()=>assess({...partial,scope:"Unknown / Needs Review"},candidates(ASTELLAS),asrc,asrc),
        "SNAPSHOT_SCOPE_NOT_QUALIFIED");
});
test("Duplicated trusted source identities cannot certify an expected count",()=>{
    const list=[...GILEAD];list[20]=list[0];
    requireHold(()=>assess(baseline(list,"Full Catalogue"),candidates(GILEAD),gpage,src),
        "BASELINE_PRODUCT_IDENTITY_MISSING_OR_DUPLICATE");
});
test("Guard is before Marketed Product Discovery writes in worker review copy",()=>{
    const p=worker.indexOf("const r5Admission = r5CatalogueAdmission(");
    const update=worker.indexOf("discoveryTable.updateRecordsAsync(");
    const create=worker.indexOf("discoveryTable.createRecordsAsync(");
    const audit=worker.indexOf("auditTable.updateRecordAsync(");
    assert.ok(p>=0&&p<update&&p<create&&p<audit);
});
test("Published worker remains unchanged; draft has no portfolio writes",()=>{
    assert.ok(worker.includes("REVIEW COPY ONLY"));
    assert.ok(!worker.includes("portfolioTable.createRecordsAsync("));
    assert.ok(!worker.includes("portfolioTable.updateRecordsAsync("));
});

test("Trusted snapshot produces deterministic source markers for both companies",()=>{
    for (const snap of [full,partial]) {
        const first=markerContract(snap), replay=markerContract(snap);
        assert.deepEqual(first,replay);
        assert.equal(first.minHits,3);
        assert.equal(first.markers.length,12);
        for (const item of first.markers) assert.ok(snap.products.some(p=>p.brand===item));
    }
});
test("Long navigation-only direct content is insufficient before transport selection",()=>{
    const nav=("Home About News Investor Relations Contact " ).repeat(40);
    assert.ok(nav.length>700);
    const markers=markerContract(full);
    assert.equal(markerHits({visibleText:nav,headings:[],anchors:[]},markers),0);
    assert.ok(markerHits({visibleText:markers.markers.slice(0,3).join(" "),headings:[],anchors:[]},markers)>=3);
});
test("Astellas partial snapshot markers are opt-in but not a full-catalogue claim",()=>{
    const terms=markerContract(partial);
    assert.equal(markerHits({visibleText:terms.markers.slice(0,2).join(" "),headings:[],anchors:[]},terms),2);
    assert.equal(assess(partial,candidates(ASTELLAS),asrc,asrc).fullCatalogueEligible,false);
});
test("Worker passes vetted markers to shared router, checks direct text, and guards before discovery writes",()=>{
    const baseline=worker.indexOf("const r5Baseline = await r5GetQualifiedSnapshot(");
    const fetchPage=worker.indexOf("const page = await fetchPage(sourceUrl, markerContract)");
    const admission=worker.indexOf("const r5Admission = r5CatalogueAdmission(");
    const write=worker.indexOf("discoveryTable.updateRecordsAsync(");
    assert.ok(baseline>=0&&baseline<fetchPage&&fetchPage<admission&&admission<write);
    assert.ok(worker.includes("r5SourceMarkerHits(direct, markerContract) < markerContract.minHits"));
    assert.ok(worker.includes("&required_content_terms="));
    assert.ok(worker.includes("&min_required_hits="));
    assert.ok(worker.includes("return await fetchExternal(url, markerContract)"));
});
