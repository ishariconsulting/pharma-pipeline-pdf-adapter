"""Read-only BioNTech AEM GraphQL contract canary.

Discovers the concrete schema types and validates a minimal pipeline query against
BioNTech's first-party AEM GraphQL endpoint. No Airtable or master-data writes.
"""
import asyncio, json
import httpx

BIO_GQL="https://www.biontech.com/content/_cq_graphql/pipeline-v2/endpoint.json"
PIPELINE_PATH="/content/dam/pipeline-v2/en/en-pipeline"
DIRECTORY_PATH="/content/dam/pipeline-v2/en"
HEADERS={"User-Agent":"Mozilla/5.0 BioNTechGraphQLCanary/1.0","Accept":"application/json"}

TYPE_QUERY=r"""
query TypeDiag {
  __schema {
    types {
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
}
"""

MIN_QUERY=r"""
query GetBioPipeline($pipelinePath: String!, $directoryPath: ID!) {
  pipelineByPath(_path: $pipelinePath) {
    item {
      _path
      enableProductShare
      enableIndicationShare
      therapeuticAreaRef {
        _path
        name
        productCandidateRef {
          _path
          candidateName
        }
      }
    }
  }
  therapeuticAreaList(
    filter: {
      _path: {
        _expressions: [
          { value: $directoryPath, _operator: STARTS_WITH }
        ]
      }
    }
  ) {
    items { _path name }
  }
  diseaseList(
    filter: {
      _path: {
        _expressions: [
          { value: $directoryPath, _operator: STARTS_WITH }
        ]
      }
    }
  ) {
    items { _path label type }
  }
}
"""

def type_name(t):
    cur=t or {}
    for _ in range(4):
        if cur.get("name"):
            return cur.get("name")
        cur=cur.get("ofType") or {}
    return None

async def main():
    async with httpx.AsyncClient(timeout=45.0,follow_redirects=True,headers=HEADERS) as c:
        rr=await c.post(BIO_GQL,json={"query":TYPE_QUERY})
        payload=rr.json()
        wanted=[]
        keys=("pipeline","productcandidate","indication","therapeuticarea","disease","metadata","platform","drugclass","collaborator")
        for typ in ((payload.get("data") or {}).get("__schema") or {}).get("types") or []:
            name=str(typ.get("name") or "")
            if any(k in name.lower() for k in keys):
                fields=[]
                for f in typ.get("fields") or []:
                    fields.append({"name":f.get("name"),"type":type_name(f.get("type")),"rawType":f.get("type")})
                wanted.append({"name":name,"kind":typ.get("kind"),"fields":fields})
        print("BIONTECH_RELEVANT_TYPES "+json.dumps({
          "status":rr.status_code,
          "errors":payload.get("errors"),
          "types":wanted
        },ensure_ascii=False),flush=True)

        qr=await c.post(BIO_GQL,json={
          "query":MIN_QUERY,
          "variables":{"pipelinePath":PIPELINE_PATH,"directoryPath":DIRECTORY_PATH},
        })
        try: q=qr.json()
        except Exception: q={"raw":qr.text[:4000]}
        data=q.get("data") or {}
        pipe=((data.get("pipelineByPath") or {}).get("item") or {})
        tas=pipe.get("therapeuticAreaRef") or []
        candidates=[]
        for ta in tas:
            for pc in ta.get("productCandidateRef") or []:
                candidates.append({
                  "ta":ta.get("name"),"_path":pc.get("_path"),"candidateName":pc.get("candidateName")
                })
        print("BIONTECH_MIN_QUERY "+json.dumps({
          "status":qr.status_code,
          "errors":q.get("errors"),
          "pipelinePath":pipe.get("_path"),
          "therapeuticAreaCount":len(tas),
          "candidateCount":len(candidates),
          "candidateSample":candidates[:20],
          "therapeuticAreaListCount":len((data.get("therapeuticAreaList") or {}).get("items") or []),
          "diseaseListCount":len((data.get("diseaseList") or {}).get("items") or []),
          "masterWrites":0
        },ensure_ascii=False),flush=True)

if __name__=="__main__":
    asyncio.run(main())
