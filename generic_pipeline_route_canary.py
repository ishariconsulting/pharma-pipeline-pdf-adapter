"""Read-only Roche phase-section geometry diagnostic."""
import json, re, httpx, fitz

URL="https://assets.roche.com/f/176343/x/cb875526bd/pharmahy26.pdf"
r=httpx.get(URL,timeout=45,follow_redirects=True,headers={"User-Agent":"Mozilla/5.0"})
r.raise_for_status()
doc=fitz.open(stream=r.content,filetype="pdf")

for pno in [2,3]:
    p=doc[pno]
    words=p.get_text("words")
    headers=[
        {
            "x0":round(float(w[0]),1),"y0":round(float(w[1]),1),
            "x1":round(float(w[2]),1),"y1":round(float(w[3]),1),
            "t":w[4],
        }
        for w in words
        if (
            float(w[1]) < 145 and
            re.search(r"phase|registration|project|program|indication",str(w[4]),re.I)
        )
    ]
    rg=[
        {"x":round(float(w[0]),1),"y":round(float(w[1]),1),"t":w[4]}
        for w in words
        if re.fullmatch(r"(?:RG\d+[A-Za-z]*|CHU)",str(w[4]),re.I)
    ]
    print("ROCHE_PHASE_GEOMETRY "+json.dumps({
        "page":pno+1,
        "width":round(p.rect.width,1),
        "height":round(p.rect.height,1),
        "headers":headers,
        "rgAnchors":rg[:80],
    },ensure_ascii=False),flush=True)
