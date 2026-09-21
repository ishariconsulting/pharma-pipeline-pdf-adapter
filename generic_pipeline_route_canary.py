"""Read-only Amgen machine endpoint probe."""
import asyncio, json, re, httpx
BASE="https://www.amgenpipeline.com"
URL=BASE+"/pipeline/molecule/getjsondata"
HEADERS={
  "User-Agent":"Mozilla/5.0 AmgenPipelineEndpointProbe/1.0",
  "Accept":"application/json,text/plain,*/*;q=0.8",
  "Referer":BASE+"/",
  "X-Requested-With":"XMLHttpRequest",
}
def compact(v): return re.sub(r"\s+"," ",str(v or "")).strip()
async def main():
  async with httpx.AsyncClient(timeout=35.0,follow_redirects=True,headers=HEADERS) as c:
    for method in ["GET","POST"]:
      try:
        r=await (c.get(URL) if method=="GET" else c.post(URL))
        body=r.text
        try: data=r.json()
        except Exception: data=None
        if isinstance(data,dict):
          sample={k:data[k] for k in list(data)[:12]}
        elif isinstance(data,list):
          sample=data[:3]
        else:
          sample=None
        print("AMGEN_MACHINE_ENDPOINT "+json.dumps({
          "method":method,"status":r.status_code,"finalUrl":str(r.url),
          "contentType":r.headers.get("content-type"),"chars":len(body),
          "jsonType":type(data).__name__ if data is not None else None,
          "keys":list(data.keys())[:30] if isinstance(data,dict) else None,
          "sample":sample,
          "head":compact(body[:9000])[:9000]
        },ensure_ascii=False),flush=True)
      except Exception as exc:
        print("AMGEN_MACHINE_ENDPOINT "+json.dumps({"method":method,"error":f"{type(exc).__name__}: {exc}"},ensure_ascii=False),flush=True)
if __name__=="__main__":
  asyncio.run(main())
