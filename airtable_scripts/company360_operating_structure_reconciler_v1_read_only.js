/*
 * COMPANY360_OPERATING_STRUCTURE_RECONCILER_V1_READ_ONLY
 * Shared Company 360 operating-structure reconciler for Airtable automation.
 *
 * SAFETY: APPLY_WRITES is deliberately false. This version never mutates Airtable.
 * It plans idempotent Company Regional Definitions changes and the corresponding
 * Company Completeness Audit decision. No Portfolio access or writes.
 */

const VERSION = "COMPANY360_OPERATING_STRUCTURE_RECONCILER_V1_READ_ONLY";
const APPLY_WRITES = false;

const TABLES = {
  regionalDefinitions: "tblKnET0GjoemCZE0",
  completenessAudit: "tbl4gfb4fkCUwR173",
};

const F = {
  regional: {
    primary: "fld3bttNI1B7ZwEsA",
    company: "fldYaGsi0kOtuwyzI",
    name: "fldnH4pFcrHuZzqnA",
    level: "fld8Ep1FZpRVpwqYc",
    parentName: "fldaHJ5G4bjAV5tFl",
    effectiveFrom: "fldRrSgfhZ4L1Qii2",
    effectiveTo: "fld0gJAqF1J1rchSg",
    current: "fld3O8yV1H6AdLqej",
    definition: "fldEjjehLnw171gqc",
    sourceName: "fldz3jG09f1UZ3hUr",
    sourceUrl: "fldwT4grMHTkZgXmr",
    verification: "fldm1GxSgocLFRE9b",
    lastVerified: "fld7JCaemSyhKqBne",
    parentLink: "fld9Ow6TTUIdFCHaQ",
  },
  audit: {
    primary: "fld1fMaYEpvdokv3z",
    company: "fldnyj9I8Aar2SHIN",
    checkType: "fldzIrDxgQhqAtDCc",
    status: "fldaVp7k8DxQSq2Ir",
    expectedCount: "fldcHiSG8jo6F76Op",
    capturedCount: "fldT2JFprho51krd8",
    requiredEvidence: "fldtiD39KaRJf0hvL",
    evidenceUrls: "fldSljEbU6cg4OYBd",
    notes: "fld7lOldSsYbwqz9T",
    nextAction: "fldCucvdpLjkWkFW9",
    lastChecked: "fldUeQbLPujzzR8cG",
    evidenceStrength: "fldkOvurR740MwxkB",
  },
};

const ALLOWED_LEVELS = new Set([
  "Business Unit",
  "Region",
  "Sub-region",
  "Country Business Unit",
]);
const ALLOWED_VERIFY = new Set(["Verified", "Partially verified", "Needs verification"]);
const DISCLOSURE_STATUSES = new Set([
  "DISCLOSED_STRUCTURE",
  "VERIFIED_NO_SEPARATE_BUSINESS_UNIT_HIERARCHY",
  "INSUFFICIENT_EVIDENCE",
]);
const COVERAGE_STATUSES = new Set(["FULL_CURRENT_STRUCTURE", "PARTIAL_DISCLOSURE", "NOT_APPLICABLE"]);

function clean(v) { return String(v ?? "").trim(); }
function norm(v) {
  return clean(v)
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/&/g, " and ")
    .replace(/[^a-z0-9]+/g, " ")
    .trim()
    .replace(/\s+/g, " ");
}
function isoDate(v) {
  const s = clean(v);
  if (!s) return "";
  return /^\d{4}-\d{2}-\d{2}$/.test(s) ? s : "";
}
function linkIds(v) { return Array.isArray(v) ? v.map(x => x && x.id).filter(Boolean) : []; }
function selectName(v) { return v && typeof v === "object" ? clean(v.name) : clean(v); }
function semanticKey(name, level) { return `${norm(name)}|${clean(level)}`; }
function isHttpsUrl(v) {
  try {
    const u = new URL(clean(v));
    return u.protocol === "https:" && !!u.hostname;
  } catch (_) { return false; }
}
function same(a, b) { return clean(a) === clean(b); }
function sameNorm(a, b) { return norm(a) === norm(b); }
function deepClone(v) { return JSON.parse(JSON.stringify(v)); }

function parseResearch(raw) {
  if (raw && typeof raw === "object" && !Array.isArray(raw)) return raw;
  const s = clean(raw);
  if (!s) return {};
  try { return JSON.parse(s); } catch (e) {
    return { __parseError: `Invalid research JSON: ${e.message}` };
  }
}

function candidateFromRaw(raw, global) {
  const c = raw || {};
  return {
    name: clean(c.name),
    level: clean(c.level),
    parentName: clean(c.parentName),
    effectiveFrom: isoDate(c.effectiveFrom),
    effectiveTo: isoDate(c.effectiveTo),
    current: c.current !== false,
    definitionScope: clean(c.definitionScope),
    sourceName: clean(c.sourceName) || clean(global.sourceName),
    sourceUrl: clean(c.sourceUrl) || clean(global.sourceUrl),
    verificationStatus: clean(c.verificationStatus) || "Verified",
    lastVerified: isoDate(c.lastVerified) || isoDate(global.asOfDate),
  };
}

function existingFromRecordLike(r, companyRecordId) {
  const v = r.cellValuesByFieldId || r.fields || {};
  const companyIds = linkIds(v[F.regional.company]);
  if (companyRecordId && companyIds.length && !companyIds.includes(companyRecordId)) return null;
  return {
    id: r.id,
    primary: clean(v[F.regional.primary]),
    name: clean(v[F.regional.name]),
    level: selectName(v[F.regional.level]),
    parentName: clean(v[F.regional.parentName]),
    effectiveFrom: clean(v[F.regional.effectiveFrom]),
    effectiveTo: clean(v[F.regional.effectiveTo]),
    current: !!v[F.regional.current],
    definitionScope: clean(v[F.regional.definition]),
    sourceName: clean(v[F.regional.sourceName]),
    sourceUrl: clean(v[F.regional.sourceUrl]),
    verificationStatus: selectName(v[F.regional.verification]),
    lastVerified: clean(v[F.regional.lastVerified]),
    parentIds: linkIds(v[F.regional.parentLink]),
  };
}

function validateResearch(research) {
  const blocks = [];
  const disclosureStatus = clean(research.structureDisclosureStatus);
  const structureCoverage = clean(research.structureCoverage);
  const evidenceStrength = clean(research.evidenceStrength);
  const asOfDate = isoDate(research.asOfDate);
  const sourceName = clean(research.sourceName);
  const sourceUrl = clean(research.sourceUrl);

  if (research.__parseError) blocks.push(research.__parseError);
  if (!DISCLOSURE_STATUSES.has(disclosureStatus)) blocks.push(`Invalid structureDisclosureStatus: ${disclosureStatus || "<blank>"}`);
  if (disclosureStatus === "DISCLOSED_STRUCTURE" && !COVERAGE_STATUSES.has(structureCoverage)) blocks.push(`Invalid structureCoverage: ${structureCoverage || "<blank>"}`);
  if (!new Set(["High", "Medium", "Low"]).has(evidenceStrength)) blocks.push(`Invalid evidenceStrength: ${evidenceStrength || "<blank>"}`);
  if (!asOfDate) blocks.push("asOfDate must be YYYY-MM-DD");
  if (!sourceName) blocks.push("sourceName is required");
  if (!isHttpsUrl(sourceUrl)) blocks.push("sourceUrl must be an https URL");

  const rawUnits = Array.isArray(research.units) ? research.units : [];
  if (disclosureStatus === "DISCLOSED_STRUCTURE" && rawUnits.length === 0) blocks.push("DISCLOSED_STRUCTURE requires at least one unit");
  if (disclosureStatus !== "DISCLOSED_STRUCTURE" && rawUnits.length > 0) blocks.push(`${disclosureStatus} must not include structural unit records`);

  return { blocks, disclosureStatus, structureCoverage, evidenceStrength, asOfDate, sourceName, sourceUrl, rawUnits };
}

function validateCandidates(rawUnits, global) {
  const candidates = rawUnits.map(x => candidateFromRaw(x, global));
  const blocks = [];
  const seen = new Map();

  for (let i = 0; i < candidates.length; i++) {
    const c = candidates[i];
    const label = `unit[${i}]`;
    if (!c.name) blocks.push(`${label}: name is required`);
    if (!ALLOWED_LEVELS.has(c.level)) blocks.push(`${label}: unsupported level '${c.level}'`);
    if (!c.definitionScope) blocks.push(`${label}: definitionScope is required`);
    if (!c.sourceName) blocks.push(`${label}: sourceName is required`);
    if (!isHttpsUrl(c.sourceUrl)) blocks.push(`${label}: sourceUrl must be https`);
    if (!ALLOWED_VERIFY.has(c.verificationStatus)) blocks.push(`${label}: invalid verificationStatus '${c.verificationStatus}'`);
    if (!c.lastVerified) blocks.push(`${label}: lastVerified/asOfDate must be YYYY-MM-DD`);
    if (c.effectiveTo && c.current) blocks.push(`${label}: current=true cannot have effectiveTo`);
    const key = semanticKey(c.name, c.level);
    if (seen.has(key)) blocks.push(`${label}: duplicate candidate semantic identity with unit[${seen.get(key)}] (${key})`);
    else seen.set(key, i);
  }
  return { candidates, blocks };
}

function buildPlan({ companyRecordId, companyName, research, existingRecords }) {
  const researchCheck = validateResearch(research);
  const global = {
    sourceName: researchCheck.sourceName,
    sourceUrl: researchCheck.sourceUrl,
    asOfDate: researchCheck.asOfDate,
  };
  const candidateCheck = validateCandidates(researchCheck.rawUnits, global);
  const blocks = [...researchCheck.blocks, ...candidateCheck.blocks];
  const candidates = candidateCheck.candidates;
  const existing = (existingRecords || []).map(r => existingFromRecordLike(r, companyRecordId)).filter(Boolean);

  const activeByKey = new Map();
  const historicalByKey = new Map();
  for (const e of existing) {
    const key = semanticKey(e.name, e.level);
    const target = e.current ? activeByKey : historicalByKey;
    if (!target.has(key)) target.set(key, []);
    target.get(key).push(e);
  }
  for (const [key, arr] of activeByKey.entries()) {
    if (arr.length > 1) blocks.push(`Existing active duplicate semantic identity ${key}: ${arr.map(x => x.id).join(",")}`);
  }

  const plannedCreates = [];
  const plannedUpdates = [];
  const plannedParentLinks = [];
  const noops = [];
  const retirementReview = [];
  const versionChangeReview = [];

  if (blocks.length === 0 && researchCheck.disclosureStatus === "DISCLOSED_STRUCTURE") {
    const candidateKeys = new Set();
    for (const c of candidates) {
      const key = semanticKey(c.name, c.level);
      candidateKeys.add(key);
      const active = activeByKey.get(key) || [];
      const historical = historicalByKey.get(key) || [];

      if (active.length === 1) {
        const e = active[0];
        if (e.effectiveFrom && c.effectiveFrom && e.effectiveFrom !== c.effectiveFrom) {
          versionChangeReview.push({
            semanticKey: key,
            existingRecordId: e.id,
            existingEffectiveFrom: e.effectiveFrom,
            proposedEffectiveFrom: c.effectiveFrom,
            reason: "Effective-from changed on an active semantic identity; do not overwrite/version automatically.",
          });
          continue;
        }
        const changes = {};
        if (!sameNorm(e.parentName, c.parentName)) changes.parentName = c.parentName;
        if (!same(e.definitionScope, c.definitionScope)) changes.definitionScope = c.definitionScope;
        if (!same(e.sourceName, c.sourceName)) changes.sourceName = c.sourceName;
        if (!same(e.sourceUrl, c.sourceUrl)) changes.sourceUrl = c.sourceUrl;
        if (!same(e.verificationStatus, c.verificationStatus)) changes.verificationStatus = c.verificationStatus;
        if (!same(e.lastVerified, c.lastVerified)) changes.lastVerified = c.lastVerified;
        if (!e.effectiveFrom && c.effectiveFrom) changes.effectiveFrom = c.effectiveFrom;
        if (Object.keys(changes).length) plannedUpdates.push({ semanticKey: key, recordId: e.id, changes, candidate: c });
        else noops.push({ semanticKey: key, recordId: e.id });
      } else if (active.length === 0) {
        const sameHistoricalDate = historical.find(h => h.effectiveFrom && c.effectiveFrom && h.effectiveFrom === c.effectiveFrom);
        if (sameHistoricalDate) {
          versionChangeReview.push({
            semanticKey: key,
            historicalRecordId: sameHistoricalDate.id,
            reason: "Candidate matches a historical version; do not reactivate automatically.",
          });
          continue;
        }
        plannedCreates.push({ semanticKey: key, candidate: c });
      }
    }

    for (const [key, arr] of activeByKey.entries()) {
      if (!candidateKeys.has(key)) {
        for (const e of arr) retirementReview.push({
          semanticKey: key,
          recordId: e.id,
          name: e.name,
          level: e.level,
          reason: "Active existing unit absent from current evidence. Review only; never auto-retire from one snapshot.",
        });
      }
    }

    const candidateByNormName = new Map();
    for (const c of candidates) {
      const nk = norm(c.name);
      if (!candidateByNormName.has(nk)) candidateByNormName.set(nk, []);
      candidateByNormName.get(nk).push(c);
    }
    const activeByNormName = new Map();
    for (const e of existing.filter(x => x.current)) {
      const nk = norm(e.name);
      if (!activeByNormName.has(nk)) activeByNormName.set(nk, []);
      activeByNormName.get(nk).push(e);
    }

    for (const c of candidates) {
      if (!c.parentName) continue;
      const nk = norm(c.parentName);
      const candidateParents = candidateByNormName.get(nk) || [];
      const existingParents = activeByNormName.get(nk) || [];

      // Candidate + existing representations of the SAME semantic parent count as one logical parent.
      const logicalParents = new Map();
      for (const p of candidateParents) {
        const pk = semanticKey(p.name, p.level);
        logicalParents.set(pk, { semanticKey: pk, candidate: p, existing: null });
      }
      for (const p of existingParents) {
        const pk = semanticKey(p.name, p.level);
        const entry = logicalParents.get(pk) || { semanticKey: pk, candidate: null, existing: null };
        entry.existing = p;
        logicalParents.set(pk, entry);
      }

      if (logicalParents.size !== 1) {
        blocks.push(`Parent '${c.parentName}' for '${c.name}' resolves to ${logicalParents.size} logical identities; expected exactly 1`);
      } else {
        const parent = [...logicalParents.values()][0];
        const childKey = semanticKey(c.name, c.level);
        const childExisting = (activeByKey.get(childKey) || [])[0] || null;
        const parentExistingRecordId = parent.existing?.id || null;
        const alreadyLinked = !!(childExisting && parentExistingRecordId && childExisting.parentIds.includes(parentExistingRecordId));
        if (!alreadyLinked) {
          plannedParentLinks.push({
            childSemanticKey: childKey,
            parentName: c.parentName,
            parentCandidateSemanticKey: parent.semanticKey,
            parentExistingRecordId,
          });
        }
      }
    }
  }

  const reviewItems = [...retirementReview, ...versionChangeReview];
  let auditStatus = "Needs Review";
  let expectedCount = null;
  let capturedCount = existing.filter(x => x.current).length;
  let auditReason = "";

  if (blocks.length) {
    auditStatus = "Needs Review";
    auditReason = `Structural reconciliation blocked: ${blocks.join(" | ")}`;
  } else if (researchCheck.disclosureStatus === "INSUFFICIENT_EVIDENCE") {
    auditStatus = "Needs Review";
    expectedCount = null;
    auditReason = "Authoritative evidence is insufficient to determine a reliable current operating structure.";
  } else if (researchCheck.disclosureStatus === "VERIFIED_NO_SEPARATE_BUSINESS_UNIT_HIERARCHY") {
    auditStatus = researchCheck.evidenceStrength === "High" ? "Pass" : "Needs Review";
    expectedCount = 0;
    capturedCount = 0;
    auditReason = researchCheck.evidenceStrength === "High"
      ? "Authoritative evidence verifies that no separate business-unit hierarchy is publicly disclosed for this master scope; zero structural records are expected."
      : "No-business-unit-hierarchy conclusion has less than High evidence strength; retain review.";
  } else if (researchCheck.disclosureStatus === "DISCLOSED_STRUCTURE") {
    expectedCount = candidates.filter(x => x.current).length;
    const projectedCaptured = new Set([
      ...existing.filter(x => x.current).map(x => semanticKey(x.name, x.level)),
      ...plannedCreates.filter(x => x.candidate.current).map(x => x.semanticKey),
    ]).size;
    capturedCount = projectedCaptured;
    if (researchCheck.structureCoverage !== "FULL_CURRENT_STRUCTURE") {
      auditStatus = "Needs Review";
      auditReason = "Current evidence is partial disclosure, so completeness cannot pass.";
    } else if (researchCheck.evidenceStrength !== "High") {
      auditStatus = "Needs Review";
      auditReason = "Current structure is not supported at High evidence strength.";
    } else if (reviewItems.length) {
      auditStatus = "Needs Review";
      auditReason = "Current structure is evidenced, but retirement/version-change review remains open.";
    } else {
      auditStatus = "Pass";
      auditReason = "Full current structure is evidenced at High confidence and reconciles without unresolved semantic conflicts.";
    }
  }

  const status = blocks.length ? "BLOCK" : (auditStatus === "Pass" ? "PASS_PLAN" : "REVIEW_REQUIRED");
  return {
    version: VERSION,
    mode: APPLY_WRITES ? "WRITE_ENABLED" : "READ_ONLY_ZERO_WRITES",
    companyRecordId,
    companyName,
    disclosureStatus: researchCheck.disclosureStatus,
    structureCoverage: researchCheck.structureCoverage,
    evidenceStrength: researchCheck.evidenceStrength,
    status,
    blocks,
    plannedCreates,
    plannedUpdates,
    plannedParentLinks,
    noops,
    retirementReview,
    versionChangeReview,
    auditDecision: {
      status: auditStatus,
      expectedCount,
      capturedCount,
      evidenceStrength: researchCheck.evidenceStrength || "Low",
      evidenceUrls: researchCheck.sourceUrl || "",
      lastChecked: researchCheck.asOfDate || "",
      notes: auditReason,
      nextAction: auditStatus === "Pass" ? "No action required; refresh on next authoritative structural change." : "Resolve structural evidence/reconciliation review before marking this completeness check Pass.",
    },
    writesPlanned: plannedCreates.length + plannedUpdates.length + plannedParentLinks.length + 1,
    airtableWrites: 0,
    portfolioWrites: 0,
    masterPortfolioWrites: 0,
  };
}

async function loadExistingRecords(companyRecordId) {
  const table = base.getTable(TABLES.regionalDefinitions);
  const q = await table.selectRecordsAsync({ fields: Object.values(F.regional) });
  return q.records
    .filter(r => linkIds(r.getCellValue(F.regional.company)).includes(companyRecordId))
    .map(r => ({
      id: r.id,
      cellValuesByFieldId: Object.fromEntries(Object.values(F.regional).map(fid => [fid, r.getCellValue(fid)])),
    }));
}

async function main() {
  const cfg = input.config();
  const companyRecordId = clean(cfg.companyRecordId);
  const companyName = clean(cfg.companyName);
  const research = parseResearch(cfg.researchJson ?? cfg.research ?? cfg.operatingStructureJson ?? cfg.operatingStructure);

  if (!companyRecordId) throw new Error("companyRecordId is required");
  if (!companyName) throw new Error("companyName is required");

  const existingRecords = await loadExistingRecords(companyRecordId);
  const plan = buildPlan({ companyRecordId, companyName, research, existingRecords });

  output.set("version", VERSION);
  output.set("status", plan.status);
  output.set("auditStatus", plan.auditDecision.status);
  output.set("plannedCreateCount", plan.plannedCreates.length);
  output.set("plannedUpdateCount", plan.plannedUpdates.length);
  output.set("plannedParentLinkCount", plan.plannedParentLinks.length);
  output.set("retirementReviewCount", plan.retirementReview.length);
  output.set("versionChangeReviewCount", plan.versionChangeReview.length);
  output.set("blockCount", plan.blocks.length);
  output.set("airtableWrites", 0);
  output.set("portfolioWrites", 0);
  output.set("planJson", JSON.stringify(plan));
}

function selfTest() {
  const companyRecordId = "recCOMPANY";
  const baseResearch = {
    structureDisclosureStatus: "DISCLOSED_STRUCTURE",
    structureCoverage: "FULL_CURRENT_STRUCTURE",
    evidenceStrength: "High",
    asOfDate: "2026-10-08",
    sourceName: "Official organisation page",
    sourceUrl: "https://example.com/official",
    units: [{
      name: "International Business Unit",
      level: "Business Unit",
      parentName: "",
      effectiveFrom: "2026-04-01",
      current: true,
      definitionScope: "All markets outside the United States",
      verificationStatus: "Verified",
    }],
  };
  const empty = [];
  const p1 = buildPlan({ companyRecordId, companyName: "Example", research: deepClone(baseResearch), existingRecords: empty });
  if (p1.status !== "PASS_PLAN" || p1.plannedCreates.length !== 1) throw new Error("selfTest create failed");

  const existing = [{ id: "recUNIT", cellValuesByFieldId: {
    [F.regional.company]: [{ id: companyRecordId, name: "Example" }],
    [F.regional.name]: "International Business Unit",
    [F.regional.level]: { name: "Business Unit" },
    [F.regional.parentName]: "",
    [F.regional.effectiveFrom]: "2026-04-01",
    [F.regional.effectiveTo]: null,
    [F.regional.current]: true,
    [F.regional.definition]: "All markets outside the United States",
    [F.regional.sourceName]: "Official organisation page",
    [F.regional.sourceUrl]: "https://example.com/official",
    [F.regional.verification]: { name: "Verified" },
    [F.regional.lastVerified]: "2026-10-08",
    [F.regional.parentLink]: [],
  }}];
  const p2 = buildPlan({ companyRecordId, companyName: "Example", research: deepClone(baseResearch), existingRecords: existing });
  if (p2.status !== "PASS_PLAN" || p2.noops.length !== 1 || p2.plannedCreates.length !== 0) throw new Error("selfTest idempotence failed");

  const dup = deepClone(baseResearch);
  dup.units.push(deepClone(dup.units[0]));
  const p3 = buildPlan({ companyRecordId, companyName: "Example", research: dup, existingRecords: empty });
  if (p3.status !== "BLOCK") throw new Error("selfTest duplicate block failed");

  const zero = {
    // This path requires explicit evidence about BUSINESS-UNIT hierarchy.
    // A single accounting operating segment is not sufficient.
    structureDisclosureStatus: "VERIFIED_NO_SEPARATE_BUSINESS_UNIT_HIERARCHY",
    structureCoverage: "NOT_APPLICABLE",
    evidenceStrength: "High",
    asOfDate: "2026-10-08",
    sourceName: "Official annual report",
    sourceUrl: "https://example.com/annual-report",
    units: [],
  };
  const p4 = buildPlan({ companyRecordId, companyName: "Example", research: zero, existingRecords: empty });
  if (p4.status !== "PASS_PLAN" || p4.auditDecision.status !== "Pass" || p4.auditDecision.expectedCount !== 0) throw new Error("selfTest verified-zero failed");

  const changed = deepClone(baseResearch);
  changed.units = [{
    name: "U.S. Business Unit",
    level: "Business Unit",
    effectiveFrom: "2026-04-01",
    current: true,
    definitionScope: "United States",
    verificationStatus: "Verified",
  }];
  const p5 = buildPlan({ companyRecordId, companyName: "Example", research: changed, existingRecords: existing });
  if (p5.retirementReview.length !== 1 || p5.auditDecision.status !== "Needs Review") throw new Error("selfTest disappearance review failed");

  const hierarchyResearch = deepClone(baseResearch);
  hierarchyResearch.units.push({
    name: "Japan Pharma Business Unit",
    level: "Country Business Unit",
    parentName: "International Business Unit",
    effectiveFrom: "2026-04-01",
    current: true,
    definitionScope: "Japan operating unit",
    verificationStatus: "Verified",
    lastVerified: "2026-10-08",
  });
  const hierarchyExisting = [
    existing[0],
    { id: "recCHILD", cellValuesByFieldId: {
      [F.regional.company]: [{ id: companyRecordId, name: "Example" }],
      [F.regional.name]: "Japan Pharma Business Unit",
      [F.regional.level]: { name: "Country Business Unit" },
      [F.regional.parentName]: "International Business Unit",
      [F.regional.effectiveFrom]: "2026-04-01",
      [F.regional.effectiveTo]: null,
      [F.regional.current]: true,
      [F.regional.definition]: "Japan operating unit",
      [F.regional.sourceName]: "Official organisation page",
      [F.regional.sourceUrl]: "https://example.com/official",
      [F.regional.verification]: { name: "Verified" },
      [F.regional.lastVerified]: "2026-10-08",
      [F.regional.parentLink]: [{ id: "recUNIT", name: "International Business Unit" }],
    }},
  ];
  const p6 = buildPlan({ companyRecordId, companyName: "Example", research: hierarchyResearch, existingRecords: hierarchyExisting });
  if (p6.status !== "PASS_PLAN" || p6.plannedParentLinks.length !== 0 || p6.blocks.length !== 0) throw new Error("selfTest parent-link idempotence failed");

  return { ok: true, version: VERSION, tests: 6 };
}

if (typeof process !== "undefined" && process.env.COMPANY360_SELF_TEST === "1") {
  console.log(JSON.stringify(selfTest()));
} else if (typeof input !== "undefined" && typeof base !== "undefined" && typeof output !== "undefined") {
  await main();
}
