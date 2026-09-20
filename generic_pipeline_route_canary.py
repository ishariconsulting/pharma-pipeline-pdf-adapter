"""Compact read-only canary for generic PDF parser families."""
import asyncio, json
from generic_pdf_pipeline_extension import extract_generic_pdf

SOURCES=[
 ("Takeda","https://assets-dam.takeda.com/image/upload/v1785376660/Global/Investor/Financial-Results/FY2026/Q1/qr2026_q1_Pipeline_table_en.pdf"),
 ("argenx SE","https://argenx.com/content/dam/argenx-corp/pipeline/Pipeline_August2026%201.pdf.coredownload.inline.pdf"),
 ("Roche","https://assets.roche.com/f/176343/x/cb875526bd/pharmahy26.pdf"),
]

async def one(company,url):
    try:
        r=await extract_generic_pdf(company,url,35.0)
        rows=r.rows
        focus=[
            {
                "sourceRecordId":x.get("sourceRecordId"),
                "asset":x.get("asset"),
                "developmentCode":x.get("developmentCode"),
                "indication":x.get("indication"),
                "phase":x.get("phase"),
                "marketRegion":x.get("marketRegion"),
            }
            for x in rows
            if (
                (company=="Takeda" and x.get("sourcePage") in {3,5} and 480 <= int(x.get("sourceRecordId","y0").split("y")[-1] or 0) <= 540)
                or (company=="argenx SE" and len(rows) <= 30)
            )
        ]
        payload={
          "company":company,
          "readyForDiscovery":r.readyForDiscovery,
          "rowCount":r.rowCount,
          "selectedMethod":r.summary.get("selectedMethod"),
          "issues":r.validation.get("issues"),
          "rowFailures":r.diagnostics.get("rowFailures"),
          "failureSamples":r.diagnostics.get("failureSamples"),
          "exactDuplicatesRemoved":r.diagnostics.get("exactDuplicatesRemoved"),
          "focusRows":focus[:30],
          "masterWrites":0,
        }
    except Exception as exc:
        payload={"company":company,"readyForDiscovery":False,"error":f"{type(exc).__name__}: {exc}","masterWrites":0}
    print("GENERIC_PDF_COMPACT_CANARY "+json.dumps(payload,ensure_ascii=False),flush=True)

async def main():
    for company,url in SOURCES:
        await one(company,url)

if __name__=="__main__":
    asyncio.run(main())
