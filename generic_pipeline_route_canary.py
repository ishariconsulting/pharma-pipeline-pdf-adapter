"""Read-only Roche targeted word-coordinate diagnostic."""
import asyncio, json, fitz
from generic_pdf_pipeline_extension import download_pdf, _word_center_y

URL="https://assets.roche.com/f/176343/x/cb875526bd/pharmahy26.pdf"

async def main():
    data,final=await download_pdf(URL,35.0)
    page=fitz.open(stream=data,filetype="pdf")[3]
    words=page.get_text("words")
    targets=[144,150,156,182,194,198,204,216,240,246,252,178,190,196,200,212]
    out=[]
    for target in targets:
        ws=[w for w in words if abs(_word_center_y(w)-target)<=3.0]
        if ws:
            out.append({
              "target":target,
              "words":[{"x0":round(float(w[0]),1),"x1":round(float(w[2]),1),"t":str(w[4])} for w in sorted(ws,key=lambda q:float(q[0]))]
            })
    print("ROCHE_TARGET_COORDS "+json.dumps({"rows":out,"masterWrites":0},ensure_ascii=False),flush=True)

if __name__=="__main__":
    asyncio.run(main())
