"""Read-only rendered-line diagnostics for current pipeline pages.

Captures numbered browser-visible lines for BioNTech, J&J and Wave so reusable
semantic card/flow parsers can be built from source structure rather than
Portfolio aliases or company-specific row values.
"""
import asyncio, json, os
import httpx

SOURCES=[
 ("BioNTech SE","https://www.biontech.com/int/en/home/pipeline-and-products/pipeline.html"),
 ("Johnson & Johnson","https://www.investor.jnj.com/pipeline/development-pipeline/default.aspx"),
 ("Wave Life Sciences","https://wavelifesciences.com/pipeline/research-and-development/"),
]

async def main():
    base=os.getenv("BROWSER_FETCH_BASE_URL","").strip().rstrip("/")
    key=os.getenv("BROWSER_FETCH_KEY","").strip()
    if not base or not key:
        print("RENDERED_LINE_DIAGNOSTIC "+json.dumps({"configured":False}),flush=True)
        return
    async with httpx.AsyncClient(timeout=55.0,follow_redirects=True) as c:
      for company,url in SOURCES:
        try:
          r=await c.get(base+"/fetch/browser",params={"url":url,"timeout_seconds":30},headers={"X-Browser-Key":key})
          data=r.json()
          lines=data.get("visibleLines") or []
          numbered=[{"i":i,"text":str(v)} for i,v in enumerate(lines)]
          print("RENDERED_LINE_DIAGNOSTIC "+json.dumps({
            "company":company,"status":r.status_code,"browserVersion":data.get("version"),
            "httpStatus":data.get("httpStatus"),"title":data.get("title"),
            "visibleTextLength":data.get("visibleTextLength"),
            "lineCount":len(lines),"lines":numbered
          },ensure_ascii=False),flush=True)
        except Exception as exc:
          print("RENDERED_LINE_DIAGNOSTIC "+json.dumps({
            "company":company,"error":f"{type(exc).__name__}: {exc}"
          },ensure_ascii=False),flush=True)

if __name__=="__main__":
    asyncio.run(main())
