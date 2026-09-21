"""Read-only AbbVie PDF geometry diagnostic."""
import asyncio, json, re, collections
import fitz
from abbvie_pdf_pipeline_extension import _download_with_retry, clean, word_y

ABBVIE="https://investors.abbvie.com/static-files/de1828c0-47ed-42cb-8573-24fe42ceb748"

async def main():
  try:
    data,final=await _download_with_retry(ABBVIE,35.0)
    doc=fitz.open(stream=data,filetype="pdf")
    page=doc[1]
    words=page.get_text("words")
    lines={}
    for w in words:
      y=round(word_y(w),1)
      # cluster on nearest ~3 points
      key=round(y/3)*3
      lines.setdefault(key,[]).append(w)
    line_dump=[]
    for y,ws in sorted(lines.items()):
      ws=sorted(ws,key=lambda q:float(q[0]))
      txt=clean(" ".join(str(w[4]) for w in ws))
      if txt:
        line_dump.append({
          "y":y,
          "x0":round(min(float(w[0]) for w in ws),1),
          "x1":round(max(float(w[2]) for w in ws),1),
          "text":txt[:800],
          "words":[{"x0":round(float(w[0]),1),"x1":round(float(w[2]),1),"t":clean(w[4])} for w in ws[:50]]
        })
    drawings=page.get_drawings()
    dsum=[]
    color_counts=collections.Counter()
    size_counts=collections.Counter()
    for d in drawings:
      rect=d.get("rect"); fill=d.get("fill")
      if not rect: continue
      width=round(float(rect.x1-rect.x0),1); height=round(float(rect.y1-rect.y0),1)
      if fill is not None:
        color=tuple(round(float(c),3) for c in fill)
        color_counts[str(color)]+=1
      else: color=None
      size_counts[str((width,height))]+=1
      if width<=30 and height<=30:
        dsum.append({"x0":round(float(rect.x0),1),"y0":round(float(rect.y0),1),"x1":round(float(rect.x1),1),"y1":round(float(rect.y1),1),"w":width,"h":height,"fill":color,"type":d.get("type")})
    print("ABBVIE_GEOMETRY_DIAGNOSTIC "+json.dumps({
      "finalUrl":final,"bytes":len(data),"pageCount":len(doc),
      "pageWidth":round(page.rect.width,1),"pageHeight":round(page.rect.height,1),
      "lines":line_dump[:140],
      "drawingCount":len(drawings),
      "smallDrawings":dsum[:200],
      "topFillColors":color_counts.most_common(20),
      "topSizes":size_counts.most_common(30),
    },ensure_ascii=False),flush=True)
  except Exception as exc:
    print("ABBVIE_GEOMETRY_DIAGNOSTIC "+json.dumps({"error":f"{type(exc).__name__}: {exc}"},ensure_ascii=False),flush=True)

if __name__=="__main__":
  asyncio.run(main())
