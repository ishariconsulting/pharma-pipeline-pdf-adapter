"""Read-only Roche page-4 parsed-row diagnostic."""
import asyncio, json
from generic_pdf_pipeline_extension import download_pdf, parse_phase_column_pdf

URL="https://assets.roche.com/f/176343/x/cb875526bd/pharmahy26.pdf"

async def main():
    data,final=await download_pdf(URL,35.0)
    rows,diag=parse_phase_column_pdf("Roche",final,data)
    p4=[{
      "id":r["sourceRecordId"],"code":r["developmentCode"],
      "asset":r["asset"],"indication":r["indication"],"phase":r["phase"]
    } for r in rows if r.get("sourcePage")==4]
    print("ROCHE_P4_PARSED_ROWS "+json.dumps({
      "count":len(p4),
      "declaredProgrammes":diag.get("declaredProgrammes"),
      "rows":p4,
      "masterWrites":0
    },ensure_ascii=False),flush=True)

if __name__=="__main__":
    asyncio.run(main())
