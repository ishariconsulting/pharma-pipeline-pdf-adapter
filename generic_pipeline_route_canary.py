"""Read-only Wave graphical pipeline row-summary diagnostic."""
import asyncio, json, os, re
import httpx

URL="https://wavelifesciences.com/pipeline/research-and-development/"
BASE=os.environ.get("BROWSER_FETCH_BASE_URL","").rstrip("/")
KEY=os.environ.get("BROWSER_FETCH_KEY","")

def clean(v):
    return re.sub(r"\s+"," ",str(v or "")).strip()

async def main():
    out={"configured":bool(BASE and KEY),"masterWrites":0}
    if not BASE or not KEY:
        print("WAVE_ROW_SUMMARY "+json.dumps(out),flush=True); return
    async with httpx.AsyncClient(timeout=60.0,follow_redirects=False) as c:
        r=await c.get(
            BASE+"/fetch/browser",
            params={"url":URL,"timeout_seconds":35.0,"include_layout":"true"},
            headers={"X-Browser-Key":KEY,"Accept":"application/json"},
        )
        p=r.json() if r.status_code==200 else {}
        nodes=p.get("layoutTextNodes") or []
        row_containers=[n for n in nodes if "rows flex w-full items-center" in clean(n.get("className"))]
        summaries=[]
        for row in row_containers:
            y=float(row.get("y") or 0)
            h=float(row.get("height") or 0)
            members=[n for n in nodes if n.get("inPipelineRow") and abs(float(n.get("y") or 0)-y) <= max(16,h)]
            titles=[]
            indications=[]
            population=[]
            status=[]
            for n in members:
                txt=clean(n.get("text"))
                cls=clean(n.get("className"))
                parent=clean(n.get("parentClassName"))
                if txt and (re.search(r"\bWVE[-A-Z0-9]+",txt,re.I) or "rows-title" in parent):
                    if txt not in titles: titles.append(txt)
                if txt and "sub-title" in cls and txt not in indications:
                    indications.append(txt)
                if txt and "population" in parent and txt not in population:
                    population.append(txt)
                if "rounded-block-stat" in cls:
                    status.append({
                      "class":cls,
                      "x":n.get("x"),"width":n.get("width"),
                      "height":n.get("height")
                    })
            summaries.append({
              "rowY":y,
              "titles":titles,
              "indications":indications,
              "population":population,
              "status":status
            })
        out.update({
          "status":r.status_code,
          "version":p.get("version"),
          "rowCount":len(summaries),
          "rows":summaries,
        })
    print("WAVE_ROW_SUMMARY "+json.dumps(out,ensure_ascii=False),flush=True)

if __name__=="__main__":
    asyncio.run(main())
