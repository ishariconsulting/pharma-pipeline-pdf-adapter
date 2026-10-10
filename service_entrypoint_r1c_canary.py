"""Isolated R1C canary entrypoint.

Use only on a separately approved non-production Render canary:
    uvicorn service_entrypoint_r1c_canary:app --host 0.0.0.0 --port $PORT

The current production entrypoint and /compare/portfolio-discovery endpoint
are unchanged. No Airtable writes or Portfolio master writes are introduced.
"""
from service_entrypoint import app  # noqa: F401
import programme_compare_r1c_v1  # noqa: E402,F401
