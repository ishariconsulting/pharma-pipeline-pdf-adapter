"""Read-only Amgen endpoint context diagnostic."""
import asyncio, json
from generic_pipeline_extension import _fetch_raw_public_html
URL="https://www.amgenpipeline.com/"
async def main():
  try:
    html,final=await _fetch_raw_public_html(URL,timeout_seconds=30.0)
    keys=["/XA-API/","pipeline-cu","moleculeLi","amgen-pipeline-chart.pdf"]
    ctx={}
    for key in keys:
      start=0; vals=[]
      while True:
        i=html.lower().find(key.lower(),start)
        if i<0 or len(vals)>=12: break
        vals.append(html[max(0,i-700):min(len(html),i+1800)])
        start=i+len(key)
      ctx[key]=vals
    print("AMGEN_ENDPOINT_CONTEXT "+json.dumps({"finalUrl":final,"context":ctx},ensure_ascii=False),flush=True)
  except Exception as exc:
    print("AMGEN_ENDPOINT_CONTEXT "+json.dumps({"error":f"{type(exc).__name__}: {exc}"}),flush=True)
if __name__=="__main__": asyncio.run(main())
