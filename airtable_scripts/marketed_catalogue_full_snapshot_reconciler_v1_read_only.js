/*
 * MARKETED_CATALOGUE_FULL_SNAPSHOT_RECONCILER_V1.0_READ_ONLY
 *
 * Shared fail-closed membership reconciler for authoritative Full Catalogue sources.
 * READ ONLY: this file plans Discovery status changes but never writes Airtable or Portfolio.
 *
 * Contract:
 * - Only a validated Full Catalogue snapshot can reconcile catalogue membership.
 * - Stable identity is Source Watch + Source Product Key.
 * - Products absent from a valid new full snapshot are review transitions only:
 *   Current / Source-listed -> Historical / Needs Validation.
 * - Never infer discontinuation, withdrawal, ownership change or Portfolio deletion from absence.
 * - Large extraction drops fail closed; no disappearance transitions are planned.
 */

const VERSION = "MARKETED_CATALOGUE_FULL_SNAPSHOT_RECONCILER_V1.0_READ_ONLY";
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

function planFullSnapshotReconciliation({
  sourceWatchRecordId,
  sourceScope,
  previousCandidateCount,
  extractedCandidates,
  existingDiscoveryRows
}) {
  const blocks = [];
  const sw = clean(sourceWatchRecordId);
  const scope = clean(sourceScope);
  const candidates = Array.isArray(extractedCandidates) ? extractedCandidates : [];
  const existing = Array.isArray(existingDiscoveryRows) ? existingDiscoveryRows : [];

  if (!sw) blocks.push("sourceWatchRecordId is required");
  if (scope !== "Full Catalogue") blocks.push(`Membership reconciliation requires Full Catalogue scope; received '${scope || "<blank>"}'`);

  const candidateKeys = candidates.map(x=>clean(x.sourceProductKey));
  if (candidateKeys.some(x=>!x)) blocks.push("Every extracted candidate requires a stable Source Product Key");
  const dupCandidateKeys = candidateKeys.filter((x,i,a)=>x && a.indexOf(x)!==i);
  if (dupCandidateKeys.length) blocks.push(`Duplicate candidate Source Product Key(s): ${unique(dupCandidateKeys).join(", ")}`);

  if (candidates.length < MIN_CANDIDATE_COUNT) {
    blocks.push(`Candidate count ${candidates.length} is below minimum guardrail ${MIN_CANDIDATE_COUNT}`);
  }

  const prev = Number(previousCandidateCount || 0);
  if (prev >= MIN_PREVIOUS_COUNT_FOR_RATIO_GUARD && candidates.length / prev < DISAPPEARANCE_MIN_RATIO) {
    blocks.push(`Candidate-count ratio ${(candidates.length/prev).toFixed(3)} is below disappearance guardrail ${DISAPPEARANCE_MIN_RATIO}; possible truncated/restructured extraction`);
  }

  const currentKeys = new Set(candidateKeys.filter(Boolean));
  const currentLinked = existing.filter(r =>
    clean(r.catalogueStatus) === "Current / Source-listed" &&
    Array.isArray(r.sourceWatchRecordIds) &&
    r.sourceWatchRecordIds.includes(sw)
  );

  const duplicateExisting = new Map();
  for (const r of currentLinked) {
    const k=clean(r.sourceProductKey);
    if(!k) continue;
    if(!duplicateExisting.has(k)) duplicateExisting.set(k,[]);
    duplicateExisting.get(k).push(r.id);
  }
  for(const [k,ids] of duplicateExisting){
    if(ids.length>1) blocks.push(`Multiple active Discovery rows share source identity ${sw}|${k}: ${ids.join(",")}`);
  }

  const disappearanceReview=[];
  const retainedCurrent=[];
  if(!blocks.length){
    for(const r of currentLinked){
      const key=clean(r.sourceProductKey);
      if(!key){
        disappearanceReview.push({
          recordId:r.id,
          sourceProductKey:"",
          product:clean(r.brand),
          action:"HOLD_UNADDRESSABLE",
          reason:"Current source-linked row has no stable Source Product Key; do not change automatically."
        });
        continue;
      }
      if(currentKeys.has(key)){
        retainedCurrent.push({recordId:r.id,sourceProductKey:key,product:clean(r.brand)});
      } else {
        disappearanceReview.push({
          recordId:r.id,
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
  const old=(n)=>Array.from({length:n},(_,i)=>({
    id:`recOLD${i}`,brand:`Product ${i+1}`,
    sourceProductKey:`MKT1|company:recC|product:p${i+1}`,
    catalogueStatus:"Current / Source-listed",
    sourceWatchRecordIds:[sw]
  }));
  const cand=(n)=>Array.from({length:n},(_,i)=>({sourceProductKey:`MKT1|company:recC|product:p${i+1}`}));

  const p1=planFullSnapshotReconciliation({sourceWatchRecordId:sw,sourceScope:"Full Catalogue",previousCandidateCount:29,extractedCandidates:cand(28),existingDiscoveryRows:old(29)});
  if(p1.status!=="PASS_PLAN"||p1.plannedHistoricalReviewCount!==1) throw new Error("small delta test failed");

  const p2=planFullSnapshotReconciliation({sourceWatchRecordId:sw,sourceScope:"Full Catalogue",previousCandidateCount:29,extractedCandidates:cand(10),existingDiscoveryRows:old(29)});
  if(p2.status!=="BLOCK"||p2.plannedHistoricalReviewCount!==0) throw new Error("large drop fail-closed test failed");

  const p3=planFullSnapshotReconciliation({sourceWatchRecordId:sw,sourceScope:"Partial Catalogue",previousCandidateCount:29,extractedCandidates:cand(28),existingDiscoveryRows:old(29)});
  if(p3.status!=="BLOCK") throw new Error("partial scope block failed");

  const p4=planFullSnapshotReconciliation({sourceWatchRecordId:sw,sourceScope:"Full Catalogue",previousCandidateCount:29,extractedCandidates:cand(29),existingDiscoveryRows:old(29)});
  if(p4.status!=="PASS_PLAN"||p4.plannedHistoricalReviewCount!==0||p4.retainedCurrent.length!==29) throw new Error("idempotence test failed");

  const dup=cand(8); dup.push({sourceProductKey:dup[0].sourceProductKey});
  const p5=planFullSnapshotReconciliation({sourceWatchRecordId:sw,sourceScope:"Full Catalogue",previousCandidateCount:9,extractedCandidates:dup,existingDiscoveryRows:old(9)});
  if(p5.status!=="BLOCK") throw new Error("duplicate candidate block failed");

  const other=old(8); other.push({id:"recOTHER",brand:"Other source",sourceProductKey:"OTHER1",catalogueStatus:"Current / Source-listed",sourceWatchRecordIds:["recOTHER_SOURCE"]});
  const p6=planFullSnapshotReconciliation({sourceWatchRecordId:sw,sourceScope:"Full Catalogue",previousCandidateCount:8,extractedCandidates:cand(8),existingDiscoveryRows:other});
  if(p6.status!=="PASS_PLAN"||p6.retainedCurrent.length!==8||p6.disappearanceReview.length!==0) throw new Error("source isolation test failed");

  return {ok:true,version:VERSION,tests:6};
}

if (typeof module !== "undefined") module.exports={planFullSnapshotReconciliation,selfTest};
