"""Read-only Takeda row-boundary diagnostic."""
import json, httpx, fitz
URL="https://assets-dam.takeda.com/image/upload/v1785376660/Global/Investor/Financial-Results/FY2026/Q1/qr2026_q1_Pipeline_table_en.pdf"
r=httpx.get(URL,timeout=45,follow_redirects=True,headers={"User-Agent":"Mozilla/5.0"})
r.raise_for_status()
doc=fitz.open(stream=r.content,filetype="pdf")
for pno,lo,hi in [(2,370,520),(3,55,220),(4,130,380),(7,130,470)]:
    p=doc[pno]
    words=p.get_text("words")
    lines={}
    for w in words:
        y=(float(w[1])+float(w[3]))/2
        if y<lo or y>hi: continue
        key=round(y/3)*3
        lines.setdefault(key,[]).append(w)
    body=[]
    for y,ws in sorted(lines.items()):
        body.append({"y":y,"items":[{"x":round(float(w[0]),1),"t":w[4]} for w in sorted(ws,key=lambda q:q[0])]})
    print("TAKEDA_BOUNDARY "+json.dumps({"page":pno+1,"body":body},ensure_ascii=False),flush=True)
