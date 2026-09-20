"""Read-only Amgen pipeline page-shape diagnostic."""

import asyncio, json, re
from generic_pipeline_extension import _fetch_raw_public_html
from generic_pipeline_interpreter_canary import PageShapeParser, interpret_pipeline_html, validate_source

URL="https://www.amgenpipeline.com/"

async def main():
    try:
        html, final_url = await _fetch_raw_public_html(URL, timeout_seconds=30.0)
        p=PageShapeParser(); p.feed(html)
        rows, diag = interpret_pipeline_html("Amgen", final_url, html)
        val=validate_source("Amgen", rows, diag)
        interesting=[]
        for i,line in enumerate(p.visible_lines):
            if re.search(r"investigational indication|therapeutic area|molecule name|phase|dazodalibep|xaluritamig|maridebart", line, re.I):
                interesting.append({"i":i,"line":line[:500]})
                if len(interesting)>=80: break
        payload={"finalUrl":final_url,"htmlChars":len(html),"visibleLineCount":len(p.visible_lines),
                 "tableCount":len(p.tables),"diag":diag,"validation":val,
                 "interesting":interesting}
    except Exception as exc:
        payload={"error":f"{type(exc).__name__}: {exc}"}
    print("AMGEN_PIPELINE_DIAGNOSTIC "+json.dumps(payload,ensure_ascii=False),flush=True)

if __name__=="__main__":
    asyncio.run(main())
