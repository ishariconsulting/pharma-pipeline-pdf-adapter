"""Read-only geometry diagnostic for Takeda official pipeline PDF."""
import json, httpx, fitz

URL="https://assets-dam.takeda.com/image/upload/v1785376660/Global/Investor/Financial-Results/FY2026/Q1/qr2026_q1_Pipeline_table_en.pdf"
r=httpx.get(URL,timeout=45,follow_redirects=True,headers={"User-Agent":"Mozilla/5.0"})
r.raise_for_status()
doc=fitz.open(stream=r.content,filetype="pdf")
for pageno in [3,4,5,6,7,8]:
    if pageno >= len(doc): continue
    p=doc[pageno]
    words=p.get_text("words")
    rows={}
    for w in words:
        x0,y0,x1,y1,txt,*_=w
        key=round(y0/3)*3
        rows.setdefault(key,[]).append((x0,txt))
    samples=[]
    for y,items in sorted(rows.items()):
        text=" ".join(t for _,t in sorted(items))
        if any(k.lower() in text.lower() for k in ["development code","indications","stage","tak-","global","p-ii","p-iii","filed","approved"]):
            samples.append({"y":y,"items":[{"x":round(x,1),"t":t} for x,t in sorted(items)][:80]})
    print("TAKEDA_GEOMETRY "+json.dumps({"page":pageno+1,"width":p.rect.width,"height":p.rect.height,"samples":samples[:40]},ensure_ascii=False),flush=True)
