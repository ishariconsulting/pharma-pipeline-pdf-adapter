"""V1.3 additive precision patch for the AstraZeneca official pipeline adapter.

This patch is deliberately narrow and read-only. It fixes deterministic source-
parsing errors discovered during Portfolio Discovery staging without changing
source acquisition, source row IDs, commercial inclusion rules, or any master-
data write path.

Fixes:
1) parenthetical source qualifiers such as (China) and (platform) are not
   treated as molecules;
2) study/program names before those qualifiers are not folded into the asset;
3) a missing source-space such as EnhertuDESTINY-PanTumor02 is repaired before
   identity parsing;
4) INN forms such as "efzimfotase alfa" remain a two-word molecule;
5) title-case slash brand pairs such as Breztri/Trixeo reconcile on the primary
   brand while retaining the source alias in parse notes;
6) brand (molecule)/co-therapy forms such as
   Baxfendy (baxdrostat)/dapagliflozin keep the molecule out of the indication.

No fuzzy matching and no Airtable/master-data writes are introduced.
"""

import re
from typing import Any, Dict

import astrazeneca_pipeline_adapter as base


AZ_PIPELINE_VERSION = "V1.3.0 ASTRAZENECA OFFICIAL PIPELINE - SOURCE HYGIENE PATCH"

_ORIGINAL_SPLIT = base._split_program_text

# Families observed on the official AstraZeneca pipeline. This list is used
# only to repair a missing separator between a leading asset and a study token;
# it does not infer indication or approval status.
_STUDY_FAMILIES = (
    "ARTEMIDE|SERENA|CAMBRIA|DESTINY|TROPION|PACIFIC|CAPItello|EvoPAR|"
    "SOUNDTRACK|CLARITY|eVOLVE|BaxHTN|BaxPA|CLEAR|TULIP|NAVIGATOR|OBERON|"
    "TITANIA|PROSPERO|MIRANDA|CALYPSO|PREVAIL|CARES|DepleTTR|AUTUMN|CONCORD|"
    "TRANSCEND|DURGA|TREVI|VECTRA|ESCALADE|AMPLIFY|ECHO|KALOS|LOGOS|THARROS|"
    "DAISY|IRIS|JASMINE|LAVENDER|CROSSING|EMBARK|JOURNEY|WAYPOINT|AWAKE|"
    "AZURE|POTOMAC|KUNLUN|VOLGA|NILE|MATTERHORN|POSEIDON|NeoCOAST|HIMALAYA|"
    "SAFFRON|ADAURA|ORCHARD"
)
_ATTACHED_STUDY_RE = re.compile(
    rf"(?<=[A-Za-z0-9])(?=(?:{_STUDY_FAMILIES})(?:[-0-9]|\b))",
    flags=re.I,
)

_NON_MOLECULE_PAREN = {
    "china",
    "platform",
}

_ALFA_BETA_RE = re.compile(
    r"^([a-z][A-Za-z0-9-]*)\s+(alfa|beta)\s+(.+)$"
)

_BRAND_SLASH_RE = re.compile(
    r"^([A-Z][A-Za-z0-9-]+)/([A-Z][A-Za-z0-9-]+)$"
)


def _clean(value: Any) -> str:
    return base._clean(value)


def _append_note(existing: Any, note: str) -> str:
    current = _clean(existing)
    if not current:
        return note
    if note in current:
        return current
    return f"{current}; {note}"


def _repair_attached_study_token(text: str) -> str:
    """Insert one missing separator before a known study family.

    Example: EnhertuDESTINY-PanTumor02 -> Enhertu DESTINY-PanTumor02.
    The raw source text and sourceRecordId remain unchanged elsewhere.
    """
    return _ATTACHED_STUDY_RE.sub(" ", _clean(text))


def _leading_identity(text: str) -> str:
    """Return only the deterministic leading drug/brand identity."""
    cleaned = _clean(text)
    if not cleaned:
        return ""

    code = base.CODE_RE.match(cleaned)
    if code:
        return _clean(code.group(0))

    tokens = cleaned.split()
    if not tokens:
        return ""

    # Preserve lower-case two-word INNs already supported by the base parser.
    if len(tokens) >= 2:
        first, second = tokens[0], tokens[1]
        if (
            first[:1].islower()
            and second[:1].islower()
            and (
                base.TWO_WORD_DRUG_SUFFIX_RE.search(second)
                or second.lower() in {"alfa", "beta"}
            )
            and not base.STUDY_TOKEN_RE.match(second)
        ):
            return _clean(f"{first} {second}")

    return _clean(tokens[0])


def _set_identity_fields(result: Dict[str, Any], identity: str) -> None:
    result["asset"] = identity or None
    result["brand"] = None
    result["molecule"] = None
    if not identity:
        return
    if identity[:1].islower():
        result["molecule"] = identity
    elif not base.CODE_RE.fullmatch(identity):
        result["brand"] = identity


def _split_program_text_v13(text: str) -> Dict[str, Any]:
    original_text = _clean(text)
    repaired_text = _repair_attached_study_token(original_text)

    # Keep INN suffixes such as "alfa" attached to the molecule rather than
    # leaking them into the indication field.
    alfa_beta = _ALFA_BETA_RE.match(repaired_text)
    if alfa_beta:
        molecule = _clean(f"{alfa_beta.group(1)} {alfa_beta.group(2)}")
        indication = _clean(alfa_beta.group(3))
        code_match = base.CODE_RE.search(repaired_text)
        return {
            "asset": molecule,
            "molecule": molecule,
            "developmentCode": _clean(code_match.group(0)) if code_match else None,
            "brand": None,
            "indication": indication or None,
            "parseStatus": "PASS" if indication else "REVIEW",
            "parseNotes": "Two-word INN with alfa/beta suffix",
        }

    # Brand (molecule)/co-therapy disease wording. The co-therapy remains
    # available in the raw programText, but it must not contaminate disease
    # matching in the indication field.
    co_therapy = re.match(
        r"^([^()]+?)\s*\(([^)]+)\)(/[^\s]+)\s+(.+)$",
        repaired_text,
    )
    if co_therapy:
        prefix = _clean(co_therapy.group(1))
        molecule = _clean(co_therapy.group(2))
        co_asset = _clean(co_therapy.group(3)).lstrip("/")
        indication = _clean(co_therapy.group(4))
        if (
            prefix
            and prefix[:1].isupper()
            and molecule[:1].islower()
            and molecule.lower() not in _NON_MOLECULE_PAREN
        ):
            return {
                "asset": prefix,
                "molecule": molecule,
                "developmentCode": None,
                "brand": prefix,
                "indication": indication or None,
                "parseStatus": "PASS" if indication else "REVIEW",
                "parseNotes": f"Brand with parenthetical molecule; source co-therapy={co_asset}",
            }

    result = dict(_ORIGINAL_SPLIT(repaired_text))

    # The base parser intentionally treats any parenthetical string after a
    # title-case prefix as a molecule. That is too broad for market or source
    # qualifiers such as (China) and (platform).
    paren = re.match(r"^(.+?)\s*\(([^)]+)\)\s*(.*)$", repaired_text)
    if paren and _clean(paren.group(2)).lower() in _NON_MOLECULE_PAREN:
        qualifier = _clean(paren.group(2))
        identity = _leading_identity(paren.group(1))
        trailing = _clean(paren.group(3))
        _set_identity_fields(result, identity)
        result["indication"] = trailing or result.get("indication")
        result["parseStatus"] = "PASS" if identity and result.get("indication") else "REVIEW"
        result["parseNotes"] = _append_note(
            result.get("parseNotes"),
            f"Parenthetical source qualifier excluded from molecule: {qualifier}",
        )

    # A development code in parentheses can follow either a molecule or a
    # brand. If the named prefix is title-case / a slash brand pair, do not
    # mirror that brand into the molecule field.
    asset = _clean(result.get("asset"))
    molecule = _clean(result.get("molecule"))
    if result.get("developmentCode") and asset and molecule == asset:
        if asset[:1].isupper() or "/" in asset:
            result["molecule"] = None
            result["brand"] = asset
            result["parseNotes"] = _append_note(
                result.get("parseNotes"),
                "Parenthetical development code attached to brand identity",
            )

    # Two regional title-case brand names separated by slash are aliases, not a
    # single novel molecule/asset. Use the first brand as the comparator
    # identity while retaining the complete source naming in parse notes and
    # raw programText.
    asset = _clean(result.get("asset"))
    brand_alias = _BRAND_SLASH_RE.fullmatch(asset)
    if brand_alias:
        primary, alias = brand_alias.group(1), brand_alias.group(2)
        result["asset"] = primary
        result["brand"] = primary
        if _clean(result.get("molecule")) == asset:
            result["molecule"] = None
        result["parseNotes"] = _append_note(
            result.get("parseNotes"),
            f"Source regional brand alias={alias}",
        )

    if repaired_text != original_text:
        result["parseNotes"] = _append_note(
            result.get("parseNotes"),
            "Repaired missing separator before study/program token",
        )

    return result


base._split_program_text = _split_program_text_v13
base.AZ_PIPELINE_VERSION = AZ_PIPELINE_VERSION


def _self_test_v13() -> Dict[str, Any]:
    checks: Dict[str, bool] = {}

    saphnelo = _split_program_text_v13(
        "Saphnelo TULIP 1 & TULIP 2 AZALEA (China) systemic lupus erythematosus"
    )
    checks["china_not_molecule_saphnelo"] = (
        saphnelo.get("asset") == "Saphnelo"
        and saphnelo.get("brand") == "Saphnelo"
        and not saphnelo.get("molecule")
        and saphnelo.get("indication") == "systemic lupus erythematosus"
    )

    tezspire = _split_program_text_v13(
        "Tezspire NAVIGATOR DIRECTION (China) severe uncontrolled asthma"
    )
    checks["china_not_molecule_tezspire"] = (
        tezspire.get("asset") == "Tezspire"
        and not tezspire.get("molecule")
        and tezspire.get("indication") == "severe uncontrolled asthma"
    )

    platform = _split_program_text_v13(
        "Enhertu (platform) DESTINY-Breast07 HER2+ breast cancer"
    )
    checks["platform_not_molecule"] = (
        platform.get("asset") == "Enhertu"
        and not platform.get("molecule")
        and platform.get("indication") == "DESTINY-Breast07 HER2+ breast cancer"
    )

    attached = _split_program_text_v13(
        "EnhertuDESTINY-PanTumor02 HER2 expressing solid tumours"
    )
    checks["attached_study_repaired"] = (
        attached.get("asset") == "Enhertu"
        and attached.get("brand") == "Enhertu"
        and attached.get("indication") == "DESTINY-PanTumor02 HER2 expressing solid tumours"
    )

    alfa = _split_program_text_v13(
        "efzimfotase alfa Hickory (301), Mulberry (305), Chestnut (303) hypophosphatasia"
    )
    checks["alfa_kept_with_molecule"] = (
        alfa.get("asset") == "efzimfotase alfa"
        and alfa.get("molecule") == "efzimfotase alfa"
        and alfa.get("indication").endswith("hypophosphatasia")
    )

    breztri = _split_program_text_v13(
        "Breztri/Trixeo (PT010) KALOS LOGOS asthma"
    )
    checks["slash_brand_primary_identity"] = (
        breztri.get("asset") == "Breztri"
        and breztri.get("brand") == "Breztri"
        and not breztri.get("molecule")
        and breztri.get("developmentCode") == "PT010"
    )

    baxfendy = _split_program_text_v13(
        "Baxfendy (baxdrostat)/dapagliflozin CKD"
    )
    checks["parenthetical_molecule_cotherapy"] = (
        baxfendy.get("asset") == "Baxfendy"
        and baxfendy.get("brand") == "Baxfendy"
        and baxfendy.get("molecule") == "baxdrostat"
        and baxfendy.get("indication") == "CKD"
    )

    return {"ok": all(checks.values()), "checks": checks}


V13_SELF_TEST_RESULTS = _self_test_v13()
if not V13_SELF_TEST_RESULTS["ok"]:
    raise RuntimeError(f"AstraZeneca source-hygiene self-test failed: {V13_SELF_TEST_RESULTS}")
