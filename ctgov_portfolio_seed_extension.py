"""Generic ClinicalTrials.gov portfolio-seed adapter.

Purpose
-------
Provide a safe cross-source fallback when an official company pipeline source
cannot be retrieved or structurally parsed. Uses only the public
ClinicalTrials.gov API v2 and returns the same read-only discovery row contract
used by company-pipeline adapters.

Guardrails
----------
- public ClinicalTrials.gov API only;
- no Airtable access and no master-data writes;
- sponsor-scoped, experimental-intervention only;
- placebo/sham/control interventions excluded;
- Phase 1 remains source-visible but commercial policy decides inclusion later;
- fail closed if API pagination is truncated or no structured programme rows
  can be recovered;
- no company-specific asset names or programme rules.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import httpx
from fastapi import Header, HTTPException, Query
from pydantic import BaseModel

from main import _auth, app


VERSION = "CTGOV_PORTFOLIO_SEED_V1.0_READ_ONLY"
MAX_PAGES = 5
PAGE_SIZE_LIMIT = 100

ALLOWED_INTERVENTION_TYPES = {
    "DRUG",
    "BIOLOGICAL",
    "GENETIC",
    "COMBINATION_PRODUCT",
}

CONTROL_TERMS = re.compile(
    r"\b(placebo|sham|control|standard of care|standard-of-care|soc only|vehicle)\b",
    re.I,
)

CORPORATE_SUFFIXES = {
    "inc", "incorporated", "corp", "corporation", "company", "co",
    "limited", "ltd", "plc", "llc", "pharmaceutical", "pharmaceuticals",
    "therapeutics", "biopharma", "biotechnology",
}


class CtgovPortfolioSeedResponse(BaseModel):
    version: str
    company: str
    sourceUrl: str
    retrievalMode: str
    readOnly: bool
    readyForDiscovery: bool
    rowCount: int
    rows: List[Dict[str, Any]]
    summary: Dict[str, Any]
    issues: List[Dict[str, Any]]
    validation: Dict[str, Any]
    diagnostics: Dict[str, Any]
    guardrails: Dict[str, Any]


def clean(value: Any) -> str:
    if value is None:
        return ""
    value = unicodedata.normalize("NFKC", str(value))
    value = (
        value.replace("\u2010", "-")
        .replace("\u2011", "-")
        .replace("\u2012", "-")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("\u2212", "-")
    )
    return re.sub(r"\s+", " ", value).strip()


def norm(value: Any) -> str:
    value = clean(value).lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def company_root(value: Any) -> str:
    tokens = [x for x in norm(value).split() if x not in CORPORATE_SUFFIXES]
    return " ".join(tokens).strip()


def sponsor_matches(company: str, sponsor: str) -> bool:
    c = company_root(company)
    s = company_root(sponsor)
    if not c or not s:
        return False
    return c == s or c.startswith(s + " ") or s.startswith(c + " ")


def phase_label(values: List[str]) -> str:
    ranks: List[int] = []
    for raw in values or []:
        n = norm(raw).replace(" ", "")
        if n in {"earlyphase1", "phase1"}:
            ranks.append(1)
        elif n == "phase2":
            ranks.append(2)
        elif n == "phase3":
            ranks.append(3)
        elif n == "phase4":
            ranks.append(4)
    if not ranks:
        return ""
    return f"Phase {max(ranks)}"


def friendly_status(value: Any) -> str:
    n = clean(value).upper()
    mapping = {
        "RECRUITING": "Recruiting",
        "NOT_YET_RECRUITING": "Not yet recruiting",
        "ACTIVE_NOT_RECRUITING": "Active, not recruiting",
        "ENROLLING_BY_INVITATION": "Enrolling by invitation",
        "COMPLETED": "Completed",
        "TERMINATED": "Terminated",
        "WITHDRAWN": "Withdrawn",
        "SUSPENDED": "Suspended",
        "UNKNOWN": "Unknown",
    }
    return mapping.get(n, clean(value).replace("_", " ").title())


def phase_rank(value: str) -> int:
    m = re.search(r"\bPhase\s*([1-4])\b", clean(value), re.I)
    return int(m.group(1)) if m else 0


def status_priority(value: str) -> int:
    n = norm(value)
    if n in {
        "recruiting",
        "not yet recruiting",
        "active not recruiting",
        "enrolling by invitation",
    }:
        return 4
    if n == "completed":
        return 3
    if n in {"suspended", "terminated", "withdrawn"}:
        return 1
    return 2


def experimental_names(arms: Dict[str, Any]) -> Set[str]:
    out: Set[str] = set()
    for group in arms.get("armGroups") or []:
        if clean(group.get("type")).upper() != "EXPERIMENTAL":
            continue
        for name in group.get("interventionNames") or []:
            raw = clean(name)
            raw = re.sub(
                r"^(?:DRUG|BIOLOGICAL|GENETIC|COMBINATION_PRODUCT)\s*:\s*",
                "",
                raw,
                flags=re.I,
            )
            if raw:
                out.add(norm(raw))
    return out


def intervention_is_experimental(
    intervention: Dict[str, Any],
    exp_names: Set[str],
    title: str,
) -> bool:
    itype = clean(intervention.get("type")).upper()
    if itype not in ALLOWED_INTERVENTION_TYPES:
        return False

    name = clean(intervention.get("name"))
    if not name or CONTROL_TERMS.search(name):
        return False

    variants = [name, *(intervention.get("otherNames") or [])]
    variant_norms = [norm(v) for v in variants if norm(v)]

    if exp_names:
        for variant in variant_norms:
            if any(
                variant == exp or variant in exp or exp in variant
                for exp in exp_names
            ):
                return True
        return False

    title_norm = norm(title)
    if any(v and v in title_norm for v in variant_norms):
        return True

    # Development-code identities are usually source-specific investigational
    # assets rather than background standard-of-care comparators.
    if re.search(r"\b[A-Z]{2,}[A-Z0-9-]*\d+[A-Z0-9-]*\b", name):
        return True

    return False


def _validated_source_url(source_url: str) -> str:
    parsed = urlparse(source_url)
    if parsed.scheme != "https":
        raise HTTPException(status_code=400, detail="CT.gov fallback requires HTTPS")
    if (parsed.hostname or "").lower() != "clinicaltrials.gov":
        raise HTTPException(status_code=400, detail="CT.gov fallback only accepts clinicaltrials.gov")
    if not parsed.path.startswith("/api/v2/studies"):
        raise HTTPException(status_code=400, detail="CT.gov fallback requires /api/v2/studies")
    return source_url


def with_page_token(url: str, token: str) -> str:
    parsed = urlparse(url)
    q = dict(parse_qsl(parsed.query, keep_blank_values=True))
    q["pageToken"] = token
    q["pageSize"] = str(min(PAGE_SIZE_LIMIT, int(q.get("pageSize") or PAGE_SIZE_LIMIT)))
    return urlunparse(parsed._replace(query=urlencode(q)))


async def fetch_studies(source_url: str, timeout_seconds: float) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    source_url = _validated_source_url(source_url)
    headers = {
        "User-Agent": "IshariPharmaIntelligence/1.0 CTGovFallback",
        "Accept": "application/json",
    }

    studies: List[Dict[str, Any]] = []
    page_url = source_url
    pages = 0
    next_token: Optional[str] = None

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds, connect=min(12.0, timeout_seconds)),
            follow_redirects=True,
            headers=headers,
        ) as client:
            for _ in range(MAX_PAGES):
                response = await client.get(page_url)
                if response.status_code != 200:
                    raise HTTPException(
                        status_code=502,
                        detail=f"ClinicalTrials.gov returned HTTP {response.status_code}",
                    )
                try:
                    payload = response.json()
                except Exception as exc:
                    raise HTTPException(
                        status_code=502,
                        detail="ClinicalTrials.gov returned invalid JSON",
                    ) from exc

                batch = payload.get("studies") or []
                if not isinstance(batch, list):
                    raise HTTPException(
                        status_code=502,
                        detail="ClinicalTrials.gov studies payload is not an array",
                    )
                studies.extend(batch)
                pages += 1

                next_token = clean(payload.get("nextPageToken")) or None
                if not next_token:
                    break
                page_url = with_page_token(source_url, next_token)
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="ClinicalTrials.gov fallback timed out") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"ClinicalTrials.gov fallback failed: {exc}") from exc

    return studies, {
        "pagesFetched": pages,
        "studyCount": len(studies),
        "paginationTruncated": bool(next_token),
        "maxPages": MAX_PAGES,
    }


def normalize_studies(
    company: str,
    source_url: str,
    studies: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    grouped: Dict[str, Dict[str, Any]] = {}
    sponsor_rejected = 0
    no_phase = 0
    no_experimental_asset = 0
    study_rows = 0

    for study in studies:
        ps = study.get("protocolSection") or {}
        ident = ps.get("identificationModule") or {}
        status = ps.get("statusModule") or {}
        design = ps.get("designModule") or {}
        conditions_mod = ps.get("conditionsModule") or {}
        sponsor_mod = ps.get("sponsorCollaboratorsModule") or {}
        arms = ps.get("armsInterventionsModule") or {}

        nct = clean(ident.get("nctId"))
        title = clean(ident.get("briefTitle") or ident.get("officialTitle"))
        lead = clean((sponsor_mod.get("leadSponsor") or {}).get("name"))

        if lead and not sponsor_matches(company, lead):
            sponsor_rejected += 1
            continue

        phase = phase_label(design.get("phases") or [])
        if not phase:
            no_phase += 1
            continue

        conditions = [
            clean(x) for x in (conditions_mod.get("conditions") or [])
            if clean(x)
        ]
        if not conditions:
            continue

        exp_names = experimental_names(arms)
        interventions = [
            i for i in (arms.get("interventions") or [])
            if intervention_is_experimental(i, exp_names, title)
        ]
        if not interventions:
            no_experimental_asset += 1
            continue

        study_status = friendly_status(status.get("overallStatus"))

        for intervention in interventions:
            asset = clean(intervention.get("name"))
            other_names = [
                clean(x) for x in (intervention.get("otherNames") or [])
                if clean(x)
            ]
            for indication in conditions:
                study_rows += 1
                key = norm(asset) + "|" + norm(indication)
                existing = grouped.get(key)

                candidate = {
                    "company": company,
                    "sourceFamily": "ClinicalTrials.gov",
                    "sourceRecordId": f"ctgov-fallback:{norm(asset).replace(' ', '_')}:{norm(indication).replace(' ', '_')}",
                    "sourceUrl": f"https://clinicaltrials.gov/study/{nct}" if nct else source_url,
                    "asset": asset,
                    "molecule": asset,
                    "developmentCode": asset if re.search(r"\d", asset) else "",
                    "brand": "",
                    "indication": indication,
                    "phase": phase,
                    "programStatus": study_status,
                    "sponsorOwner": lead or company,
                    "partners": [],
                    "study": title,
                    "trialIds": [nct] if nct else [],
                    "therapeuticArea": "",
                    "modality": clean(intervention.get("type")).title(),
                    "description": clean(intervention.get("description")),
                    "additionalInformation": "; ".join(other_names),
                    "strategicPhase1": False,
                    "importantLabelExpansion": False,
                    "marketedStrategicRx": False,
                    "genericCommodity": False,
                    "ownershipResolved": True,
                }

                if existing is None:
                    grouped[key] = candidate
                    continue

                merged_trials = sorted(set(
                    (existing.get("trialIds") or []) + (candidate.get("trialIds") or [])
                ))
                existing["trialIds"] = merged_trials

                if phase_rank(candidate["phase"]) > phase_rank(existing["phase"]):
                    existing["phase"] = candidate["phase"]

                if status_priority(candidate["programStatus"]) > status_priority(existing["programStatus"]):
                    existing["programStatus"] = candidate["programStatus"]

                extra = clean(candidate.get("additionalInformation"))
                if extra and extra not in clean(existing.get("additionalInformation")):
                    existing["additionalInformation"] = clean(
                        (existing.get("additionalInformation") or "") + "; " + extra
                    ).strip("; ")

    rows = list(grouped.values())
    rows.sort(key=lambda r: (norm(r.get("asset")), norm(r.get("indication"))))
    for idx, row in enumerate(rows, start=1):
        row["sourceOrdinal"] = idx

    return rows, {
        "rawStudyProgrammeRows": study_rows,
        "dedupedProgrammeRows": len(rows),
        "sponsorRejectedStudies": sponsor_rejected,
        "studiesWithoutPhase": no_phase,
        "studiesWithoutExperimentalAsset": no_experimental_asset,
    }


async def extract_ctgov_portfolio_seed(
    company: str,
    source_url: str,
    timeout_seconds: float = 30.0,
) -> CtgovPortfolioSeedResponse:
    studies, fetch_diag = await fetch_studies(source_url, timeout_seconds)
    rows, parse_diag = normalize_studies(company, source_url, studies)

    issues: List[Dict[str, Any]] = []
    if fetch_diag["paginationTruncated"]:
        issues.append({
            "issue": "ClinicalTrials.gov pagination exceeded safe fallback limit; coverage is incomplete"
        })
    if not rows:
        issues.append({
            "issue": "No sponsor-scoped experimental asset/indication/phase rows recovered"
        })

    ready = not issues
    diagnostics = {
        **fetch_diag,
        **parse_diag,
        "rowFailures": 0,
        "boundaryWarnings": 0,
        "coverageWarnings": 1 if fetch_diag["paginationTruncated"] else 0,
        "fallbackCoverageMode": "CROSS_SOURCE_PARTIAL",
        "companySpecificParserBranch": False,
        "writes": 0,
    }

    return CtgovPortfolioSeedResponse(
        version=VERSION,
        company=company,
        sourceUrl=source_url,
        retrievalMode="DIRECT",
        readOnly=True,
        readyForDiscovery=ready,
        rowCount=len(rows),
        rows=rows,
        summary={
            "structuralValidationPass": ready,
            "actual": {"Total": len(rows)},
            "selectedMethod": "CTGOV_SPONSOR_EXPERIMENTAL_PROGRAMME_AGGREGATION",
            "productionStatus": (
                "READY FOR PORTFOLIO DISCOVERY COMPARISON"
                if ready
                else "FAIL CLOSED - CTGOV FALLBACK COVERAGE REVIEW REQUIRED"
            ),
        },
        issues=issues,
        validation={
            "pass": ready,
            "rowCount": len(rows),
            "sponsorScoped": True,
            "experimentalInterventionsOnly": True,
            "paginationComplete": not fetch_diag["paginationTruncated"],
        },
        diagnostics=diagnostics,
        guardrails={
            "airtableWrites": False,
            "portfolioWrites": False,
            "masterDataWrites": False,
            "companySpecificParserBranch": False,
            "publicCtgovOnly": True,
            "controlInterventionsExcluded": True,
        },
    )


@app.get("/extract/generic/ctgov-portfolio-seed/health")
async def ctgov_portfolio_seed_health() -> Dict[str, Any]:
    return {
        "ok": True,
        "version": VERSION,
        "readOnly": True,
        "source": "ClinicalTrials.gov API v2",
    }


@app.get(
    "/extract/generic/ctgov-portfolio-seed",
    response_model=CtgovPortfolioSeedResponse,
)
async def ctgov_portfolio_seed(
    company: str = Query(..., min_length=1, max_length=180),
    source_url: str = Query(..., min_length=8),
    timeout_seconds: float = Query(default=30.0, ge=5.0, le=35.0),
    x_adapter_key: Optional[str] = Header(default=None),
) -> CtgovPortfolioSeedResponse:
    _auth(x_adapter_key)
    return await extract_ctgov_portfolio_seed(company, source_url, timeout_seconds)
