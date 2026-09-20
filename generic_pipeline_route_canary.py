"""Read-only Amgen official pipeline PDF phase-marker diagnostic."""
import json, math, httpx, fitz

URL="https://www.amgenpipeline.com/-/media/Themes/Amgen/amgenpipeline-com/amgenpipeline-com/PDF/amgen-pipeline-chart.pdf"

def compact_drawing(d):
    r=d.get("rect")
    return {
        "rect":[round(r.x0,2),round(r.y0,2),round(r.x1,2),round(r.y1,2)] if r else None,
        "fill":d.get("fill"),
        "color":d.get("color"),
        "fill_opacity":d.get("fill_opacity"),
        "stroke_opacity":d.get("stroke_opacity"),
        "width":d.get("width"),
        "items":[str(x)[:300] for x in d.get("items",[])[:12]],
    }

def main():
  try:
    with httpx.Client(timeout=45.0,follow_redirects=True,headers={"User-Agent":"Mozilla/5.0 PipelinePdfCanary/1.0"}) as c:
      r=c.get(URL); r.raise_for_status(); data=r.content
    doc=fitz.open(stream=data,filetype="pdf")
    pages=[]
    for pi,p in enumerate(doc):
      w,h=p.rect.width,p.rect.height
      candidates=[]
      for d in p.get_drawings():
        rr=d.get("rect")
        if not rr: continue
        # phase column and row body; include slightly wider area for digits/outlines
        if rr.x1 < 500 or rr.x0 > 590 or rr.y1 < 170 or rr.y0 > h-40:
          continue
        # ignore huge page/background paths
        if rr.width > 100 or rr.height > 100:
          continue
        candidates.append(compact_drawing(d))
      pages.append({"page":pi+1,"size":[w,h],"candidateCount":len(candidates),"drawings":candidates[:250]})
    print("AMGEN_PHASE_MARKERS "+json.dumps({"bytes":len(data),"pageCount":len(doc),"pages":pages},ensure_ascii=False),flush=True)
  except Exception as exc:
    print("AMGEN_PHASE_MARKERS "+json.dumps({"error":f"{type(exc).__name__}: {exc}"}),flush=True)

if __name__=="__main__": main()
