"""Opt-in, read-only original-source evidence envelope for shared pipeline adapters.

This helper preserves what the publisher actually returned. It never verifies a
clinical programme, interprets an arm, or authorises a Portfolio/Candidate write.
"""
from __future__ import annotations

import hashlib
from html.parser import HTMLParser
import json
import re
from typing import Any, Mapping
from urllib.parse import urlparse


_NCT_PATH = re.compile(r"^/(?:study|ct2/show)/(NCT\d{8})(?:/|$)", re.I)


class _RegistryLinkCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.urls: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        href = dict(attrs).get("href") or ""
        try:
            parsed = urlparse(href.strip())
            if (parsed.scheme.lower() != "https" or
                    (parsed.hostname or "").lower() not in {"clinicaltrials.gov", "www.clinicaltrials.gov"} or
                    not _NCT_PATH.match(parsed.path)):
                return
        except ValueError:
            return
        if href not in self.urls:
            self.urls.append(href)


def original_item_evidence(
    item: Mapping[str, Any], *, source_record_id: str, official_url: str,
    retrieved_at: str, original_text: str, stable_id_present: bool,
) -> dict[str, Any]:
    """Lossless official item capture. All clinical relationships remain unverified.

    `retrieved_at` is the observation time, NOT a publication date. In particular,
    no source-issued as-of date or arm evidence is inferred from arbitrary JSON.
    """
    canonical = json.dumps(dict(item), ensure_ascii=False, sort_keys=True,
                           separators=(",", ":"), allow_nan=False)
    # Detached snapshot: later adapter mutations cannot rewrite observed evidence.
    original = json.loads(canonical)
    collector = _RegistryLinkCollector()
    collector.feed(str(original.get("Html") or ""))
    links = []
    for url in collector.urls:
        match = _NCT_PATH.match(urlparse(url).path)
        if match:
            links.append({"nct": match.group(1).upper(), "url": url,
                          "status": "OBSERVED_LINK_NOT_VERIFIED"})
    return {
        "contractVersion": "SOURCE_ITEM_EVIDENCE_V1_READ_ONLY",
        "sourceRecordId": source_record_id,
        "stableSourceRecordIdPresent": stable_id_present,
        "officialPageUrl": official_url,
        "retrievedAt": retrieved_at,
        "sourceAsOf": None,
        "originalSourceItem": original,
        "originalSourceText": original_text,
        "originalSourceItemSha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "observedRegistryLinks": links,
        "programmeToNctVerified": False,
        "focalArmVerified": False,
        "programmeScopeVerified": False,
        "writeEligible": False,
        "verificationGate": "CAPTURED_UNVERIFIED",
    }
