"""Read-only Amgen phase-marker colour/image diagnostic."""
import json, collections, httpx, fitz

URL="https://www.amgenpipeline.com/-/media/Themes/Amgen/amgenpipeline-com/amgenpipeline-com/PDF/amgen-pipeline-chart.pdf"

def rgb_key(v):
  if v is None: return None
  return tuple(round(float(x),3) for x in v)

def is_gray(v):
  if v is None: return True
  vals=[float(x) for x in v]
  return max(vals)-min(vals) < 0.035

def main():
  with httpx.Client(timeout=45.0,follow_redirects=True,headers={"User-Agent":"Mozilla/5.0 PipelinePdfCanary/1.0"}) as c:
    r=c.get(URL); r.raise_for_status(); data=r.content
  doc=fitz.open(stream=data,filetype="pdf")
  out=[]
  for pi,p in enumerate(doc):
    colored=[]
    fills=collections.Counter()
    for d in p.get_drawings():
      rr=d.get("rect"); fill=d.get("fill"); color=d.get("color")
      if not rr: continue
      if rr.x1 < 500 or rr.x0 > 590 or rr.y1 < 175 or rr.y0 > 720: continue
      fills[(rgb_key(fill),rgb_key(color),round(rr.width,1),round(rr.height,1))]+=1
      if (fill and not is_gray(fill)) or (color and not is_gray(color)):
        colored.append({
          "rect":[round(rr.x0,2),round(rr.y0,2),round(rr.x1,2),round(rr.y1,2)],
          "fill":rgb_key(fill),"color":rgb_key(color),
          "items":[str(x)[:180] for x in d.get("items",[])[:8]]
        })
    images=[]
    for img in p.get_images(full=True):
      xref=img[0]
      try: rects=p.get_image_rects(xref)
      except Exception: rects=[]
      for rr in rects:
        if rr.x1 >= 500 and rr.x0 <= 590 and rr.y1 >=175 and rr.y0 <=720:
          images.append({"xref":xref,"rect":[round(rr.x0,2),round(rr.y0,2),round(rr.x1,2),round(rr.y1,2)],"w":img[2],"h":img[3]})
    common=[{"fill":k[0],"color":k[1],"w":k[2],"h":k[3],"count":v} for k,v in fills.most_common(30)]
    out.append({"page":pi+1,"colored":colored[:120],"images":images[:120],"common":common})
  print("AMGEN_PHASE_COLOUR "+json.dumps({"pageCount":len(doc),"pages":out},ensure_ascii=False),flush=True)

if __name__=="__main__": main()
