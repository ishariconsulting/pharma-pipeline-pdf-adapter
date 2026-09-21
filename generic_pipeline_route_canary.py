"""Read-only AbbVie adapter validation plus bullet-color diagnostic."""
import asyncio, json
import fitz
from abbvie_pdf_pipeline_extension import extract_abbvie_pipeline, _download_with_retry

ABBVIE="https://investors.abbvie.com/static-files/de1828c0-47ed-42cb-8573-24fe42ceb748"

async def main():
  try:
    r=await extract_abbvie_pipeline("AbbVie",ABBVIE,35.0)
    print("ABBVIE_ADAPTER_CANARY "+json.dumps({
      "readyForDiscovery":r.readyForDiscovery,"rowCount":r.rowCount,
      "sourceDate":r.sourceDate,"summary":r.summary,"issues":r.issues,
      "diagnostics":r.diagnostics,"sample":r.rows[:16],"masterWrites":0
    },ensure_ascii=False),flush=True)
  except Exception as exc:
    print("ABBVIE_ADAPTER_CANARY "+json.dumps({"readyForDiscovery":False,"error":f"{type(exc).__name__}: {exc}","masterWrites":0},ensure_ascii=False),flush=True)

  try:
    data,_=await _download_with_retry(ABBVIE,35.0)
    page=fitz.open(stream=data,filetype="pdf")[1]
    spans=[]
    for block in page.get_text("dict").get("blocks",[]):
      for line in block.get("lines",[]):
        for span in line.get("spans",[]):
          txt=str(span.get("text") or "")
          bbox=span.get("bbox",[0,0,0,0])
          if "■" in txt:
            spans.append({
              "text":txt,"bbox":[round(float(x),1) for x in bbox],
              "color":span.get("color"),"font":span.get("font"),
              "size":round(float(span.get("size") or 0),2)
            })
    print("ABBVIE_BULLET_COLOR_DIAGNOSTIC "+json.dumps({"count":len(spans),"spans":spans[:180]},ensure_ascii=False),flush=True)
  except Exception as exc:
    print("ABBVIE_BULLET_COLOR_DIAGNOSTIC "+json.dumps({"error":f"{type(exc).__name__}: {exc}"},ensure_ascii=False),flush=True)

if __name__=="__main__":
  asyncio.run(main())
