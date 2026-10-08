/*
 * COMPANY360_OPERATING_STRUCTURE_WRITER_V1
 * Approval-gated shared writer for Company 360 operating structure.
 *
 * SAFETY:
 * - Generic/company-agnostic logic.
 * - Creates only approved missing Company Regional Definitions and market mappings.
 * - No updates, retirements, parent-link changes, completeness-audit writes or Portfolio access.
 * - Re-running the same approved manifest is idempotent: existing approved identities become no-ops.
 */

const VERSION = "COMPANY360_OPERATING_STRUCTURE_WRITER_V1.0_APPROVAL_GATED";

const TABLES = {
  regionalDefinitions: "tblKnET0GjoemCZE0",
  regionMarketMapping: "tblgL5ZMMecFLd3n7",
  markets: "tbldDJ2PaSggrkcnq",
};

const F = {
  regional: {
    primary: "fld3bttNI1B7ZwEsA",
    company: "fldYaGsi0kOtuwyzI",
    name: "fldnH4pFcrHuZzqnA",
    level: "fld8Ep1FZpRVpwqYc",
    effectiveFrom: "fldRrSgfhZ4L1Qii2",
    effectiveTo: "fld0gJAqF1J1rchSg",
    current: "fld3O8yV1H6AdLqej",
    definition: "fldEjjehLnw171gqc",
    sourceName: "fldz3jG09f1UZ3hUr",
    sourceUrl: "fldwT4grMHTkZgXmr",
    verification: "fldm1GxSgocLFRE9b",
    lastVerified: "fld7JCaemSyhKqBne",
  },
  mapping: {
    primary: "fldEnKjnPGgLXQ0bA",
    company: "fldx9pbPQtWgdk4WN",
    market: "fld34jYpHmIvEVtcE",
    marketName: "fldGoHvsZ8owwU0W8",
    region: "fldw1UhUtChuAksQC",
    current: "fldwsEbNxt0oY4WMg",
    sourceName: "fldct9P7twirFVYGB",
    sourceUrl: "fldjq1JitjJrxtKix",
    lastVerified: "fldbDMuOOydNVGNiC",
    notes: "fldFgWiyhyixZsOsb",
  },
  market: {
    name: "fldXwBVMJfM83Wn39",
  },
};

const ALLOWED_LEVELS = new Set(["Business Unit","Region","Sub-region","Country Business Unit"]);

function clean(v){ return String(v ?? "").trim(); }
function norm(v){
  return clean(v).normalize("NFKD").replace(/[\u0300-\u036f]/g,"").toLowerCase()
    .replace(/&/g," and ").replace(/[^a-z0-9]+/g," ").trim().replace(/\s+/g," ");
}
function parseJson(v,label){
  if (v && typeof v === "object") return v;
  try { return JSON.parse(clean(v)); } catch(e){ throw new Error(`${label} must be valid JSON: ${e.message}`); }
}
function linkIds(v){ return Array.isArray(v) ? v.map(x=>x && x.id).filter(Boolean) : []; }
function selectName(v){ return v && typeof v === "object" ? clean(v.name) : clean(v); }
function semanticKey(u){
  const base = `${norm(u.name)}|${clean(u.level)}`;
  if (clean(u.level) !== "Country Business Unit") return base;
  return `${base}|${norm((u.markets||[])[0])}`;
}
function mappingKey(semKey,market){ return `${semKey}|market:${norm(market)}`; }
function httpsUrl(v){
  try { const u=new URL(clean(v)); return u.protocol==="https:" && !!u.hostname; } catch(_){ return false; }
}
function sameSetSubset(planned,approved){
  const a=new Set(approved);
  return planned.every(x=>a.has(x));
}
function primaryLabel(companyName,name,asOfDate){
  return `${companyName} | ${name} | as-of ${asOfDate}`;
}
function mappingLabel(companyName,market,name,asOfDate){
  return `${companyName} | ${market} | ${name} | as-of ${asOfDate}`;
}

async function loadState(companyRecordId){
  const defsT=base.getTable(TABLES.regionalDefinitions);
  const mapsT=base.getTable(TABLES.regionMarketMapping);
  const marketsT=base.getTable(TABLES.markets);
  const [dq,mq,mktq]=await Promise.all([
    defsT.selectRecordsAsync({fields:Object.values(F.regional)}),
    mapsT.selectRecordsAsync({fields:Object.values(F.mapping)}),
    marketsT.selectRecordsAsync({fields:[F.market.name]}),
  ]);
  const marketByNorm=new Map(mktq.records.map(r=>[norm(r.getCellValue(F.market.name)),{id:r.id,name:clean(r.getCellValue(F.market.name))}]));
  const mappingMarketsByDef=new Map();
  for(const r of mq.records){
    if(!linkIds(r.getCellValue(F.mapping.company)).includes(companyRecordId)) continue;
    const defIds=linkIds(r.getCellValue(F.mapping.region));
    const marketIds=linkIds(r.getCellValue(F.mapping.market));
    const names=[clean(r.getCellValue(F.mapping.marketName)),...marketIds.map(id=>{
      const hit=[...marketByNorm.values()].find(x=>x.id===id); return hit ? hit.name : "";
    })].filter(Boolean);
    for(const id of defIds){
      if(!mappingMarketsByDef.has(id)) mappingMarketsByDef.set(id,new Set());
      for(const n of names) mappingMarketsByDef.get(id).add(norm(n));
    }
  }
  const existing=[];
  for(const r of dq.records){
    if(!linkIds(r.getCellValue(F.regional.company)).includes(companyRecordId)) continue;
    const level=selectName(r.getCellValue(F.regional.level));
    const markets=[...(mappingMarketsByDef.get(r.id)||new Set())];
    existing.push({
      id:r.id,
      current:!!r.getCellValue(F.regional.current),
      name:clean(r.getCellValue(F.regional.name)),
      level,
      markets,
    });
  }
  return {defsT,mapsT,marketByNorm,existing,mappingMarketsByDef};
}

async function main(){
  const cfg=input.config();
  const companyRecordId=clean(cfg.companyRecordId);
  const companyName=clean(cfg.companyName);
  const research=parseJson(cfg.researchJson ?? cfg.research,"researchJson");
  const approval=parseJson(cfg.approvalJson ?? cfg.approval,"approvalJson");

  if(!companyRecordId || !companyName) throw new Error("companyRecordId and companyName are required");
  if(approval.approved !== true) throw new Error("Explicit approved=true manifest is required");
  if(!clean(approval.approvalLabel)) throw new Error("approvalLabel is required");
  if(research.structureDisclosureStatus !== "DISCLOSED_STRUCTURE") throw new Error("Writer requires DISCLOSED_STRUCTURE");
  if(!["FULL_CURRENT_STRUCTURE","PARTIAL_DISCLOSURE"].includes(research.structureCoverage)) throw new Error("Invalid structureCoverage");
  if(!["High","Medium"].includes(research.evidenceStrength)) throw new Error("Evidence strength must be High or Medium");
  if(!/^\d{4}-\d{2}-\d{2}$/.test(clean(research.asOfDate))) throw new Error("asOfDate must be YYYY-MM-DD");

  const units=(research.units||[]).map(u=>({
    name:clean(u.name),
    level:clean(u.level),
    markets:[...(Array.isArray(u.markets)?u.markets:(u.market?[u.market]:[]))].map(clean).filter(Boolean),
    current:u.current !== false,
    definitionScope:clean(u.definitionScope),
    sourceName:clean(u.sourceName)||clean(research.sourceName),
    sourceUrl:clean(u.sourceUrl)||clean(research.sourceUrl),
    verificationStatus:clean(u.verificationStatus)||"Verified",
    lastVerified:clean(u.lastVerified)||clean(research.asOfDate),
  }));

  const seen=new Set();
  for(const u of units){
    if(!u.name || !ALLOWED_LEVELS.has(u.level) || !u.definitionScope) throw new Error(`Invalid unit: ${JSON.stringify(u)}`);
    if(u.level==="Country Business Unit" && u.markets.length!==1) throw new Error(`Country Business Unit requires exactly one market: ${u.name}`);
    if(!httpsUrl(u.sourceUrl)) throw new Error(`Invalid source URL for ${u.name}`);
    const k=semanticKey(u);
    if(seen.has(k)) throw new Error(`Duplicate candidate semantic identity: ${k}`);
    seen.add(k);
  }

  const state=await loadState(companyRecordId);
  for(const u of units){
    for(const m of u.markets){
      if(!state.marketByNorm.has(norm(m))) throw new Error(`Market not in Markets master: ${m}`);
    }
  }

  const activeByKey=new Map();
  for(const e of state.existing.filter(x=>x.current)){
    const key = e.level==="Country Business Unit"
      ? `${norm(e.name)}|${e.level}|${[...e.markets][0]||""}`
      : `${norm(e.name)}|${e.level}`;
    if(!activeByKey.has(key)) activeByKey.set(key,[]);
    activeByKey.get(key).push(e);
  }
  for(const [k,v] of activeByKey) if(v.length>1) throw new Error(`Existing active duplicate semantic identity: ${k}`);

  const plannedDefs=[], noops=[];
  for(const u of units){
    const k=semanticKey(u);
    const ex=activeByKey.get(k)||[];
    if(ex.length===0) plannedDefs.push({key:k,unit:u});
    else noops.push({key:k,recordId:ex[0].id});
  }

  const approvedDefKeys=approval.approvedDefinitionKeys||[];
  const plannedDefKeys=plannedDefs.map(x=>x.key);
  if(!sameSetSubset(plannedDefKeys,approvedDefKeys)) throw new Error(`Unapproved definition create in plan: ${JSON.stringify(plannedDefKeys.filter(x=>!new Set(approvedDefKeys).has(x)))}`);
  const allCandidateKeys=new Set(units.map(semanticKey));
  for(const k of approvedDefKeys) if(!allCandidateKeys.has(k)) throw new Error(`Approval contains definition not in candidate snapshot: ${k}`);
  if(plannedDefs.length > Number(approval.maxDefinitionCreates ?? 0)) throw new Error("Definition create count exceeds approval");

  const idByKey=new Map(noops.map(x=>[x.key,x.recordId]));
  const createdDefs=[];
  if(plannedDefs.length){
    const payload=plannedDefs.map(({key,unit})=>({fields:{
      [F.regional.primary]:primaryLabel(companyName,unit.name,research.asOfDate),
      [F.regional.company]:[companyRecordId],
      [F.regional.name]:unit.name,
      [F.regional.level]:unit.level,
      [F.regional.current]:unit.current,
      [F.regional.definition]:unit.definitionScope,
      [F.regional.sourceName]:unit.sourceName,
      [F.regional.sourceUrl]:unit.sourceUrl,
      [F.regional.verification]:unit.verificationStatus,
      [F.regional.lastVerified]:unit.lastVerified,
    }}));
    const ids=await state.defsT.createRecordsAsync(payload);
    for(let i=0;i<ids.length;i++){
      idByKey.set(plannedDefs[i].key,ids[i]);
      createdDefs.push({semanticKey:plannedDefs[i].key,recordId:ids[i]});
    }
  }

  const plannedMappings=[];
  for(const u of units){
    if(u.level!=="Country Business Unit") continue;
    const key=semanticKey(u);
    const defId=idByKey.get(key);
    const existingMarkets=state.mappingMarketsByDef.get(defId)||new Set();
    for(const market of u.markets){
      if(!existingMarkets.has(norm(market))) plannedMappings.push({key:mappingKey(key,market),semanticKey:key,defId,market,unit:u});
    }
  }

  const approvedMapKeys=approval.approvedMappingKeys||[];
  const plannedMapKeys=plannedMappings.map(x=>x.key);
  if(!sameSetSubset(plannedMapKeys,approvedMapKeys)) throw new Error(`Unapproved market mapping in plan: ${JSON.stringify(plannedMapKeys.filter(x=>!new Set(approvedMapKeys).has(x)))}`);
  const allPossibleMapKeys=new Set(units.filter(u=>u.level==="Country Business Unit").flatMap(u=>u.markets.map(m=>mappingKey(semanticKey(u),m))));
  for(const k of approvedMapKeys) if(!allPossibleMapKeys.has(k)) throw new Error(`Approval contains mapping not in candidate snapshot: ${k}`);
  if(plannedMappings.length > Number(approval.maxMappingCreates ?? 0)) throw new Error("Mapping create count exceeds approval");

  const createdMappings=[];
  if(plannedMappings.length){
    const payload=plannedMappings.map(x=>{
      const mkt=state.marketByNorm.get(norm(x.market));
      return {fields:{
        [F.mapping.primary]:mappingLabel(companyName,mkt.name,x.unit.name,research.asOfDate),
        [F.mapping.company]:[companyRecordId],
        [F.mapping.market]:[mkt.id],
        [F.mapping.marketName]:mkt.name,
        [F.mapping.region]:[x.defId],
        [F.mapping.current]:true,
        [F.mapping.sourceName]:x.unit.sourceName,
        [F.mapping.sourceUrl]:x.unit.sourceUrl,
        [F.mapping.lastVerified]:x.unit.lastVerified,
        [F.mapping.notes]:`Approved Gate 1 mapping for ${x.unit.name}; bounded Company 360 structure evidence.`,
      }};
    });
    const ids=await state.mapsT.createRecordsAsync(payload);
    for(let i=0;i<ids.length;i++) createdMappings.push({mappingKey:plannedMappings[i].key,recordId:ids[i]});
  }

  const result={
    version:VERSION,
    approvalLabel:approval.approvalLabel,
    companyRecordId,
    companyName,
    plannedDefinitionCreates:plannedDefs.length,
    createdDefinitions:createdDefs,
    definitionNoops:noops,
    plannedMappingCreates:plannedMappings.length,
    createdMappings,
    updates:0,
    retirements:0,
    parentLinkWrites:0,
    completenessAuditWrites:0,
    portfolioWrites:0,
    masterPortfolioWrites:0,
    status:(createdDefs.length||createdMappings.length)?"APPROVED_WRITES_APPLIED":"IDEMPOTENT_NO_OP",
  };
  output.set("status",result.status);
  output.set("createdDefinitionCount",createdDefs.length);
  output.set("createdMappingCount",createdMappings.length);
  output.set("portfolioWrites",0);
  output.set("resultJson",JSON.stringify(result));
}

await main();
