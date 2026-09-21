"""Read-only J&J direct HTTP/query-variant source diagnostic."""
import asyncio, json, re
import httpx

BASE="https://www.investor.jnj.com/pipeline/development-pipeline/default.aspx"
URLS=[
 ("base",BASE),
 ("neuro",BASE+"?a=Neuroscience"),
 ("oncology",BASE+"?a=Oncology"),
 ("phase3",BASE+"?p=Phase+3"),
 ("multi",BASE+"?a=Neuroscience%3BOncology"),
]
HEADERS={
 "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
 "Accept":"text/html,application/xhtml+xml,*/*;q=0.8",
}

async def main():
    async with httpx.AsyncClient(timeout=45.0,follow_redirects=True,headers=HEADERS) as c:
        out=[]
        for label,url in URLS:
            try:
                r=await c.get(url)
                body=r.text
                lower=body.lower()
                out.append({
                  "label":label,
                  "status":r.status_code,
                  "finalUrl":str(r.url),
                  "chars":len(body),
                  "h2":len(re.findall(r"<h2\\b",body,re.I)),
                  "h3":len(re.findall(r"<h3\\b",body,re.I)),
                  "phaseTokens":lower.count("phase 1")+lower.count("phase 2")+lower.count("phase 3")+lower.count("registration"),
                  "has97":"97 of 97" in lower,
                  "hasDarzalex":"darzalex" in lower,
                  "hasPumitamig":"pumitamig" in lower,
                  "hasCaplyta":"caplyta" in lower,
                  "hasPipeline":"development pipeline" in lower,
                  "bodyHead":re.sub(r"\\s+"," ",body[:2000])[:1200],
                })
            except Exception as exc:
                out.append({"label":label,"error":f"{type(exc).__name__}: {exc}"})
        print("JNJ_DIRECT_VARIANTS "+json.dumps({"results":out,"masterWrites":0},ensure_ascii=False),flush=True)

if __name__=="__main__":
    asyncio.run(main())
