"""Read-only Amgen pipeline transport-endpoint diagnostic."""

import asyncio, json, re
from generic_pipeline_extension import _fetch_raw_public_html

URL="https://www.amgenpipeline.com/"

async def main():
    try:
        html, final_url = await _fetch_raw_public_html(URL, timeout_seconds=30.0)
        snippets=[]
        patterns=[
          r'https?://[^"\'<>\\s]+',
          r'[^"\'<>\\s]{0,100}(?:api|json|pipeline|graphql|search|molecule)[^"\'<>\\s]{0,160}'
        ]
        seen=set()
        for pat in patterns:
          for m in re.finditer(pat, html, re.I):
            s=re.sub(r"\\s+"," ",m.group(0))[:500]
            if s in seen: continue
            seen.add(s)
            if re.search(r"api|json|pipeline|graphql|molecule",s,re.I):
              snippets.append(s)
            if len(snippets)>=120: break
          if len(snippets)>=120: break
        payload={"finalUrl":final_url,"htmlChars":len(html),"snippets":snippets}
    except Exception as exc:
        payload={"error":f"{type(exc).__name__}: {exc}"}
    print("AMGEN_ENDPOINT_DIAGNOSTIC "+json.dumps(payload,ensure_ascii=False),flush=True)

if __name__=="__main__":
    asyncio.run(main())
