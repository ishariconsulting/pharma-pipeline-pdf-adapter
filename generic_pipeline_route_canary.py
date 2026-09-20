"""Read-only combined pipeline-source canary.

1) Boundary QA for Takeda's official pipeline PDF using the reusable semantic
   PDF-table adapter.
2) Structural HTML extraction for Bayer, Roche and argenx official pipeline
   pages using the generic HTML interpreter.
No Airtable or master-data writes.
"""
import asyncio, json
from generic_pdf_pipeline_extension import download_pdf, parse_semantic_pdf, extract_generic_pdf, norm
from generic_pipeline_extension import _extract_generic_pipeline

TAKEDA_URL="https://assets-dam.takeda.com/image/upload/v1785376660/Global/Investor/Financial-Results/FY2026/Q1/qr2026_q1_Pipeline_table_en.pdf"
HTML_SOURCES=[
 ("Bayer","https://www.bayer.com/en/pharma/development-pipeline"),
 ("Roche","https://www.roche.com/solutions/pipeline"),
 ("argenx SE","https://argenx.com/pipeline"),
]

def suspicious_pairs(rows):
    out=[]
    ordered=sorted(rows,key=lambda r:(int(r.get("sourcePage") or 0),float(r.get("sourceStageY") or 0)))
    for prev,cur in zip(ordered,ordered[1:]):
        if prev.get("sourcePage")!=cur.get("sourcePage"):
            continue
        dy=abs(float(cur.get("sourceStageY") or 0)-float(prev.get("sourceStageY") or 0))
        if dy>30 or norm(prev.get("developmentCode"))==norm(cur.get("developmentCode")):
            continue
        a=set(norm(prev.get("indication")).split()); b=set(norm(cur.get("indication")).split())
        sim=(len(a&b)/max(1,min(len(a),len(b)))) if a and b else 0
        if sim>=0.55:
            out.append({
              "page":prev.get("sourcePage"),
              "y1":prev.get("sourceStageY"),"y2":cur.get("sourceStageY"),
              "code1":prev.get("developmentCode"),"code2":cur.get("developmentCode"),
              "indication1":prev.get("indication"),"indication2":cur.get("indication"),
              "tokenOverlap":round(sim,3),
            })
    return out

async def takeda():
    data,final=await download_pdf(TAKEDA_URL,35.0)
    rows,diag=parse_semantic_pdf("Takeda",final,data)
    full=await extract_generic_pdf("Takeda",TAKEDA_URL,35.0)
    print("TAKEDA_PDF_FINAL_QA "+json.dumps({
      "readyForDiscovery":full.readyForDiscovery,
      "rowCount":full.rowCount,
      "issues":[x.get("issue") for x in full.issues],
      "rowFailures":diag.get("rowFailures"),
      "boundaryWarnings":diag.get("boundaryWarnings"),
      "boundaryRepairs":diag.get("boundaryRepairs"),
      "boundaryRepairSamples":diag.get("boundaryRepairSamples"),
      "suspiciousPairs":suspicious_pairs(rows),
      "masterWrites":0,
    },ensure_ascii=False),flush=True)

async def html_one(company,url):
    try:
        r=await _extract_generic_pipeline(company=company,source_url=url,timeout_seconds=28.0)
        payload={
          "company":company,
          "readyForDiscovery":r.readyForDiscovery,
          "rowCount":r.rowCount,
          "retrievalMode":r.summary.get("retrievalMode"),
          "routingReason":r.summary.get("routingReason"),
          "selectedMethod":r.summary.get("selectedMethod"),
          "issues":[x.get("issue") for x in r.issues],
          "semanticTableRows":r.diagnostics.get("semanticTableRows"),
          "labelledFlowRows":r.diagnostics.get("labelledFlowRows"),
          "tableCount":r.diagnostics.get("tableCount"),
          "portfolioDependentValidation":r.diagnostics.get("portfolioDependentValidation"),
          "sampleRows":r.rows[:5],
          "masterWrites":0,
        }
    except Exception as exc:
        payload={"company":company,"readyForDiscovery":False,"error":f"{type(exc).__name__}: {exc}","masterWrites":0}
    print("GENERIC_HTML_PIPELINE_CANARY "+json.dumps(payload,ensure_ascii=False),flush=True)

async def main():
    await takeda()
    for company,url in HTML_SOURCES:
        await html_one(company,url)

if __name__=="__main__":
    asyncio.run(main())
