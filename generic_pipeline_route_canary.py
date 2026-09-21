"""Read-only Boehringer first-party annual-report pipeline source probe."""
import asyncio, json
import httpx

URLS=[
 "https://annualreport.boehringer-ingelheim.com/2024/download/BOE_AR24_Highlights_2024_EN_safe.pdf",
 "https://annualreport.boehringer-ingelheim.com/2024/download/BOE_AR24_Highlights_2024_EN.pdf",
 "https://annualreport.boehringer-ingelheim.com/2024/download/BOE_AR24_Highlights_EN_safe.pdf",
 "https://annualreport.boehringer-ingelheim.com/2024/download/BOE_AR24_Highlights_EN.pdf",
 "https://annualreport.boehringer-ingelheim.com/2024/downloads/BOE_AR24_Highlights_2024_EN_safe.pdf",
 "https://annualreport.boehringer-ingelheim.com/2024/downloads/en/BOE_AR24_Highlights_2024_EN_safe.pdf",
 "https://annualreport.boehringer-ingelheim.com/2024/",
 "https://www.boehringer-ingelheim.com/about-us/annual-report",
]

async def main():
    out=[]
    headers={"User-Agent":"Mozilla/5.0","Accept":"application/pdf,text/html,*/*"}
    async with httpx.AsyncClient(timeout=25.0,follow_redirects=True,headers=headers) as c:
        for url in URLS:
            item={"url":url}
            try:
                r=await c.get(url)
                item.update({
                  "status":r.status_code,
                  "finalUrl":str(r.url),
                  "contentType":r.headers.get("content-type"),
                  "bytes":len(r.content),
                  "head":r.text[:300].replace("\n"," ") if "text" in (r.headers.get("content-type") or "") else None,
                })
            except Exception as exc:
                item["error"]=f"{type(exc).__name__}: {exc}"
            out.append(item)
    print("BOEHRINGER_ANNUAL_REPORT_PROBE "+json.dumps({"results":out,"masterWrites":0},ensure_ascii=False),flush=True)

if __name__=="__main__":
    asyncio.run(main())
