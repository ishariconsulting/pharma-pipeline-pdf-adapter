"""Read-only diagnostics for generic graphical PDF parsing and Takeda glyph recovery."""
import json, httpx, fitz

ARGENX="https://argenx.com/content/dam/argenx-corp/pipeline/Pipeline_August2026%201.pdf.coredownload.inline.pdf"
TAKEDA="https://assets-dam.takeda.com/image/upload/v1785376660/Global/Investor/Financial-Results/FY2026/Q1/qr2026_q1_Pipeline_table_en.pdf"

def get(url):
    r=httpx.get(url,timeout=45,follow_redirects=True,headers={"User-Agent":"Mozilla/5.0"})
    r.raise_for_status()
    return r.content

# argenx vector geometry
doc=fitz.open(stream=get(ARGENX),filetype="pdf")
p=doc[0]
words=p.get_text("words")
headers=[{"x0":round(w[0],1),"y0":round(w[1],1),"x1":round(w[2],1),"y1":round(w[3],1),"t":w[4]} for w in words if w[4] in {"Program","Indication","Preclinical","Phase","Proof","Registrational","Commercial"} or "Phase" in w[4]]
draws=[]
for d in p.get_drawings():
    rect=d.get("rect")
    if not rect: continue
    # candidate horizontal stage bars only
    if rect.width >= 40 and rect.height <= 30 and 150 <= rect.y0 <= 900:
        draws.append({
            "rect":[round(rect.x0,1),round(rect.y0,1),round(rect.x1,1),round(rect.y1,1)],
            "fill":d.get("fill"),
            "color":d.get("color"),
            "width":d.get("width"),
            "items":len(d.get("items") or []),
        })
print("ARGENX_VECTOR_DIAGNOSTIC "+json.dumps({"page":[p.rect.width,p.rect.height],"headers":headers,"bars":draws[:120]},ensure_ascii=False),flush=True)

# Takeda raw character recovery around the one unresolved Phase-I row
doc=fitz.open(stream=get(TAKEDA),filetype="pdf")
p=doc[4]
raw=p.get_text("rawdict")
chars=[]
for block in raw.get("blocks",[]):
    for line in block.get("lines",[]):
        for span in line.get("spans",[]):
            for ch in span.get("chars",[]):
                bbox=ch.get("bbox") or [0,0,0,0]
                y=(bbox[1]+bbox[3])/2
                if 338 <= y <= 360 and bbox[0] < 120:
                    c=ch.get("c","")
                    chars.append({"x":round(bbox[0],1),"y":round(y,1),"c":c,"ord":ord(c) if c else None,"font":span.get("font")})
print("TAKEDA_RAW_GLYPHS "+json.dumps(chars,ensure_ascii=False),flush=True)
