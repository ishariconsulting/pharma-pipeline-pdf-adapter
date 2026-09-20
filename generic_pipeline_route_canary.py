"""Read-only Amgen table-separator diagnostic."""
import json, collections, httpx, fitz

URL="https://www.amgenpipeline.com/-/media/Themes/Amgen/amgenpipeline-com/amgenpipeline-com/PDF/amgen-pipeline-chart.pdf"

def main():
    with httpx.Client(timeout=45.0,follow_redirects=True,headers={"User-Agent":"Mozilla/5.0 PipelinePdfCanary/1.0"}) as c:
        r=c.get(URL); r.raise_for_status(); data=r.content
    doc=fitz.open(stream=data,filetype="pdf")
    out=[]
    for pi,p in enumerate(doc):
        xs=collections.Counter()
        samples=[]
        for d in p.get_drawings():
            rr=d.get("rect")
            if not rr: continue
            # Near-vertical table borders / thin rectangles spanning data area.
            if rr.y1 < 155 or rr.y0 > 650: continue
            if rr.width <= 1.2 and rr.height >= 3.0:
                x=round((rr.x0+rr.x1)/2,1)
                xs[x]+=1
                if len(samples)<120:
                    samples.append({"x":x,"y0":round(rr.y0,1),"y1":round(rr.y1,1),"fill":d.get("fill"),"color":d.get("color")})
        out.append({"page":pi+1,"commonX":[{"x":x,"count":n} for x,n in xs.most_common(20)],"samples":samples})
    print("AMGEN_SEPARATOR_DIAGNOSTIC "+json.dumps({"pages":out},ensure_ascii=False),flush=True)

if __name__=="__main__": main()
