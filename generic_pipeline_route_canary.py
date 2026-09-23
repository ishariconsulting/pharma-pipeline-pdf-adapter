"""Read-only promotion and generic-pipeline startup canaries."""
import asyncio, json
from amgen_json_pipeline_extension import extract_amgen_pipeline
from generic_pipeline_extension import _extract_generic_pipeline
from generic_pipeline_interpreter_canary import norm

TARGETS={
"amgen:2:2:1",
"amgen:1:1:1",
"amgen:24:1:1",
"amgen:17:2:1",
"amgen:2:3:1",
"amgen:11:2:1",
"amgen:12:1:2",
}

GENERIC_CONTEXT_ASSETS={
    "liver",
    "muscle",
    "lung",
    "cns",
    "adipose",
    "brain",
    "kidney",
    "heart",
    "skin",
    "blood",
    "bone",
    "bone marrow",
    "retina",
    "eye",
    "skeletal muscle",
    "central nervous system",
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

    arrowhead=await _extract_generic_pipeline(
        company="Arrowhead Pharmaceuticals",
        source_url="https://arrowheadpharma.com/en-us/pipeline",
        timeout_seconds=35.0,
    )
    bad_assets=sorted({
        row.get("asset","")
        for row in arrowhead.rows
        if (
            norm(row.get("asset","")) in GENERIC_CONTEXT_ASSETS
            or any(
                term in norm(row.get("asset",""))
                for term in (
                    "years old",
                    "all sexes",
                    "healthy volunteers",
                    "eligibility criteria",
                    "participants",
                    "locations",
                )
            )
            or any(
                term in norm(row.get("asset",""))
                for term in (
                    "licensed to",
                    "licensed from",
                    "partnered with",
                    "in collaboration with",
                )
            )
            or str(row.get("asset","")).strip().replace(".", "", 1).isdigit()
            or __import__("re").fullmatch(
                r"(?:january|february|march|april|may|june|july|august|september|october|november|december)(?:\s+\d{1,2},?)?\s+\d{4}",
                str(row.get("asset","")).strip(),
                flags=__import__("re").I,
            ) is not None
        )
    })
    if not arrowhead.readyForDiscovery:
        raise RuntimeError(
            "Arrowhead generic canary failed structural validation: "
            + json.dumps(arrowhead.validation,ensure_ascii=False)
        )
    if bad_assets:
        raise RuntimeError(
            "Arrowhead generic canary emitted context labels as assets: "
            + json.dumps(bad_assets,ensure_ascii=False)
        )
    print("ARROWHEAD_GENERIC_QA "+json.dumps({
        "rowCount":arrowhead.rowCount,
        "selectedMethod":arrowhead.summary.get("selectedMethod"),
        "assets":[row.get("asset") for row in arrowhead.rows],
        "rows":[{
            "sourceRecordId":row.get("sourceRecordId"),
            "asset":row.get("asset"),
            "developmentCode":row.get("developmentCode"),
            "indication":row.get("indication"),
            "phase":row.get("phase"),
        } for row in arrowhead.rows],
        "badContextAssets":bad_assets,
        "readyForDiscovery":arrowhead.readyForDiscovery,
        "masterWrites":0,
    },ensure_ascii=False),flush=True)

if __name__=="__main__":
    asyncio.run(main())
