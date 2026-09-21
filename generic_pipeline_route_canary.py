"""Read-only normalized pipeline-source canary for Gilead, Ionis and Amgen."""
import asyncio, json, re, html as html_lib
import httpx
from generic_pdf_pipeline_extension import extract_generic_pdf

HEADERS={"User-Agent":"Mozilla/5.0 GenericPipelineNormalizedCanary/1.0","Accept":"application/json,text/html,*/*;q=0.8"}
GILEAD_URL="https://www.gilead.com/sxa/search/results/?v=%7B16E72BF3-7230-403E-BB34-EAE20C26BD0F%7D&s=%7BB5AA5689-719C-4965-8E20-4B67741FF639%7D&l=en&p=100&defaultSortOrder=Pipeline%20Therapeutic%20Areas%2CDescending&sig=pipeline&itemid=%7BEFC74AF2-1C5C-4D7C-BACD-F20CD4FF35AA%7D&autoFireSearch=true"
AMGEN_PDF="https://www.amgenpipeline.com/-/media/Themes/Amgen/amgenpipeline-com/amgenpipeline-com/PDF/amgen-pipeline-chart.pdf"

def text_only(raw):
    s=html_lib.unescape(raw or "")
    s=re.sub(r"<[^>]+>"," ",s)
    return re.sub(r"\s+"," ",s).strip()

def field(raw,cls):
    m=re.search(r'class="[^"]*\b'+re.escape(cls)+r'\b[^"]*"[^>]*>([\s\S]*?)</div>',raw,re.I)
    return text_only(m.group(1)) if m else ""

def canonical_phase(v):
    n=str(v or "").strip().lower()
    if n in {"1","phase 1","phase i"}: return "Phase 1"
    if n in {"2","phase 2","phase ii"}: return "Phase 2"
    if n in {"3","phase 3","phase iii"}: return "Phase 3"
    if "approved" in n: return "Approved"
    if "filed" in n or "registration" in n: return "Filed / Registration"
    return ""

async def gilead(c):
    r=await c.get(GILEAD_URL); data=r.json()
    rows=[]
    for item in data.get("Results") or []:
        raw=item.get("Html") or ""
        asset=field(raw,"field-headbrandname")
        indication=field(raw,"field-potentialindication")
        phase=canonical_phase(field(raw,"phase-name"))
        ta=field(raw,"field-therapeuticareaname")
        if asset and indication and phase:
            rows.append({"asset":asset,"indication":indication,"phase":phase,"therapeuticArea":ta,"id":item.get("Id")})
    print("GILEAD_NORMALIZED_CANARY "+json.dumps({
      "sourceCount":data.get("Count"),"parsedRows":len(rows),
      "coreComplete":sum(1 for x in rows if x["asset"] and x["indication"] and x["phase"]),
      "phaseCounts":{p:sum(1 for x in rows if x["phase"]==p) for p in sorted(set(x["phase"] for x in rows))},
      "sample":rows[:10],"masterWrites":0
    },ensure_ascii=False),flush=True)

async def ionis(c):
    rows=[]
    counts={}
    for family,url in [
      ("Owned","https://ionis.com/pipeline/independent?_format=json"),
      ("Partnered","https://ionis.com/pipeline/partnered?_format=json"),
    ]:
      r=await c.get(url); data=r.json(); counts[family]=len(data)
      for item in data:
        phase=canonical_phase(item.get("phase"))
        row={
          "asset":re.sub(r"\*+$","",str(item.get("drug_name") or "")).strip(),
          "target":str(item.get("generic") or "").strip(),
          "indication":str(item.get("disease") or "").strip(),
          "phase":phase,
          "therapeuticArea":str(item.get("therapeutic_area") or "").strip(),
          "partner":item.get("partner"),
          "family":family,
          "changed":item.get("changed"),
        }
        if row["asset"] and row["indication"] and row["phase"]: rows.append(row)
    keys=set()
    dup=0
    for row in rows:
      k=(row["asset"].lower(),row["indication"].lower(),row["phase"].lower(),str(row["partner"]).lower())
      if k in keys: dup+=1
      keys.add(k)
    print("IONIS_NORMALIZED_CANARY "+json.dumps({
      "sourceCounts":counts,"parsedRows":len(rows),"exactDuplicates":dup,
      "phaseCounts":{p:sum(1 for x in rows if x["phase"]==p) for p in sorted(set(x["phase"] for x in rows))},
      "sample":rows[:12],"masterWrites":0
    },ensure_ascii=False),flush=True)

async def amgen():
    try:
      r=await extract_generic_pdf("Amgen",AMGEN_PDF,35.0)
      print("AMGEN_PDF_CANARY "+json.dumps({
        "readyForDiscovery":r.readyForDiscovery,"rowCount":r.rowCount,
        "issues":[x.get("issue") for x in r.issues],
        "summary":r.summary,"diagnostics":r.diagnostics,
        "sample":r.rows[:10],"masterWrites":0
      },ensure_ascii=False),flush=True)
    except Exception as exc:
      print("AMGEN_PDF_CANARY "+json.dumps({"readyForDiscovery":False,"error":f"{type(exc).__name__}: {exc}","masterWrites":0},ensure_ascii=False),flush=True)

async def main():
  async with httpx.AsyncClient(timeout=35.0,follow_redirects=True,headers=HEADERS) as c:
    await gilead(c); await ionis(c)
  await amgen()

if __name__=="__main__":
  asyncio.run(main())
