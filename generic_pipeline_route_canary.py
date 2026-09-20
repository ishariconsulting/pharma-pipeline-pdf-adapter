"""Focused read-only QA for generic PDF pipeline parser."""
import asyncio, json
from generic_pdf_pipeline_extension import download_pdf, parse_semantic_pdf, extract_generic_pdf, norm

URL="https://assets-dam.takeda.com/image/upload/v1785376660/Global/Investor/Financial-Results/FY2026/Q1/qr2026_q1_Pipeline_table_en.pdf"

def suspicious_pairs(rows):
    out=[]
    prev=None
    for r in rows:
        if prev and r.get("sourcePage")==prev.get("sourcePage"):
            try:
                y1=int(str(prev.get("sourceRecordId","")).split(":y")[-1])
                y2=int(str(r.get("sourceRecordId","")).split(":y")[-1])
            except Exception:
                y1=y2=9999
            a=set(norm(prev.get("indication","")).split())
            b=set(norm(r.get("indication","")).split())
            sim=(len(a&b)/max(1,min(len(a),len(b)))) if a and b else 0
            if abs(y2-y1)<=30 and prev.get("developmentCode")!=r.get("developmentCode") and sim>=0.55:
                out.append({"prev":prev,"next":r,"tokenOverlap":round(sim,3)})
        prev=r
    return out

async def main():
    data,final=await download_pdf(URL,35.0)
    rows,diag=parse_semantic_pdf("Takeda",final,data)
    print("TAKEDA_PDF_FOCUSED_QA "+json.dumps({
      "rows":len(rows),
      "rowFailures":diag.get("rowFailures"),
      "failureSamples":diag.get("failureSamples"),
      "pageDiagnostics":diag.get("pages"),
      "suspiciousPairs":suspicious_pairs(rows),
    },ensure_ascii=False),flush=True)

if __name__=="__main__":
    asyncio.run(main())
