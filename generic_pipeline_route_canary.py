"""Read-only Amgen phase-column raw text diagnostic."""
import json, httpx, fitz
URL="https://www.amgenpipeline.com/-/media/Themes/Amgen/amgenpipeline-com/amgenpipeline-com/PDF/amgen-pipeline-chart.pdf"
def main():
  with httpx.Client(timeout=45.0,follow_redirects=True,headers={"User-Agent":"Mozilla/5.0 PipelinePdfCanary/1.0"}) as c:
    r=c.get(URL); r.raise_for_status(); data=r.content
  doc=fitz.open(stream=data,filetype="pdf")
  pages=[]
  for pi,p in enumerate(doc):
    spans=[]
    raw=p.get_text("rawdict")
    for b in raw.get("blocks",[]):
      for line in b.get("lines",[]):
        for sp in line.get("spans",[]):
          bb=sp.get("bbox") or (0,0,0,0)
          if bb[2] < 500 or bb[0] > 590 or bb[3] < 175 or bb[1] > 720: continue
          chars=[]
          for ch in sp.get("chars",[]):
            cb=ch.get("bbox") or (0,0,0,0)
            chars.append({"c":ch.get("c"),"bbox":[round(x,2) for x in cb],"origin":ch.get("origin")})
          spans.append({"font":sp.get("font"),"size":sp.get("size"),"color":sp.get("color"),"bbox":[round(x,2) for x in bb],"chars":chars})
    pages.append({"page":pi+1,"spans":spans})
  print("AMGEN_PHASE_RAWTEXT "+json.dumps({"pages":pages},ensure_ascii=False),flush=True)
if __name__=="__main__": main()
