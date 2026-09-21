"""Read-only Bayer proxy table-shape probe."""
import asyncio, json, re
import httpx
PROXY="https://r.jina.ai/https://www.bayer.com/en/pharma/development-pipeline"

async def main():
    try:
        async with httpx.AsyncClient(timeout=40.0,follow_redirects=True,headers={"User-Agent":"Mozilla/5.0 BayerTableProbe/1.0"}) as c:
            r=await c.get(PROXY)
        body=r.text
        lower=body.lower()
        markers=[]
        for needle in ["Phase | Area | Program","Phase|Area|Program","Pipeline Overview","Last Updated"]:
            i=lower.find(needle.lower())
            markers.append({"needle":needle,"pos":i,"slice":body[max(0,i-600):i+12000] if i>=0 else ""})
        print("BAYER_TABLE_SHAPE "+json.dumps({"status":r.status_code,"chars":len(body),"markers":markers},ensure_ascii=False),flush=True)
    except Exception as exc:
        print("BAYER_TABLE_SHAPE "+json.dumps({"error":f"{type(exc).__name__}: {exc}"},ensure_ascii=False),flush=True)

if __name__=="__main__":
    asyncio.run(main())
