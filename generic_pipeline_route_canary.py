"""Read-only Amgen official pipeline PDF geometry diagnostic."""
import json, re, httpx, fitz

URL="https://www.amgenpipeline.com/-/media/Themes/Amgen/amgenpipeline-com/amgenpipeline-com/PDF/amgen-pipeline-chart.pdf"

def main():
  try:
    with httpx.Client(timeout=45.0,follow_redirects=True,headers={"User-Agent":"Mozilla/5.0 PipelinePdfCanary/1.0"}) as c:
      r=c.get(URL); r.raise_for_status(); data=r.content
    doc=fitz.open(stream=data,filetype="pdf")
    p=doc[0]; w,h=p.rect.width,p.rect.height
    words=p.get_text("words",sort=True)
    phase_words=[]
    header_words=[]
    for wd in words:
      x0,y0,x1,y1,text,*_=wd
      t=str(text)
      if x0 > 0.82*w and re.fullmatch(r"[1-4]",t.strip()):
        phase_words.append({"text":t,"x0":round(x0,2),"y0":round(y0,2),"x1":round(x1,2),"y1":round(y1,2)})
      if y0 < 0.25*h and re.search(r"MOLECULE|THERAPEUTIC|INDICATION|MODALITY|PHASE",t,re.I):
        header_words.append({"text":t,"x0":round(x0,2),"y0":round(y0,2),"x1":round(x1,2),"y1":round(y1,2)})
    blocks=[]
    for b in p.get_text("blocks",sort=True):
      x0,y0,x1,y1,text,*_=b
      if 0.15*h < y0 < 0.75*h:
        blocks.append({"x0":round(x0,2),"y0":round(y0,2),"x1":round(x1,2),"y1":round(y1,2),"text":" ".join(str(text).split())[:500]})
    payload={"bytes":len(data),"pageCount":len(doc),"pageSize":[w,h],"phaseWords":phase_words,"headerWords":header_words,"blocks":blocks[:80]}
  except Exception as exc:
    payload={"error":f"{type(exc).__name__}: {exc}"}
  print("AMGEN_PDF_GEOMETRY "+json.dumps(payload,ensure_ascii=False),flush=True)

if __name__=="__main__": main()
