"""Read-only Boehringer 2025 annual-report mirror parser-fit diagnostic.

The URL is a third-party mirror of Boehringer Ingelheim's 2025 Highlights
document. This is validation/backfill research only, never canonical live
pipeline monitoring and never a master-data write.
"""
import asyncio, json, re
import fitz
import httpx

import generic_pdf_pipeline_extension as pdf_table
import generic_pdf_grid_pipeline_extension as pdf_grid

URL="https://flcube.com/wp-content/uploads/2026/03/Boehringer-Ingelheim-Annual-Report-Highlights-2025.pdf"
COMPANY="Boehringer Ingelheim"

def compact_rows(rows):
    out=[]
    for r in rows[:30]:
        out.append({
          "asset":r.get("asset") or r.get("developmentCode") or r.get("brand"),
          "molecule":r.get("molecule"),
          "developmentCode":r.get("developmentCode"),
          "indication":r.get("indication"),
          "phase":r.get("phase"),
          "therapeuticArea":r.get("therapeuticArea"),
        })
    return out

async def main():
    out={"url":URL,"documentProvenance":"THIRD_PARTY_MIRROR_OF_BOEHRINGER_2025_HIGHLIGHTS","masterWrites":0}
    headers={"User-Agent":"Mozilla/5.0","Accept":"application/pdf,*/*"}
    async with httpx.AsyncClient(timeout=35.0,follow_redirects=True,headers=headers) as c:
        try:
            r=await c.get(URL)
        except Exception as exc:
            out["fetchError"]=f"{type(exc).__name__}: {exc}"
            print("BOEHRINGER_2025_PDF_FIT "+json.dumps(out,ensure_ascii=False),flush=True)
            return
    out.update({
      "status":r.status_code,
      "finalUrl":str(r.url),
      "contentType":r.headers.get("content-type"),
      "bytes":len(r.content),
    })
    if r.status_code != 200 or not r.content.startswith(b"%PDF"):
        out["fetchUsable"]=False
        out["bodyHead"]=r.text[:500] if "text" in (r.headers.get("content-type") or "") else None
        print("BOEHRINGER_2025_PDF_FIT "+json.dumps(out,ensure_ascii=False),flush=True)
        return

    data=r.content
    out["fetchUsable"]=True
    try:
        rows1,diag1=pdf_table.parse_semantic_pdf(COMPANY,URL,data)
        out["genericPdfTable"]={"rows":len(rows1),"diagnostics":diag1,"sample":compact_rows(rows1)}
    except Exception as exc:
        out["genericPdfTable"]={"error":f"{type(exc).__name__}: {exc}"}
    try:
        rows2,diag2=pdf_grid.parse_semantic_pdf_grid(COMPANY,URL,data)
        out["semanticPdfGrid"]={"rows":len(rows2),"diagnostics":diag2,"sample":compact_rows(rows2)}
    except Exception as exc:
        out["semanticPdfGrid"]={"error":f"{type(exc).__name__}: {exc}"}

    doc=fitz.open(stream=data,filetype="pdf")
    pages=[]
    for pno in range(len(doc)):
        txt=re.sub(r"\s+"," ",doc[pno].get_text("text",sort=True)).strip()
        low=txt.lower()
        if "overview of our projects" in low or "development status at the end of 2025" in low:
            pages.append({"page":pno+1,"text":txt[:12000]})
    out["pipelinePages"]=pages[:5]
    out["pageCount"]=len(doc)
    print("BOEHRINGER_2025_PDF_FIT "+json.dumps(out,ensure_ascii=False),flush=True)

if __name__=="__main__":
    asyncio.run(main())
