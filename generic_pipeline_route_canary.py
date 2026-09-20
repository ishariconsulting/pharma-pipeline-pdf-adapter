"""Read-only Roche phase-section PDF layout diagnostic."""
import json, re, httpx, fitz

URL="https://assets.roche.com/f/176343/x/cb875526bd/pharmahy26.pdf"
r=httpx.get(URL,timeout=45,follow_redirects=True,headers={"User-Agent":"Mozilla/5.0"})
r.raise_for_status()
doc=fitz.open(stream=r.content,filetype="pdf")

for pno in [1,2]:
    p=doc[pno]
    words=p.get_text("words")
    lines={}
    for w in words:
        y=(float(w[1])+float(w[3]))/2
        key=round(y/3)*3
        lines.setdefault(key,[]).append(w)

    useful=[]
    for y,ws in sorted(lines.items()):
        text=" ".join(str(w[4]) for w in sorted(ws,key=lambda q:q[0]))
        if (
            re.search(r"Phase\s+[I1-3]|Registration|RG\d|giredestrant|prasinezumab|fenebrutinib|tiragolumab",text,re.I)
            or (55 <= y <= 220)
        ):
            useful.append({
                "y":y,
                "items":[{"x":round(float(w[0]),1),"t":w[4]} for w in sorted(ws,key=lambda q:q[0])][:80]
            })
    print("ROCHE_SECTION_LAYOUT "+json.dumps({
        "page":pno+1,
        "width":p.rect.width,
        "height":p.rect.height,
        "textHead":p.get_text("text",sort=True)[:2500],
        "lines":useful[:100],
    },ensure_ascii=False),flush=True)
