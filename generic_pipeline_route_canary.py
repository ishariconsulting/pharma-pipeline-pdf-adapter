"""Read-only Vertex Q2 2026 investor presentation parser-fit diagnostic."""
import asyncio, json, re
import fitz
import httpx

import generic_pdf_pipeline_extension as pdf_table
import generic_pdf_grid_pipeline_extension as pdf_grid

URL="https://investors.vrtx.com/static-files/25a09e85-5615-46d3-8f28-7e5e75440a14"
COMPANY="Vertex Pharmaceuticals"

def compact_rows(rows):
    out=[]
    for r in rows[:50]:
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
    out={"url":URL,"documentProvenance":"VERTEX_OFFICIAL_IR_Q2_2026_PRESENTATION","masterWrites":0}
    headers={"User-Agent":"Mozilla/5.0","Accept":"application/pdf,*/*"}
    async with httpx.AsyncClient(timeout=35.0,follow_redirects=True,headers=headers) as c:
        try:
            r=await c.get(URL)
        except Exception as exc:
            out["fetchError"]=f"{type(exc).__name__}: {exc}"
            print("VERTEX_Q2_2026_PDF_FIT "+json.dumps(out,ensure_ascii=False),flush=True)
            return
    out.update({
      "status":r.status_code,
      "finalUrl":str(r.url),
      "contentType":r.headers.get("content-type"),
      "bytes":len(r.content),
    })
    if r.status_code != 200 or not r.content.startswith(b"%PDF"):
        out["fetchUsable"]=False
        try: out["bodyHead"]=r.text[:500]
        except Exception: pass
        print("VERTEX_Q2_2026_PDF_FIT "+json.dumps(out,ensure_ascii=False),flush=True)
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
    terms=("pipeline","phase 3","phase 2","phase 1","povetacicept","inaxaplin","suzetrigine","zimislecel","vx-")
    for pno in range(len(doc)):
        txt=re.sub(r"\s+"," ",doc[pno].get_text("text",sort=True)).strip()
        low=txt.lower()
        hits=sum(1 for t in terms if t in low)
        if hits>=2:
            pages.append({"page":pno+1,"hits":hits,"text":txt[:14000]})
    out["pipelineRelevantPages"]=pages[:12]
    out["pageCount"]=len(doc)
    print("VERTEX_Q2_2026_PDF_FIT "+json.dumps(out,ensure_ascii=False),flush=True)

if __name__=="__main__":
    asyncio.run(main())
