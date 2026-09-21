"""Read-only BioNTech schema canary, one introspection type per request."""
import asyncio, json
import httpx

BIO_GQL="https://www.biontech.com/content/_cq_graphql/pipeline-v2/endpoint.json"
HEADERS={"User-Agent":"Mozilla/5.0 BioNTechGraphQLCanary/1.2","Accept":"application/json"}
TYPES=["IndicationModel","ProductCandidateModel","ProductCandidateMetadataModel","PlatformModel","TagModel"]

QUERY=r"""
query OneType($name: String!) {
  __type(name: $name) {
    name
    kind
    fields {
      name
      type {
        kind
        name
        ofType {
          kind
          name
          ofType { kind name }
        }
      }
    }
  }
}
"""

def named(t):
    cur=t or {}
    for _ in range(4):
        if cur.get("name"): return cur.get("name")
        cur=cur.get("ofType") or {}
    return None

async def main():
    out={}
    async with httpx.AsyncClient(timeout=45.0,follow_redirects=True,headers=HEADERS) as c:
        for name in TYPES:
            r=await c.post(BIO_GQL,json={"query":QUERY,"variables":{"name":name}})
            q=r.json()
            v=(q.get("data") or {}).get("__type")
            out[name]={
              "status":r.status_code,
              "errors":q.get("errors"),
              "fields":[{"name":x.get("name"),"type":named(x.get("type"))} for x in ((v or {}).get("fields") or [])]
            }
    print("BIONTECH_COMPACT_TYPES "+json.dumps({"types":out,"masterWrites":0},ensure_ascii=False),flush=True)

if __name__=="__main__":
    asyncio.run(main())
