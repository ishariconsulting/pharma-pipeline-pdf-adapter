"""Read-only official pipeline artifact diagnostics.

Inspects first-party XLSX/PDF pipeline artifacts discovered from company source
pages. No Airtable or master-data writes.
"""

from __future__ import annotations

import io
import json
import re
import zipfile
import xml.etree.ElementTree as ET

import fitz
import httpx


ARTIFACTS = [
    {
        "company": "GSK",
        "kind": "xlsx",
        "url": "https://www.gsk.com/media/2qfbw2yv/2q2026-pipeline-list.xlsx",
    },
    {
        "company": "Takeda",
        "kind": "pdf",
        "url": "https://assets-dam.takeda.com/image/upload/v1785376660/Global/Investor/Financial-Results/FY2026/Q1/qr2026_q1_Pipeline_table_en.pdf",
    },
    {
        "company": "argenx SE",
        "kind": "pdf",
        "url": "https://argenx.com/content/dam/argenx-corp/pipeline/Pipeline_August2026%201.pdf.coredownload.inline.pdf",
    },
    {
        "company": "Roche",
        "kind": "pdf",
        "url": "https://assets.roche.com/f/176343/x/cb875526bd/pharmahy26.pdf",
    },
]


def clean(v):
    return re.sub(r"\s+", " ", str(v or "")).strip()


def download(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0 Safari/537.36 PipelineArtifactCanary/1.0",
        "Accept": "application/pdf,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,*/*;q=0.8",
    }
    with httpx.Client(timeout=45.0, follow_redirects=True, headers=headers) as client:
        r = client.get(url)
    r.raise_for_status()
    return r.content, str(r.url), r.headers.get("content-type")


def xlsx_cells(data):
    ns = {"m":"http://schemas.openxmlformats.org/spreadsheetml/2006/main","r":"http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
    rel_ns = {"p":"http://schemas.openxmlformats.org/package/2006/relationships"}
    out = []
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in root.findall("m:si", ns):
                shared.append(clean(" ".join(t.text or "" for t in si.findall(".//m:t", ns))))
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        relmap = {x.attrib["Id"]:x.attrib["Target"] for x in rels.findall("p:Relationship", rel_ns)}
        for sh in wb.findall("m:sheets/m:sheet", ns):
            name = sh.attrib.get("name","")
            rid = sh.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
            target = relmap.get(rid,"")
            path = target if target.startswith("xl/") else "xl/"+target.lstrip("/")
            if path not in z.namelist():
                path = "xl/worksheets/"+target.split("/")[-1]
            root = ET.fromstring(z.read(path))
            rows = []
            for row in root.findall(".//m:sheetData/m:row", ns)[:80]:
                vals = []
                for c in row.findall("m:c", ns):
                    typ=c.attrib.get("t")
                    v=c.find("m:v", ns)
                    val=""
                    if typ=="inlineStr":
                        val=clean(" ".join(t.text or "" for t in c.findall(".//m:t",ns)))
                    elif v is not None:
                        raw=v.text or ""
                        if typ=="s" and raw.isdigit() and int(raw)<len(shared):
                            val=shared[int(raw)]
                        else:
                            val=raw
                    vals.append({"ref":c.attrib.get("r"),"value":clean(val)})
                if any(x["value"] for x in vals):
                    rows.append(vals)
            out.append({"sheet":name,"rows":rows[:50]})
    return out


def inspect_pdf(data):
    doc=fitz.open(stream=data,filetype="pdf")
    pages=[]
    for i in range(len(doc)):
        text=clean(doc[i].get_text("text",sort=True))
        low=text.lower()
        if any(k in low for k in ["phase 1","phase i","phase 2","phase ii","phase 3","phase iii","pipeline","preclinical","registration"]):
            pages.append({"page":i+1,"text":text[:5000]})
    return {"pageCount":len(doc),"signalPages":pages[:12]}


def main():
    for item in ARTIFACTS:
        company=item["company"]
        try:
            data,final_url,ctype=download(item["url"])
            if item["kind"]=="xlsx":
                detail={"sheets":xlsx_cells(data)}
            else:
                detail=inspect_pdf(data)
            result={
                "company":company,
                "kind":item["kind"],
                "sourceUrl":item["url"],
                "finalUrl":final_url,
                "contentType":ctype,
                "bytes":len(data),
                "ok":True,
                "detail":detail,
            }
        except Exception as exc:
            result={"company":company,"kind":item["kind"],"sourceUrl":item["url"],"ok":False,"error":f"{type(exc).__name__}: {exc}"}
        print("STATIC_PIPELINE_ARTIFACT",json.dumps(result,ensure_ascii=False),flush=True)


if __name__=="__main__":
    main()
