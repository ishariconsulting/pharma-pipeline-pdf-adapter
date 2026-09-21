"""Read-only canary for AbbVie July-2026 and Bayer official pipeline documents."""
import asyncio, json
from generic_pdf_pipeline_extension import extract_generic_pdf
from generic_pipeline_extension import _extract_generic_pipeline

SOURCES=[
  ("AbbVie","https://investors.abbvie.com/static-files/de1828c0-47ed-42cb-8573-24fe42ceb748","PDF"),
  ("Bayer","https://www.bayer.com/sites/default/files/ph-rd-pipeline-2026-04-29-final.pdf","PDF"),
  ("Bayer","https://www.bayer.com/en/pharma/development-pipeline","HTML"),
]

async def main():
  for company,url,kind in SOURCES:
    try:
      if kind=="PDF":
        r=await extract_generic_pdf(company,url,35.0)
      else:
        r=await _extract_generic_pipeline(company=company,source_url=url,timeout_seconds=35.0)
      print("BLOCKED_SOURCE_CANARY "+json.dumps({
        "company":company,"kind":kind,"url":url,
        "readyForDiscovery":r.readyForDiscovery,"rowCount":r.rowCount,
        "summary":r.summary,"issues":r.issues,"diagnostics":r.diagnostics,
        "sample":r.rows[:8],"masterWrites":0
      },ensure_ascii=False),flush=True)
    except Exception as exc:
      print("BLOCKED_SOURCE_CANARY "+json.dumps({
        "company":company,"kind":kind,"url":url,
        "readyForDiscovery":False,"error":f"{type(exc).__name__}: {exc}","masterWrites":0
      },ensure_ascii=False),flush=True)

if __name__=="__main__":
  asyncio.run(main())
