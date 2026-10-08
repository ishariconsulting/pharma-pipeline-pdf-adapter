/*
 * MARKETED_CATALOGUE_FULL_SNAPSHOT_RECONCILER_V1.0_READ_ONLY
 *
 * Shared fail-closed membership reconciler for authoritative Full Catalogue sources.
 * READ ONLY: this file plans Discovery status changes but never writes Airtable or Portfolio.
 *
 * Contract:
 * - Only a validated Full Catalogue snapshot can reconcile catalogue membership.
 * - Cross-route membership identity is Company + normalized canonical Brand / Product Family.
 * - Source Product Key remains route/provenance metadata; MKT1 remains the downstream
 *   canonical full-catalogue key and is never overwritten merely to reconcile membership.
 * - Products absent from a valid new full snapshot are review transitions only:
 *   Current / Source-listed -> Historical / Needs Validation.
 * - Never infer discontinuation, withdrawal, ownership change or Portfolio deletion from absence.
 * - Large extraction drops fail closed; no disappearance transitions are planned.
 */

const VERSION = "MARKETED_CATALOGUE_FULL_SNAPSHOT_RECONCILER_V1.1_ROUTE_NEUTRAL_FAMILY_IDENTITY_READ_ONLY";
const APPLY_WRITES = false;
const MIN_CANDIDATE_COUNT = 4;
const MIN_PREVIOUS_COUNT_FOR_RATIO_GUARD = 8;
const DISAPPEARANCE_MIN_RATIO = 0.75;

function clean(v){ return String(v ?? "").trim(); }
function norm(v){
  return clean(v).toLowerCase().normalize("NFKD")
    .replace(/[\u0300-\u036f]/g,"")
    .replace(/[®™©]/g,"")
    .replace(/[^a-z0-9]+/g," ")
    .trim().replace(/\s+/g," ");
}
function unique(xs){ return [...new Set((xs||[]).filter(Boolean))]; }
function familyKey(companyRecordId, brand){
  const company=clean(companyRecordId);
  const b=norm(brand);
  return company && b ? `${company}|${b}` : "";
}

function planFullSnapshotReconciliation({
  sourceWatchRecordId,
  companyRecordId,
  sourceScope,
  previousCandidateCount,
  extractedCandidates,
  existingDiscoveryRows
}) {
  const blocks = [];
  const sw = clean(sourceWatchRecordId);
  const company = clean(companyRecordId);
  const scope = clean(sourceScope);
  const candidates = Array.isArray(extractedCandidates) ? extractedCandidates : [];
  const existing = Array.isArray(existingDiscoveryRows) ? existingDiscoveryRows : [];

  if (!sw) blocks.push("sourceWatchRecordId is required");
  if (!company) blocks.push("companyRecordId is required");
  if (scope !== "Full Catalogue") blocks.push(`Membership reconciliation requires Full Catalogue scope; received '${scope || "<blank>"}'`);

  const candidateFamilyKeys = candidates.map(x=>familyKey(company, x.brand));
  if (candidateFamilyKeys.some(x=>!x)) blocks.push("Every extracted candidate requires a canonical Brand / Product Family");
  const dupCandidateFamilies = candidateFamilyKeys.filter((x,i,a)=>x && a.indexOf(x)!==i);
  if (dupCandidateFamilies.length) blocks.push(`Duplicate candidate company-family identity/identities: ${unique(dupCandidateFamilies).join(", ")}`);

  if (candidates.length < MIN_CANDIDATE_COUNT) {
    blocks.push(`Candidate count ${candidates.length} is below minimum guardrail ${MIN_CANDIDATE_COUNT}`);
  }

  const prev = Number(previousCandidateCount || 0);
  if (prev >= MIN_PREVIOUS_COUNT_FOR_RATIO_GUARD && candidates.length / prev < DISAPPEARANCE_MIN_RATIO) {
    blocks.push(`Candidate-count ratio ${(candidates.length/prev).toFixed(3)} is below disappearance guardrail ${DISAPPEARANCE_MIN_RATIO}; possible truncated/restructured extraction`);
  }

  const currentFamilies = new Set(candidateFamilyKeys.filter(Boolean));
  const currentLinked = existing.filter(r =>
    clean(r.catalogueStatus) === "Current / Source-listed" &&
    clean(r.companyRecordId) === company &&
    Array.isArray(r.sourceWatchRecordIds) &&
    r.sourceWatchRecordIds.includes(sw)
  );

  const duplicateExisting = new Map();
  for (const r of currentLinked) {
    const k=familyKey(company, r.brand);
    if(!k) {
      blocks.push(`Current source-linked Discovery row ${r.id} has no canonical Brand / Product Family`);
      continue;
    }
    if(!duplicateExisting.has(k)) duplicateExisting.set(k,[]);
    duplicateExisting.get(k).push(r.id);
  }
  for(const [k,ids] of duplicateExisting){
    if(ids.length>1) blocks.push(`Multiple active Discovery rows share company-family identity ${k}: ${ids.join(",")}`);
  }

  const disappearanceReview=[];
  const retainedCurrent=[];
  if(!blocks.length){
    for(const r of currentLinked){
      const key=clean(r.sourceProductKey);
      const fk=familyKey(company, r.brand);
      if(currentFamilies.has(fk)){
        retainedCurrent.push({recordId:r.id,familyIdentity:fk,sourceProductKey:key,product:clean(r.brand)});
      } else {
        disappearanceReview.push({
          recordId:r.id,
          familyIdentity:fk,
          sourceProductKey:key,
          product:clean(r.brand),
          action:"PLAN_HISTORICAL_NEEDS_VALIDATION",
          proposedCatalogueStatus:"Historical / Needs Validation",
          reason:"Absent from latest validated Full Catalogue snapshot. Review source change; absence alone is not evidence of discontinuation, withdrawal, ownership change or Portfolio deletion."
        });
      }
    }
  }

  return {
    version:VERSION,
    mode:APPLY_WRITES?"WRITE_ENABLED":"READ_ONLY_ZERO_WRITES",
    sourceWatchRecordId:sw,
    companyRecordId:company,
    sourceScope:scope,
    previousCandidateCount:prev,
    candidateCount:candidates.length,
    candidateRatio:prev>0?candidates.length/prev:null,
    status:blocks.length?"BLOCK":"PASS_PLAN",
    blocks,
    retainedCurrent,
    disappearanceReview,
    plannedHistoricalReviewCount:disappearanceReview.filter(x=>x.action==="PLAN_HISTORICAL_NEEDS_VALIDATION").length,
    airtableWrites:0,
    portfolioWrites:0
  };
}

function selfTest(){
  const sw="recSOURCE";
  const company="recC";
  const old=(n,prefix="MKT1")=>Array.from({length:n},(_,i)=>({
    id:`recOLD${i}`,companyRecordId:company,brand:`Product ${i+1}`,
    sourceProductKey: prefix==="MKT1" ? `MKT1|company:${company}|product:p${i+1}` : `MPD1|${company}|product ${i+1}`,
    catalogueStatus:"Current / Source-listed",
    sourceWatchRecordIds:[sw]
  }));
  const cand=(n,prefix="MPD1")=>Array.from({length:n},(_,i)=>({
    brand:`Product ${i+1}`,
    sourceProductKey: prefix==="MKT1" ? `MKT1|company:${company}|product:p${i+1}` : `MPD1|${company}|product ${i+1}`
  }));

  const p1=planFullSnapshotReconciliation({sourceWatchRecordId:sw,companyRecordId:company,sourceScope:"Full Catalogue",previousCandidateCount:29,extractedCandidates:cand(28),existingDiscoveryRows:old(29)});
  if(p1.status!=="PASS_PLAN"||p1.plannedHistoricalReviewCount!==1) throw new Error("small delta test failed");

  const p2=planFullSnapshotReconciliation({sourceWatchRecordId:sw,companyRecordId:company,sourceScope:"Full Catalogue",previousCandidateCount:29,extractedCandidates:cand(10),existingDiscoveryRows:old(29)});
  if(p2.status!=="BLOCK"||p2.plannedHistoricalReviewCount!==0) throw new Error("large drop fail-closed test failed");

  const p3=planFullSnapshotReconciliation({sourceWatchRecordId:sw,companyRecordId:company,sourceScope:"Partial Catalogue",previousCandidateCount:29,extractedCandidates:cand(28),existingDiscoveryRows:old(29)});
  if(p3.status!=="BLOCK") throw new Error("partial scope block failed");

  const p4=planFullSnapshotReconciliation({sourceWatchRecordId:sw,companyRecordId:company,sourceScope:"Full Catalogue",previousCandidateCount:29,extractedCandidates:cand(29),existingDiscoveryRows:old(29)});
  if(p4.status!=="PASS_PLAN"||p4.plannedHistoricalReviewCount!==0||p4.retainedCurrent.length!==29) throw new Error("idempotence test failed");

  const dup=cand(8); dup.push({brand:dup[0].brand,sourceProductKey:"DIFFERENT_ROUTE_KEY"});
  const p5=planFullSnapshotReconciliation({sourceWatchRecordId:sw,companyRecordId:company,sourceScope:"Full Catalogue",previousCandidateCount:9,extractedCandidates:dup,existingDiscoveryRows:old(9)});
  if(p5.status!=="BLOCK") throw new Error("duplicate candidate block failed");

  const other=old(8); other.push({id:"recOTHER",companyRecordId:company,brand:"Other source",sourceProductKey:"OTHER1",catalogueStatus:"Current / Source-listed",sourceWatchRecordIds:["recOTHER_SOURCE"]});
  const p6=planFullSnapshotReconciliation({sourceWatchRecordId:sw,companyRecordId:company,sourceScope:"Full Catalogue",previousCandidateCount:8,extractedCandidates:cand(8),existingDiscoveryRows:other});
  if(p6.status!=="PASS_PLAN"||p6.retainedCurrent.length!==8||p6.disappearanceReview.length!==0) throw new Error("source isolation test failed");

  const crossRoute=planFullSnapshotReconciliation({
    sourceWatchRecordId:sw,companyRecordId:company,sourceScope:"Full Catalogue",
    previousCandidateCount:8,extractedCandidates:cand(8,"MPD1"),existingDiscoveryRows:old(8,"MKT1")
  });
  if(crossRoute.status!=="PASS_PLAN"||crossRoute.plannedHistoricalReviewCount!==0||crossRoute.retainedCurrent.length!==8) {
    throw new Error("cross-route MKT1/MPD1 family identity test failed");
  }

  return {ok:true,version:VERSION,tests:7};
}

if (typeof module !== "undefined") module.exports={planFullSnapshotReconciliation,selfTest};
