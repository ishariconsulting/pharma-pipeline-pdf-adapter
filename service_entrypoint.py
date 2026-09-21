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
import bms_pipeline_extension_v3  # noqa: E402,F401
import bms_pipeline_extension_v4  # noqa: E402,F401
import generic_pipeline_extension  # noqa: E402,F401
import generic_xlsx_pipeline_extension  # noqa: E402,F401
import generic_pdf_grid_pipeline_extension  # noqa: E402,F401
import generic_pdf_pipeline_extension  # noqa: E402,F401
import sitecore_sxa_pipeline_extension  # noqa: E402,F401
import ionis_json_pipeline_extension  # noqa: E402,F401
import amgen_json_pipeline_extension  # noqa: E402,F401
import abbvie_pdf_pipeline_extension  # noqa: E402,F401
import generic_json_pipeline_extension  # noqa: E402,F401
import menarini_graphql_pipeline_extension  # noqa: E402,F401
import drupal_views_pipeline_extension  # noqa: E402,F401
import merck_kgaa_js_pipeline_extension  # noqa: E402,F401
import biontech_graphql_pipeline_extension  # noqa: E402,F401
import biontech_reconciliation_canary  # noqa: E402,F401
import wave_pipeline_extension  # noqa: E402,F401
import wave_reconciliation_canary  # noqa: E402,F401
