"""Read-only Roche pipeline PDF geometry diagnostic."""
import asyncio, json, fitz
from generic_pdf_pipeline_extension import download_pdf, clean

URL="https://assets.roche.com/f/176343/x/cb875526bd/pharmahy26.pdf"

def line_groups(words):
    rows={}
    for w in words:
        x0,y0,x1,y1,txt,*_=w
        key=round(((y0+y1)/2)/2)*2
        rows.setdefault(key,[]).append((x0,txt))
    out=[]
    for y,items in sorted(rows.items()):
        text=clean(" ".join(t for _,t in sorted(items)))
        if text:
            out.append({"y":round(y,1),"items":[{"x":round(float(x),1),"t":t} for x,t in sorted(items)],"text":text})
    return out

async def main():
    data,final=await download_pdf(URL,35.0)
    doc=fitz.open(stream=data,filetype="pdf")
    for idx in [2,3]:
        page=doc[idx]
        lines=line_groups(page.get_text("words"))
        picked=[r for r in lines if (
            "Phase I" in r["text"] or "Phase II" in r["text"] or "Phase III" in r["text"] or
            "Registration" in r["text"] or r["text"].startswith("RG") or r["text"].startswith("CHU")
        )][:120]
        print("ROCHE_GEOMETRY "+json.dumps({
          "page":idx+1,"width":page.rect.width,"height":page.rect.height,
          "lines":picked
        },ensure_ascii=False),flush=True)

if __name__=="__main__":
    asyncio.run(main())
