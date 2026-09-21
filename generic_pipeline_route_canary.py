"""Read-only Roche final semantic PDF canary."""
import asyncio, json
from collections import Counter
from generic_pdf_pipeline_extension import extract_generic_pdf

URL="https://assets.roche.com/f/176343/x/cb875526bd/pharmahy26.pdf"

async def main():
    try:
        r=await extract_generic_pdf("Roche",URL,35.0)
        print("ROCHE_FINAL_PDF_CANARY "+json.dumps({
          "readyForDiscovery":r.readyForDiscovery,
          "rowCount":r.rowCount,
          "issues":[x.get("issue") for x in r.issues],
          "selectedMethod":r.summary.get("selectedMethod"),
          "phaseCounts":dict(Counter(x.get("phase","") for x in r.rows)),
          "parserMethods":dict(Counter(x.get("parserMethod","") for x in r.rows)),
          "blankDevelopmentCodes":sum(1 for x in r.rows if not x.get("developmentCode")),
          "declaredProgrammes":r.diagnostics.get("declaredProgrammes"),
          "rowFailures":r.diagnostics.get("rowFailures"),
          "coverageWarnings":r.diagnostics.get("coverageWarnings"),
          "boundaryWarnings":r.diagnostics.get("boundaryWarnings"),
          "pageDiagnostics":r.diagnostics.get("pages"),
          "page4Rows":[
            {"code":x.get("developmentCode"),"asset":x.get("asset"),"indication":x.get("indication"),"phase":x.get("phase")}
            for x in r.rows if x.get("sourcePage")==4
          ],
          "masterWrites":0,
        },ensure_ascii=False),flush=True)
    except Exception as exc:
        print("ROCHE_FINAL_PDF_CANARY "+json.dumps({
          "readyForDiscovery":False,
          "error":f"{type(exc).__name__}: {exc}",
          "masterWrites":0
        },ensure_ascii=False),flush=True)

if __name__=="__main__":
    asyncio.run(main())
