"""Read-only source-shape diagnostics for remaining pipeline pages."""
import asyncio, json, re
from generic_pipeline_extension import _fetch_raw_public_html
from generic_pipeline_interpreter_canary import PageShapeParser

SOURCES=[
 ("Johnson & Johnson Development","https://www.investor.jnj.com/pipeline/development-pipeline/default.aspx"),
 ("Biogen","https://www.biogen.com/science-and-innovation/pipeline.html"),
 ("Merck KGaA","https://www.emdgroup.com/en/research/our-approach-to-research-and-development/healthcare.html"),
 ("Menarini Group","https://www.menarini.com/en-us/innovation-research/our-pipeline-and-products.html"),
 ("BioNTech SE","https://www.biontech.com/int/en/home/pipeline-and-products/pipeline.html"),
 ("Wave Life Sciences","https://wavelifesciences.com/pipeline/research-and-development/"),
 ("Vertex Pharmaceuticals","https://www.vrtx.com/our-science/pipeline/"),
 ("Boehringer Ingelheim","https://www.boehringer-ingelheim.com/science-innovation/human-health-innovation/pipeline"),
]

SIG=re.compile(r"phase\s*(?:1|2|3|i|ii|iii)|preclinical|registration|filed|approved|indication|therapeutic|compound|molecule|program|programme",re.I)
ATTR=re.compile(r'''(?:class|id|data-[a-z0-9_-]+)=["']([^"']{1,180})["']''',re.I)

async def one(company,url):
  try:
    html,final=await _fetch_raw_public_html(url,30.0)
    p=PageShapeParser(); p.feed(html)
    windows=[]
    for i,line in enumerate(p.visible_lines):
      if SIG.search(line):
        windows.append({
          "i":i,
          "prev":p.visible_lines[max(0,i-2):i],
          "line":line[:500],
          "next":p.visible_lines[i+1:i+5]
        })
      if len(windows)>=50: break
    attrs=[]
    for m in ATTR.finditer(html):
      val=m.group(1)
      if any(k in val.lower() for k in ["pipeline","phase","drug","product","compound","indication","program","medicine","therapy"]):
        if val not in attrs: attrs.append(val)
      if len(attrs)>=120: break
    print("SOURCE_SHAPE "+json.dumps({
      "company":company,"finalUrl":final,"htmlChars":len(html),
      "visibleLineCount":len(p.visible_lines),"tableCount":len(p.tables),
      "signalWindows":windows,"semanticAttrs":attrs
    },ensure_ascii=False),flush=True)
  except Exception as exc:
    print("SOURCE_SHAPE "+json.dumps({"company":company,"error":f"{type(exc).__name__}: {exc}"},ensure_ascii=False),flush=True)

async def main():
  for company,url in SOURCES:
    await one(company,url)

if __name__=="__main__":
  asyncio.run(main())
