"""Read-only canary for AbbVie PDF adapter and Bayer blocked official sources."""
import asyncio, json
from abbvie_pdf_pipeline_extension import extract_abbvie_pipeline
from generic_pdf_pipeline_extension import extract_generic_pdf
from generic_pipeline_extension import _extract_generic_pipeline

ABBVIE="https://investors.abbvie.com/static-files/de1828c0-47ed-42cb-8573-24fe42ceb748"

async def main():
  try:
    r=await extract_abbvie_pipeline("AbbVie",ABBVIE,35.0)
    print("ABBVIE_ADAPTER_CANARY "+json.dumps({
      "readyForDiscovery":r.readyForDiscovery,"rowCount":r.rowCount,
      "sourceDate":r.sourceDate,"summary":r.summary,"issues":r.issues,
      "diagnostics":r.diagnostics,"sample":r.rows[:12],"masterWrites":0
    },ensure_ascii=False),flush=True)
  except Exception as exc:
    print("ABBVIE_ADAPTER_CANARY "+json.dumps({"readyForDiscovery":False,"error":f"{type(exc).__name__}: {exc}","masterWrites":0},ensure_ascii=False),flush=True)

  for company,url,kind in [
    ("Bayer","https://www.bayer.com/sites/default/files/ph-rd-pipeline-2026-04-29-final.pdf","PDF"),
    ("Bayer","https://www.bayer.com/en/pharma/development-pipeline","HTML"),
  ]:
    try:
      if kind=="PDF":
        r=await extract_generic_pdf(company,url,35.0)
      else:
        r=await _extract_generic_pipeline(company=company,source_url=url,timeout_seconds=35.0)
      print("BAYER_TRANSPORT_CANARY "+json.dumps({
        "kind":kind,"readyForDiscovery":r.readyForDiscovery,"rowCount":r.rowCount,
        "issues":r.issues,"summary":r.summary,"masterWrites":0
      },ensure_ascii=False),flush=True)
    except Exception as exc:
      print("BAYER_TRANSPORT_CANARY "+json.dumps({"kind":kind,"readyForDiscovery":False,"error":f"{type(exc).__name__}: {exc}","masterWrites":0},ensure_ascii=False),flush=True)

if __name__=="__main__":
  asyncio.run(main())
