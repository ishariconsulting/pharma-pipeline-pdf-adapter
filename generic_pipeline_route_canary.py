"""Read-only Wave rendered layout diagnostic using generic browser layout extraction."""
import asyncio, json, os
import httpx

URL="https://wavelifesciences.com/pipeline/research-and-development/"
BASE=os.environ.get("BROWSER_FETCH_BASE_URL","").rstrip("/")
KEY=os.environ.get("BROWSER_FETCH_KEY","")

async def main():
    out={"configured":bool(BASE and KEY),"masterWrites":0}
    if not BASE or not KEY:
        print("WAVE_LAYOUT_DIAGNOSTIC "+json.dumps(out),flush=True)
        return
    async with httpx.AsyncClient(timeout=60.0,follow_redirects=False) as c:
        r=await c.get(
            BASE+"/fetch/browser",
            params={"url":URL,"timeout_seconds":35.0,"include_layout":"true"},
            headers={"X-Browser-Key":KEY,"Accept":"application/json"},
        )
        out["status"]=r.status_code
        out["bodyHead"]=r.text[:1200]
        try:
            p=r.json()
        except Exception:
            p={}
        nodes=p.get("layoutTextNodes") or []
        focus=[]
        wanted=("program","discovery","ind / cta","clinical","patient population","wve-","rna editing","rnai","splicing","silencing","inhbe","serpina1","pnpla3","dmd","mhtt")
        for n in nodes:
            text=str(n.get("text") or "")
            if any(term in text.lower() for term in wanted):
                focus.append(n)
        out.update({
            "version":p.get("version"),
            "finalUrl":p.get("finalUrl"),
            "visibleLineCount":len(p.get("visibleLines") or []),
            "layoutNodeCount":len(nodes),
            "focusNodes":focus[:500],
        })
    print("WAVE_LAYOUT_DIAGNOSTIC "+json.dumps(out,ensure_ascii=False),flush=True)

if __name__=="__main__":
    asyncio.run(main())
