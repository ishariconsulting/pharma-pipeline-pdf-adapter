"""Read-only artifact/link discovery for current pending pipeline sources."""

import asyncio, json, re
from html_fetch_extension import _fetch_public_html

SOURCES=[
 ("AbbVie","https://www.abbvie.com/science/pipeline.html"),
 ("Gilead Sciences","https://www.gilead.com/science/pipeline"),
 ("Amgen","https://www.amgen.com/science/clinical-trials"),
 ("Ionis Pharmaceuticals","https://ionis.com/science-and-innovation/pipeline"),
 ("Johnson & Johnson Key Events","https://www.investor.jnj.com/pipeline/2026-key-events/default.aspx"),
 ("Verve Therapeutics","https://www.vervetx.com/our-programs/our-pipeline"),
 ("Biogen","https://www.biogen.com/science-and-innovation/pipeline.html"),
 ("Johnson & Johnson Innovative Medicine","https://www.investor.jnj.com/pipeline/Innovative-Medicine-pipeline/default.aspx"),
 ("Merck KGaA","https://www.emdgroup.com/en/research/our-approach-to-research-and-development/healthcare.html"),
 ("Menarini Group","https://www.menarini.com/en-us/innovation-research/our-pipeline-and-products.html"),
]

PAT=re.compile(r"pipeline|development|portfolio|phase|clinical|pdf|xlsx|xls|download",re.I)

async def one(company,url,sem):
  async with sem:
    try:
      p=await _fetch_public_html(url,timeout_seconds=30.0)
      links=[]
      for a in p.anchors:
        text=str(a.get("text") or "")
        link=str(a.get("url") or "")
        if PAT.search(text+" "+link):
          links.append({"text":text[:180],"url":link})
      payload={"company":company,"ok":True,"status":p.httpStatus,"finalUrl":p.finalUrl,
               "visibleTextLength":p.visibleTextLength,"links":links[:60]}
    except Exception as exc:
      payload={"company":company,"ok":False,"error":f"{type(exc).__name__}: {exc}"}
    print("PIPELINE_LINK_DISCOVERY "+json.dumps(payload,ensure_ascii=False),flush=True)

async def main():
  sem=asyncio.Semaphore(4)
  await asyncio.gather(*(one(c,u,sem) for c,u in SOURCES))

if __name__=="__main__":
  asyncio.run(main())
