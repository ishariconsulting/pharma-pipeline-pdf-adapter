"""Additive Render service entrypoint.

Loads the existing FastAPI app unchanged, then registers the read-only
AstraZeneca Portfolio Discovery staging export startup task. No master-data or
production automation write paths are added.
"""

from html_fetch_extension import app  # noqa: F401
import astrazeneca_staging_export  # noqa: E402,F401
