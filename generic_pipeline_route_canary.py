"""Read-only Roche registration-column visual-row diagnostic."""
import asyncio, json, fitz
from generic_pdf_pipeline_extension import (
    download_pdf, _word_center_y, _visual_phase_column_rows
)

URL="https://assets.roche.com/f/176343/x/cb875526bd/pharmahy26.pdf"

async def main():
    data,final=await download_pdf(URL,35.0)
    page=fitz.open(stream=data,filetype="pdf")[3]
    words=page.get_text("words")
    body=[w for w in words if _word_center_y(w)>110 and _word_center_y(w)<page.rect.height-45]
    rows,diag=_visual_phase_column_rows(
      company="Roche",source_url=final,page_idx=3,body_words=body,
      code_x=652.1,left_bound=640.1,right_bound=942.0,split_x=809.6,
      phase="Filed / Registration",phase_label="Registration"
    )
    print("ROCHE_REG_VISUAL_ROWS "+json.dumps({
      "count":len(rows),"diag":diag,
      "rows":[{"id":r["sourceRecordId"],"code":r["developmentCode"],"asset":r["asset"],"indication":r["indication"]} for r in rows],
      "masterWrites":0
    },ensure_ascii=False),flush=True)

if __name__=="__main__":
    asyncio.run(main())
