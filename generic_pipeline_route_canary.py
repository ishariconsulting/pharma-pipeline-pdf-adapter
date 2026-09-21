"""Read-only compact BioNTech schema canary for adapter construction."""
import asyncio, json
import httpx

BIO_GQL="https://www.biontech.com/content/_cq_graphql/pipeline-v2/endpoint.json"
HEADERS={"User-Agent":"Mozilla/5.0 BioNTechGraphQLCanary/1.1","Accept":"application/json"}

QUERY=r"""
query CompactTypes {
  indication: __type(name: "IndicationModel") {
    name fields { name type { kind name ofType { kind name ofType { kind name } } } }
  }
  candidate: __type(name: "ProductCandidateModel") {
    name fields { name type { kind name ofType { kind name ofType { kind name } } } }
  }
  metadata: __type(name: "ProductCandidateMetadataModel") {
    name fields { name type { kind name ofType { kind name ofType { kind name } } } }
  }
  platform: __type(name: "PlatformModel") {
    name fields { name type { kind name ofType { kind name ofType { kind name } } } }
  }
  tag: __type(name: "TagModel") {
    name fields { name type { kind name ofType { kind name ofType { kind name } } } }
  }
}
"""

def named(t):
    cur=t or {}
    for _ in range(4):
        if cur.get("name"): return cur.get("name")
        cur=cur.get("ofType") or {}
    return None

def compact_type(v):
    if not v: return None
    return {
      "name":v.get("name"),
      "fields":[{"name":f.get("name"),"type":named(f.get("type"))} for f in (v.get("fields") or [])]
    }

async def main():
    async with httpx.AsyncClient(timeout=45.0,follow_redirects=True,headers=HEADERS) as c:
        r=await c.post(BIO_GQL,json={"query":QUERY})
        q=r.json()
        data=q.get("data") or {}
        print("BIONTECH_COMPACT_TYPES "+json.dumps({
          "status":r.status_code,
          "errors":q.get("errors"),
          "indication":compact_type(data.get("indication")),
          "candidate":compact_type(data.get("candidate")),
          "metadata":compact_type(data.get("metadata")),
          "platform":compact_type(data.get("platform")),
          "tag":compact_type(data.get("tag")),
          "masterWrites":0
        },ensure_ascii=False),flush=True)

if __name__=="__main__":
    asyncio.run(main())
