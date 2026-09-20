from fastapi import HTTPException, Query
from fastapi.responses import PlainTextResponse
from pathlib import Path
from html_fetch_extension import app

_TOKEN = "v258-export-20260920-7d4c91f2"
_PATH = Path(__file__).parent / "airtable_scripts" / "pipeline_source_watch_recurring_v2_58.js"

@app.get("/internal/export/v258", response_class=PlainTextResponse)
async def export_v258(token: str = Query(...)):
    if token != _TOKEN:
        raise HTTPException(status_code=404, detail="Not found")
    return PlainTextResponse(_PATH.read_text(encoding="utf-8"), media_type="text/plain; charset=utf-8")
