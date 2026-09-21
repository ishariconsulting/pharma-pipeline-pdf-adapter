"""Read-only Roche page-4 phase-column row diagnostic."""
import asyncio, json, fitz
from generic_pdf_pipeline_extension import download_pdf, parse_phase_column_pdf, _word_center_y, clean

URL="https://assets.roche.com/f/176343/x/cb875526bd/pharmahy26.pdf"

async def main():
    data,final=await download_pdf(URL,35.0)
    rows,diag=parse_phase_column_pdf("Roche",final,data)
    pdiag=next(p for p in diag["pages"] if p["page"]==4)
    doc=fitz.open(stream=data,filetype="pdf")
    page=doc[3]
    words=page.get_text("words")
    cols=[]
    for ci,c in enumerate(pdiag["columns"]):
        left=float(c["left"]); right=float(c["right"])
        grouped={}
        for w in words:
            y=_word_center_y(w)
            if 108<=y<=455 and left<=float(w[0])<right:
                key=round(y/2)*2
                grouped.setdefault(key,[]).append(w)
        lines=[]
        for y,ws in sorted(grouped.items()):
            txt=clean(" ".join(str(w[4]) for w in sorted(ws,key=lambda q:float(q[0]))))
            if txt:
                lines.append({"y":y,"text":txt})
        cols.append({"column":ci+1,"phase":c["phase"],"left":left,"right":right,"lines":lines})
    print("ROCHE_P4_COLUMN_LINES "+json.dumps({
      "rowCount":len(rows),
      "declaredProgrammes":diag.get("declaredProgrammes"),
      "columns":cols,
      "masterWrites":0
    },ensure_ascii=False),flush=True)

if __name__=="__main__":
    asyncio.run(main())
