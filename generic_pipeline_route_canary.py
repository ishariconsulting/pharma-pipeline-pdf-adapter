"""Read-only Takeda PDF column/row diagnostic."""
import json, httpx, fitz, re

URL="https://assets-dam.takeda.com/image/upload/v1785376660/Global/Investor/Financial-Results/FY2026/Q1/qr2026_q1_Pipeline_table_en.pdf"
r=httpx.get(URL,timeout=45,follow_redirects=True,headers={"User-Agent":"Mozilla/5.0"})
r.raise_for_status()
doc=fitz.open(stream=r.content,filetype="pdf")

for pno in [2,4,5,9,10]:
    p=doc[pno]
    words=p.get_text("words")
    header=[{"x":round(float(w[0]),1),"y":round(float(w[1]),1),"t":w[4]} for w in words if 75<=float(w[1])<=150]
    # Group body words into coarse y-lines, then show first 18 lines after header.
    lines={}
    for w in words:
        y=(float(w[1])+float(w[3]))/2
        if y<145 or y>560: continue
        key=round(y/3)*3
        lines.setdefault(key,[]).append(w)
    body=[]
    for y,ws in sorted(lines.items())[:24]:
        body.append({"y":y,"items":[{"x":round(float(w[0]),1),"t":w[4]} for w in sorted(ws,key=lambda q:q[0])]})
    print("TAKEDA_LAYOUT "+json.dumps({"page":pno+1,"header":header,"body":body},ensure_ascii=False),flush=True)
