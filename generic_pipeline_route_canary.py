"""Read-only official pipeline artifact diagnostics.

Downloads four first-party pipeline artifacts discovered from company pipeline
pages and prints compact structural evidence. No Airtable/master-data writes.
"""

import io, json, re, zipfile
import httpx, fitz
from xml.etree import ElementTree as ET

ARTIFACTS=[
 ("GSK","XLSX","https://www.gsk.com/media/2qfbw2yv/2q2026-pipeline-list.xlsx"),
 ("Takeda","PDF","https://assets-dam.takeda.com/image/upload/v1785376660/Global/Investor/Financial-Results/FY2026/Q1/qr2026_q1_Pipeline_table_en.pdf"),
 ("argenx SE","PDF","https://argenx.com/content/dam/argenx-corp/pipeline/Pipeline_August2026%201.pdf.coredownload.inline.pdf"),
 ("Roche","PDF","https://assets.roche.com/f/176343/x/cb875526bd/pharmahy26.pdf"),
]
SIG=re.compile(r"phase|indication|asset|compound|medicine|product|program|programme|development|registration|preclinical",re.I)

def clean(s): return re.sub(r"\s+"," ",str(s or "")).strip()

def download(url):
    with httpx.Client(timeout=45,follow_redirects=True,headers={"User-Agent":"Mozilla/5.0 PipelineArtifactDiagnostic/1.0","Accept":"*/*"}) as c:
        r=c.get(url); r.raise_for_status(); return r.content,str(r.url),r.headers.get("content-type")

def xlsx_rows(data):
    z=zipfile.ZipFile(io.BytesIO(data))
    ns={"m":"http://schemas.openxmlformats.org/spreadsheetml/2006/main","r":"http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
    shared=[]
    if "xl/sharedStrings.xml" in z.namelist():
        root=ET.fromstring(z.read("xl/sharedStrings.xml"))
        for si in root.findall("m:si",ns):
            shared.append(clean(" ".join(t.text or "" for t in si.findall(".//m:t",ns))))
    wb=ET.fromstring(z.read("xl/workbook.xml"))
    relroot=ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    relns={"p":"http://schemas.openxmlformats.org/package/2006/relationships"}
    rels={x.attrib["Id"]:x.attrib["Target"] for x in relroot.findall("p:Relationship",relns)}
    out=[]
    for sh in wb.findall("m:sheets/m:sheet",ns):
        name=sh.attrib.get("name","")
        rid=sh.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
        target=rels.get(rid,"")
        path=target if target.startswith("xl/") else "xl/"+target.lstrip("/")
        root=ET.fromstring(z.read(path))
        rows=[]
        for row in root.findall(".//m:sheetData/m:row",ns):
            vals=[]
            for c in row.findall("m:c",ns):
                typ=c.attrib.get("t"); v=c.find("m:v",ns)
                val="" if v is None else (v.text or "")
                if typ=="s" and val.isdigit() and int(val)<len(shared): val=shared[int(val)]
                elif typ=="inlineStr":
                    val=clean(" ".join(t.text or "" for t in c.findall(".//m:t",ns)))
                vals.append(clean(val))
            if any(vals): rows.append(vals)
        out.append((name,rows))
    return out

for company,kind,url in ARTIFACTS:
    try:
        data,final,ctype=download(url)
        if kind=="PDF":
            doc=fitz.open(stream=data,filetype="pdf")
            pages=[]
            for i,p in enumerate(doc):
                text=clean(p.get_text("text",sort=True))
                hits=[clean(x) for x in p.get_text("text",sort=True).splitlines() if SIG.search(x)]
                pages.append({"page":i+1,"chars":len(text),"signalLines":hits[:25],"head":text[:1200]})
            payload={"company":company,"kind":kind,"bytes":len(data),"finalUrl":final,"contentType":ctype,"pageCount":len(doc),"pages":pages[:12]}
        else:
            sheets=xlsx_rows(data)
            payload={"company":company,"kind":kind,"bytes":len(data),"finalUrl":final,"contentType":ctype,"sheets":[{"name":n,"rowCount":len(rows),"sampleRows":rows[:20]} for n,rows in sheets[:10]]}
    except Exception as exc:
        payload={"company":company,"kind":kind,"error":f"{type(exc).__name__}: {exc}"}
    print("PIPELINE_ARTIFACT_DIAGNOSTIC "+json.dumps(payload,ensure_ascii=False),flush=True)
