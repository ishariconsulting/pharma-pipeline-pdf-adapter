"""Read-only Bayer WAF transport probe via external text retrieval fallback."""
import asyncio, json, re
import httpx

OFFICIAL="https://www.bayer.com/en/pharma/development-pipeline"
PROXY="https://r.jina.ai/https://www.bayer.com/en/pharma/development-pipeline"

async def main():
    headers={"User-Agent":"Mozilla/5.0 BayerPipelineTransportProbe/1.0","Accept":"text/plain,text/markdown,*/*;q=0.8"}
    try:
        async with httpx.AsyncClient(timeout=40.0,follow_redirects=True,headers=headers) as client:
            r=await client.get(PROXY)
        body=r.text
        markers={
          "hasOfficialUrl":OFFICIAL.lower() in body.lower(),
          "hasDevelopmentPipeline":"development pipeline" in body.lower(),
          "hasDarolutamide":"darolutamide" in body.lower(),
          "hasFinerenone":"finerenone" in body.lower(),
          "hasLastUpdated":"last updated" in body.lower(),
          "hasTableHeader":bool(re.search(r"phase\s*\|\s*area\s*\|\s*program",body,re.I)),
        }
        print("BAYER_PROXY_PROBE "+json.dumps({
          "status":r.status_code,"finalUrl":str(r.url),
          "contentType":r.headers.get("content-type"),
          "chars":len(body),"markers":markers,
          "head":re.sub(r"\s+"," ",body[:5000])[:5000],
          "masterWrites":0
        },ensure_ascii=False),flush=True)
    except Exception as exc:
        print("BAYER_PROXY_PROBE "+json.dumps({"error":f"{type(exc).__name__}: {exc}","masterWrites":0},ensure_ascii=False),flush=True)

if __name__=="__main__":
    asyncio.run(main())
