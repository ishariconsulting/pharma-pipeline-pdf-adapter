"""Additive Render service entrypoint.

Loads the existing FastAPI app unchanged, then registers the read-only
retrieval router, AstraZeneca Portfolio Discovery staging export startup work,
Lilly official investor-document extraction, and Bristol Myers Squibb official
pipeline extraction. No master-data or production automation write paths are added.
"""

from html_fetch_extension import app  # noqa: F401
import routed_html_extension  # noqa: E402,F401
import astrazeneca_staging_export  # noqa: E402,F401
import lilly_static_extension  # noqa: E402,F401
import bms_pipeline_extension  # noqa: E402,F401
