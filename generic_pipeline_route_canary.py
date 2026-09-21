"""Read-only Roche semantic phase-column PDF canary."""
import asyncio, json
from generic_pdf_pipeline_extension import download_pdf, parse_phase_column_pdf

URL="https://assets.roche.com/f/176343/x/cb875526bd/pharmahy26.pdf"

async def main():
    try:
        data, final = await download_pdf(URL,35.0)
        rows, diagnostics = parse_phase_column_pdf("Roche",final,data)
        issues=[]
        if len(rows)<4:
            issues.append(f"too few structured rows: {len(rows)} < 4")
        if int(diagnostics.get("rowFailures",0))>0:
            issues.append(f"{diagnostics['rowFailures']} source rows could not be resolved structurally")
        print("ROCHE_PHASE_COLUMN_CANARY "+json.dumps({
          "readyForDiscovery":not issues,
          "rowCount":len(rows),
          "selectedMethod":"SEMANTIC_PDF_PHASE_COLUMN",
          "issues":issues,
          "diagnostics":diagnostics,
          "sampleRows":rows[:30],
          "masterWrites":0
        },ensure_ascii=False),flush=True)
    except Exception as exc:
        print("ROCHE_PHASE_COLUMN_CANARY "+json.dumps({
          "readyForDiscovery":False,
          "error":f"{type(exc).__name__}: {exc}",
          "masterWrites":0
        },ensure_ascii=False),flush=True)

if __name__=="__main__":
    asyncio.run(main())
