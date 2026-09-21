"""Read-only AbbVie PDF bullet/span color diagnostic."""
import asyncio, json
import fitz
from abbvie_pdf_pipeline_extension import _download_with_retry

ABBVIE="https://investors.abbvie.com/static-files/de1828c0-47ed-42cb-8573-24fe42ceb748"

async def main():
  try:
    data,final=await _download_with_retry(ABBVIE,35.0)
    doc=fitz.open(stream=data,filetype="pdf")
    page=doc[1]
    info=page.get_text("dict")
    spans=[]
    for block in info.get("blocks",[]):
      for line in block.get("lines",[]):
        for span in line.get("spans",[]):
          text=str(span.get("text") or "")
          if "■" in text or (570 <= float(span.get("bbox",[0,0,0,0])[0]) <= 590 and 360 <= float(span.get("bbox",[0,0,0,0])[1]) <= 475):
            spans.append({
              "text":text,
              "bbox":[round(float(x),1) for x in span.get("bbox",[0,0,0,0])],
              "color":span.get("color"),
              "font":span.get("font"),
              "size":round(float(span.get("size") or 0),2),
              "flags":span.get("flags"),
            })
    print("ABBVIE_SPAN_DIAGNOSTIC "+json.dumps({"finalUrl":final,"spanCount":len(spans),"spans":spans[:240]},ensure_ascii=False),flush=True)
  except Exception as exc:
    print("ABBVIE_SPAN_DIAGNOSTIC "+json.dumps({"error":f"{type(exc).__name__}: {exc}"},ensure_ascii=False),flush=True)

if __name__=="__main__":
  asyncio.run(main())
