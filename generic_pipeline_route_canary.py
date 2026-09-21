"""Read-only machine-source diagnostics for Gilead, Ionis and Amgen."""
import asyncio, json, re, html as html_lib
from urllib.parse import urljoin
import httpx

HEADERS={
  "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
  "Accept":"text/html,application/json,*/*;q=0.8",
}
GILEAD_PARAMS={
  "v":"{16E72BF3-7230-403E-BB34-EAE20C26BD0F}",
  "s":"{B5AA5689-719C-4965-8E20-4B67741FF639}",
  "l":"en","p":"100","defaultSortOrder":"Pipeline Therapeutic Areas,Descending",
  "sig":"pipeline","itemid":"{EFC74AF2-1C5C-4D7C-BACD-F20CD4FF35AA}",
  "autoFireSearch":"true"
}

def text_only(raw):
  s=html_lib.unescape(raw or "")
  s=re.sub(r"<script\b[^>]*>[\s\S]*?</script>"," ",s,flags=re.I)
  s=re.sub(r"<style\b[^>]*>[\s\S]*?</style>"," ",s,flags=re.I)
  s=re.sub(r"<[^>]+>"," ",s)
  return re.sub(r"\s+"," ",s).strip()

async def gilead(c):
  r=await c.get("https://www.gilead.com/sxa/search/results/",params=GILEAD_PARAMS)
  data=r.json()
  samples=[]
  for item in (data.get("Results") or [])[:8]:
    raw=item.get("Html") or ""
    classes={}
    for cls in ["field-headbrandname","field-potentialindication","phase-name","field-therapeuticareaname","field-tagname","field-action","section-notes","section-extra-info"]:
      m=re.search(r'class="[^"]*\b'+re.escape(cls)+r'\b[^"]*"[^>]*>([\s\S]*?)</div>',raw,re.I)
      if m: classes[cls]=text_only(m.group(1))
    samples.append({
      "Id":item.get("Id"),"Path":item.get("Path"),"Url":item.get("Url"),
      "classes":classes,"text":text_only(raw)[:1200]
    })
  print("GILEAD_JSON_STRUCTURE "+json.dumps({
    "status":r.status_code,"count":data.get("Count"),"signature":data.get("Signature"),
    "sampleResults":samples
  },ensure_ascii=False),flush=True)

async def ionis(c):
  for label,url in [
    ("independent","https://ionis.com/pipeline/independent?_format=json"),
    ("partnered","https://ionis.com/pipeline/partnered?_format=json"),
  ]:
    try:
      r=await c.get(url)
      body=r.text
      try: data=r.json()
      except Exception: data=None
      sample=None
      if isinstance(data,list): sample=data[:5]
      elif isinstance(data,dict):
        sample={k:data[k] for k in list(data)[:20]}
      print("IONIS_JSON_STRUCTURE "+json.dumps({
        "label":label,"url":url,"status":r.status_code,
        "contentType":r.headers.get("content-type"),"chars":len(body),
        "jsonType":type(data).__name__ if data is not None else None,
        "sample":sample,"head":re.sub(r"\s+"," ",body[:4000])[:4000]
      },ensure_ascii=False),flush=True)
    except Exception as exc:
      print("IONIS_JSON_STRUCTURE "+json.dumps({"label":label,"error":f"{type(exc).__name__}: {exc}"},ensure_ascii=False),flush=True)

async def amgen(c):
  url="https://www.amgenpipeline.com/"
  r=await c.get(url)
  body=r.text
  attrs=re.findall(r'(?:src|href)=["\']([^"\']+)["\']',body,re.I)
  candidates=[]
  for raw in attrs:
    full=urljoin(str(r.url),html_lib.unescape(raw))
    if any(k in full.lower() for k in ["js","json","api","pipeline","data","asset"]):
      if full not in candidates: candidates.append(full)
  inline=[]
  for pat in [r'fetch\s*\([^\)]{0,700}\)',r'axios[^;]{0,700}',r'["\']([^"\']*(?:api|json|pipeline)[^"\']*)["\']']:
    for m in re.finditer(pat,body,re.I):
      val=m.group(0)
      val=re.sub(r"\s+"," ",val)
      if val not in inline: inline.append(val[:900])
      if len(inline)>=50: break
  print("AMGEN_DEPENDENCY_STRUCTURE "+json.dumps({
    "status":r.status_code,"finalUrl":str(r.url),"chars":len(body),
    "candidateUrls":candidates[:120],"inline":inline[:50],
    "text":text_only(body)[:4000]
  },ensure_ascii=False),flush=True)

async def main():
  async with httpx.AsyncClient(timeout=35.0,follow_redirects=True,headers=HEADERS) as c:
    await gilead(c)
    await ionis(c)
    await amgen(c)

if __name__=="__main__":
  asyncio.run(main())
