"""Read-only canary: new machine adapters plus Amgen PDF geometry."""
import asyncio, json, re
import fitz
from sitecore_sxa_pipeline_extension import extract_sitecore_sxa
from ionis_json_pipeline_extension import extract_ionis_pipeline
from generic_pdf_pipeline_extension import download_pdf

GILEAD_URL="https://www.gilead.com/sxa/search/results/?v=%7B16E72BF3-7230-403E-BB34-EAE20C26BD0F%7D&s=%7BB5AA5689-719C-4965-8E20-4B67741FF639%7D&l=en&p=100&defaultSortOrder=Pipeline%20Therapeutic%20Areas%2CDescending&sig=pipeline&itemid=%7BEFC74AF2-1C5C-4D7C-BACD-F20CD4FF35AA%7D&autoFireSearch=true"
IONIS_PAGE="https://ionis.com/science-and-innovation/pipeline"
AMGEN_PDF="https://www.amgenpipeline.com/-/media/Themes/Amgen/amgenpipeline-com/amgenpipeline-com/PDF/amgen-pipeline-chart.pdf"

def clean(s): return re.sub(r"\s+"," ",str(s or "")).strip()

async def adapter_canaries():
    for label,fn,args in [
      ("GILEAD_SITECORE_ADAPTER",extract_sitecore_sxa,("Gilead Sciences",GILEAD_URL,35.0)),
      ("IONIS_JSON_ADAPTER",extract_ionis_pipeline,("Ionis Pharmaceuticals",IONIS_PAGE,35.0)),
    ]:
      try:
        r=await fn(*args)
        print(label+" "+json.dumps({
          "readyForDiscovery":r.readyForDiscovery,"rowCount":r.rowCount,
          "issues":[x.get("issue") for x in r.issues],
          "summary":r.summary,"diagnostics":r.diagnostics,
          "sample":r.rows[:8],"masterWrites":0
        },ensure_ascii=False),flush=True)
      except Exception as exc:
        print(label+" "+json.dumps({"readyForDiscovery":False,"error":f"{type(exc).__name__}: {exc}","masterWrites":0},ensure_ascii=False),flush=True)

async def amgen_geometry():
    data,final=await download_pdf(AMGEN_PDF,35.0)
    doc=fitz.open(stream=data,filetype="pdf")
    pages=[]
    terms=("molecule","therapeutic","investigational","indication","modality","phase","oncology","inflammation","cardiovascular")
    for pi in range(len(doc)):
      p=doc[pi]; words=p.get_text("words")
      byline={}
      for w in words:
        y=round(((float(w[1])+float(w[3]))/2)/3)*3
        byline.setdefault(y,[]).append(w)
      selected=[]
      for y,ws in sorted(byline.items()):
        text=clean(" ".join(str(w[4]) for w in sorted(ws,key=lambda q:q[0])))
        if any(t in text.lower() for t in terms):
          selected.append({"y":y,"words":[{"x":round(float(w[0]),1),"t":clean(w[4])} for w in sorted(ws,key=lambda q:q[0])][:60],"text":text[:1000]})
      pages.append({"page":pi+1,"width":round(p.rect.width,1),"height":round(p.rect.height,1),"selected":selected[:35]})
    print("AMGEN_PDF_GEOMETRY "+json.dumps({"finalUrl":final,"bytes":len(data),"pageCount":len(doc),"pages":pages},ensure_ascii=False),flush=True)

async def main():
    await adapter_canaries()
    await amgen_geometry()

if __name__=="__main__":
    asyncio.run(main())
