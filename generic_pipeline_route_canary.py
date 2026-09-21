"""Read-only Menarini official GraphQL pipeline canary."""
import asyncio, json, re
import httpx

BASE="https://www.menarini.com"
PATHS=[
 "/content/dam/menarini-com/content-fragments/en_us/pipeline-tables/pipeline-and-products/oncology-(focus-on-compound)",
 "/content/dam/menarini-com/content-fragments/en_us/pipeline-tables/pipeline-and-products/oncology-(focus-on-indication)",
 "/content/dam/menarini-com/content-fragments/en_us/pipeline-tables/pipeline-and-products/anti-infectives-table-1",
 "/content/dam/menarini-com/content-fragments/en_us/pipeline-tables/pipeline-and-products/anti-infectives-table-2",
 "/content/dam/menarini-com/content-fragments/en_us/pipeline-tables/pipeline-and-products/cardio-metabolic-table-focus-on-compound",
 "/content/dam/menarini-com/content-fragments/en_us/pipeline-tables/pipeline-and-products/cardio-metabolic-table-focus-on-indication",
]
HEADERS={"User-Agent":"Mozilla/5.0 MenariniGraphQLPipelineCanary/1.0","Accept":"application/json,*/*;q=0.8"}

def clean(x): return re.sub(r"\s+"," ",str(x or "")).strip()

async def main():
  async with httpx.AsyncClient(timeout=30.0,follow_redirects=True,headers=HEADERS) as c:
    all_rows=[]
    for path in PATHS:
      url=BASE+"/graphql/execute.json/menarini-com/pipeline-table;path="+path
      try:
        r=await c.get(url)
        payload={"path":path,"status":r.status_code,"contentType":r.headers.get("content-type"),"chars":len(r.text)}
        data=None
        try: data=r.json()
        except Exception: pass
        item=((data or {}).get("data") or {}).get("pipelineTableByPath") or {}
        item=item.get("item") if isinstance(item,dict) else None
        rows=(item or {}).get("pipelineItems") if isinstance(item,dict) else None
        rows=rows if isinstance(rows,list) else []
        payload["groupByFirstColumn"]=(item or {}).get("groupByFirstColumn") if isinstance(item,dict) else None
        payload["rowCount"]=len(rows)
        payload["keys"]=sorted({k for x in rows if isinstance(x,dict) for k in x.keys()})
        payload["sample"]=rows[:4]
        all_rows.extend(rows)
        print("MENARINI_GRAPHQL_TABLE "+json.dumps(payload,ensure_ascii=False),flush=True)
      except Exception as exc:
        print("MENARINI_GRAPHQL_TABLE "+json.dumps({"path":path,"error":f"{type(exc).__name__}: {exc}"},ensure_ascii=False),flush=True)

    compound_rows=[]
    for x in all_rows:
      if not isinstance(x,dict): continue
      compound=clean(x.get("compound")); indication=clean(x.get("indication")); stage=clean(x.get("developmentStage"))
      if compound and indication and stage:
        compound_rows.append((compound,indication,stage))
    unique=list(dict.fromkeys(compound_rows))
    print("MENARINI_GRAPHQL_SUMMARY "+json.dumps({
      "rawRows":len(all_rows),"coreCompleteRows":len(compound_rows),"uniqueCoreRows":len(unique),
      "sampleUnique":[{"compound":a,"indication":b,"developmentStage":c} for a,b,c in unique[:15]],
      "masterWrites":0
    },ensure_ascii=False),flush=True)

if __name__=="__main__":
  asyncio.run(main())
