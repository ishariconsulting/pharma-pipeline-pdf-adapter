"""Read-only Amgen seven-row promotion QA canary."""
import asyncio, json
from amgen_json_pipeline_extension import extract_amgen_pipeline

TARGETS={
"amgen:2:2:1",
"amgen:1:1:1",
"amgen:24:1:1",
"amgen:17:2:1",
"amgen:2:3:1",
"amgen:11:2:1",
"amgen:12:1:2",
}

async def main():
    r=await extract_amgen_pipeline("Amgen","https://www.amgenpipeline.com/",35.0)
    selected=[]
    for row in r.rows:
        if row.get("sourceRecordId") in TARGETS:
            selected.append({
                "sourceRecordId":row.get("sourceRecordId"),
                "asset":row.get("asset"),
                "brand":row.get("brand"),
                "molecule":row.get("molecule"),
                "developmentCode":row.get("developmentCode"),
                "indication":row.get("indication"),
                "phase":row.get("phase"),
                "therapeuticArea":row.get("therapeuticArea"),
                "modality":row.get("modality"),
                "description":row.get("description"),
                "additionalInformation":row.get("additionalInformation"),
            })
    print("AMGEN_PROMOTION_QA "+json.dumps({
        "rowCount":r.rowCount,
        "selectedCount":len(selected),
        "selected":selected,
        "issues":r.issues,
        "masterWrites":0,
    },ensure_ascii=False),flush=True)

if __name__=="__main__":
    asyncio.run(main())
