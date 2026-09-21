"""Read-only Amgen PDF row geometry diagnostic."""
import asyncio, json, re, fitz
from generic_pdf_pipeline_extension import download_pdf

URL="https://www.amgenpipeline.com/-/media/Themes/Amgen/amgenpipeline-com/amgenpipeline-com/PDF/amgen-pipeline-chart.pdf"

def clean(v): return re.sub(r"\s+"," ",str(v or "")).strip()
def join(ws): return clean(" ".join(str(w[4]) for w in sorted(ws,key=lambda q:q[0])))

async def main():
  data,final=await download_pdf(URL,35.0)
  doc=fitz.open(stream=data,filetype="pdf")
  out=[]
  for pi in range(len(doc)):
    p=doc[pi]; words=p.get_text("words")
    by={}
    for w in words:
      cy=(float(w[1])+float(w[3]))/2
      if cy<150 or cy>635: continue
      key=round(cy/2)*2
      by.setdefault(key,[]).append(w)
    lines=[]
    for y,ws in sorted(by.items()):
      cols={
        "molecule":join([w for w in ws if 45<=float(w[0])<190]),
        "ta":join([w for w in ws if 190<=float(w[0])<315]),
        "indication":join([w for w in ws if 315<=float(w[0])<430]),
        "modality":join([w for w in ws if 430<=float(w[0])<515]),
        "phase":join([w for w in ws if float(w[0])>=515]),
      }
      text=join(ws)
      if text and not any(k in text.lower() for k in ["modalities in use","this pipeline presents","unless otherwise","amgen's product"]):
        lines.append({"y":y,**cols,"all":text})
    out.append({"page":pi+1,"lines":lines[:120]})
  print("AMGEN_ROW_GEOMETRY "+json.dumps({"finalUrl":final,"pageCount":len(doc),"pages":out},ensure_ascii=False),flush=True)

if __name__=="__main__":
  asyncio.run(main())
