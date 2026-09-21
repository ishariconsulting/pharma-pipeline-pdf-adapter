"""Read-only Vertex investor press-release transport probe."""
import asyncio, json, re
import httpx
from generic_pipeline_interpreter_canary import PageShapeParser

URL="https://investors.vrtx.com/news-releases/news-release-details/vertex-reports-second-quarter-2026-financial-results"

async def main():
    out={"url":URL,"masterWrites":0}
    headers={"User-Agent":"Mozilla/5.0","Accept":"text/html,application/xhtml+xml,*/*","Accept-Language":"en-US,en;q=0.9"}
    try:
        async with httpx.AsyncClient(timeout=35.0,follow_redirects=True,headers=headers) as c:
            r=await c.get(URL)
        out.update({
          "status":r.status_code,
          "finalUrl":str(r.url),
          "contentType":r.headers.get("content-type"),
          "bytes":len(r.content),
        })
        if r.status_code==200:
            p=PageShapeParser(); p.feed(r.text)
            lines=p.visible_lines
            out["visibleLineCount"]=len(lines)
            low=[x.lower() for x in lines]
            markers={}
            for term in ["select r&d pipeline programs","povetacicept","vx-407","zimislecel","vx-828"]:
                markers[term]=any(term in x for x in low)
            out["markers"]=markers
            start=0
            for i,x in enumerate(low):
                if "select r&d pipeline programs" in x:
                    start=max(0,i-5); break
            out["snippet"]=lines[start:start+120]
        else:
            out["bodyHead"]=re.sub(r"\s+"," ",r.text)[:1200]
    except Exception as exc:
        out["error"]=f"{type(exc).__name__}: {exc}"
    print("VERTEX_IR_HTML_PROBE "+json.dumps(out,ensure_ascii=False),flush=True)

if __name__=="__main__":
    asyncio.run(main())
