"""Read-only Roche current pipeline PDF table detector."""
import json, httpx, fitz

URL="https://assets.roche.com/f/176343/x/cb875526bd/pharmahy26.pdf"
r=httpx.get(URL,timeout=45,follow_redirects=True,headers={"User-Agent":"Mozilla/5.0"})
r.raise_for_status()
doc=fitz.open(stream=r.content,filetype="pdf")

for pno in [1,2,3]:
    p=doc[pno]
    payload={"page":pno+1,"textHead":p.get_text("text",sort=True)[:1800],"tables":[]}
    try:
        finder=p.find_tables()
        for ti,t in enumerate(finder.tables[:8]):
            extracted=t.extract()
            payload["tables"].append({
                "table":ti,
                "bbox":[round(float(x),1) for x in t.bbox],
                "rows":extracted[:12],
                "rowCount":len(extracted),
                "colCount":max((len(x) for x in extracted),default=0),
            })
    except Exception as exc:
        payload["tableError"]=f"{type(exc).__name__}: {exc}"
    print("ROCHE_FIND_TABLES "+json.dumps(payload,ensure_ascii=False),flush=True)
