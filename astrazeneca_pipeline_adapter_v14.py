"""V1.4 additive source-hygiene patch for AstraZeneca pipeline parsing.

Fixes one false-positive token repair exposed by post-deployment QA: the V1.3
missing-separator repair treated the lowercase suffix `iris` inside `Ultomiris`
as the study token `IRIS`, producing the false asset `Ultom`.

V1.4 keeps the same deterministic missing-separator repair but makes study-family
matching case-sensitive. This still repairs source forms such as
`EnhertuDESTINY-PanTumor02`, while never splitting `Ultomiris` on its lowercase
suffix.

No fuzzy matching, source acquisition changes, commercial-scope changes, or
Airtable/master-data writes are introduced.
"""

import re
from typing import Any, Dict

import astrazeneca_pipeline_adapter as base
import astrazeneca_pipeline_adapter_v13 as v13


AZ_PIPELINE_VERSION = "V1.4.0 ASTRAZENECA OFFICIAL PIPELINE - CASE-SAFE STUDY TOKEN REPAIR"

# Exact source study-family casing only. The V1.3 regex used re.I, which could
# match a lowercase substring inside a legitimate asset name (Ultomiris ->
# Ultom + IRIS). A genuine attached study token on the source page is displayed
# with its study-family casing, e.g. EnhertuDESTINY-PanTumor02.
_ATTACHED_STUDY_RE_CASE_SAFE = re.compile(
    rf"(?<=[A-Za-z0-9])(?=(?:{v13._STUDY_FAMILIES})(?:[-0-9]|\b))"
)


def _repair_attached_study_token_v14(text: str) -> str:
    return _ATTACHED_STUDY_RE_CASE_SAFE.sub(" ", base._clean(text))


# V1.3's parser resolves this helper from its module globals at call time, so
# replacing only the helper preserves every other V1.3 hygiene rule unchanged.
v13._repair_attached_study_token = _repair_attached_study_token_v14
base.AZ_PIPELINE_VERSION = AZ_PIPELINE_VERSION


def _self_test_v14() -> Dict[str, Any]:
    enhertu = v13._split_program_text_v13(
        "EnhertuDESTINY-PanTumor02 HER2 expressing solid tumours"
    )
    ultomiris = v13._split_program_text_v13(
        "Ultomiris IRIS haematopoietic stem cell transplant-associated thrombotic microangiopathy"
    )
    return {
        "attached_study_separator_repaired": (
            enhertu.get("asset") == "Enhertu"
            and enhertu.get("indication") == "DESTINY-PanTumor02 HER2 expressing solid tumours"
        ),
        "ultomiris_not_split": (
            ultomiris.get("asset") == "Ultomiris"
            and ultomiris.get("brand") == "Ultomiris"
            and ultomiris.get("indication")
            == "IRIS haematopoietic stem cell transplant-associated thrombotic microangiopathy"
        ),
    }


V14_SELF_TEST_RESULTS = _self_test_v14()
if not all(V14_SELF_TEST_RESULTS.values()):
    raise RuntimeError(
        f"AstraZeneca pipeline adapter V1.4 self-test failed: {V14_SELF_TEST_RESULTS}"
    )
