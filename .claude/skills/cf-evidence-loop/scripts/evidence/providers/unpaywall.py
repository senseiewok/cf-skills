"""Unpaywall: open-access locations, PDF links, and license metadata.

Queries https://api.unpaywall.org/v2/<doi>?email=<contact> using polite Client.
Under Unpaywall terms and lab conduct rules:
- EVIDENCE_CONTACT is required for Unpaywall only; never sent to other providers.
- Operator email address is always redacted from saved evidence records and logged URLs.
- Metadata is CC0; does not assess methodological quality or clinical efficacy.
"""

from __future__ import annotations

import os
import re
from typing import Any
from urllib.parse import quote

from .. import guardrails
from ..http import Client, Fetch
from ..record import Evidence, Status
from ..shape import ShapeError, error_record, need

PROVIDER = "unpaywall/0.1"
SOURCE = "unpaywall"

LIMITATION = (
    "Unpaywall indexes open-access availability, location URLs, and license metadata (CC0 metadata). "
    "Does not evaluate scientific methodology, peer-review rigour, or clinical safety and efficacy."
)


def redact_url(url: str) -> str:
    """Redact email query parameter to prevent leaking operator email into records or ledgers."""
    if not url:
        return ""
    return re.sub(r"([?&]email=)[^&#\s]+", r"\1<redacted>", url)


def _clean_str(val: Any) -> str | None:
    """Return string value, converting prohibited stringified nulls to None."""
    if val is None:
        return None
    s = str(val).strip()
    if s.lower() in guardrails.PROHIBITED_NULL_STRINGS:
        return None
    return s


def parse_unpaywall(data: Any, doi_query: str, question: str, url: str) -> Evidence:
    """Parse Unpaywall API response into a validated Evidence record."""
    safe_url = redact_url(url)
    if not isinstance(data, dict):
        raise ShapeError(f"Unpaywall response is {type(data).__name__}, not an object")

    # Unpaywall error or 404 response
    if (
        data.get("HTTP_status_code") == 404
        or data.get("error") is True
        or "not found" in str(data.get("message", "")).lower()
    ):
        return Evidence(
            status=Status.NOT_FOUND,
            question=question,
            source_id=SOURCE,
            url=safe_url,
            provider=PROVIDER,
            fields={"doi": doi_query},
            limitations="Paper not found in Unpaywall database.",
        )

    try:
        doi = need(data, "doi", "Unpaywall response")
        if not isinstance(doi, str):
            raise ShapeError(f"Unpaywall response doi is {type(doi).__name__}, not a string")
    except ShapeError as exc:
        return error_record(
            exc,
            question=question,
            source_id=SOURCE,
            url=safe_url,
            provider=PROVIDER,
            fields={"doi": doi_query},
        )

    title = _clean_str(data.get("title"))
    raw_is_oa = data.get("is_oa")
    is_oa = raw_is_oa if isinstance(raw_is_oa, bool) else None
    oa_status = _clean_str(data.get("oa_status"))
    journal_name = _clean_str(data.get("journal_name"))
    year = str(data["year"]) if data.get("year") is not None else None
    updated = _clean_str(data.get("updated"))

    oa_locations = data.get("oa_locations")
    oa_locations_count = len(oa_locations) if isinstance(oa_locations, list) else 0

    best_oa = data.get("best_oa_location")
    best_oa_location = None
    if isinstance(best_oa, dict):
        best_oa_location = {
            "url": _clean_str(best_oa.get("url")),
            "url_for_pdf": _clean_str(best_oa.get("url_for_pdf")),
            "license": _clean_str(best_oa.get("license")),
            "version": _clean_str(best_oa.get("version")),
            "host_type": _clean_str(best_oa.get("host_type")),
            "repository_institution": _clean_str(best_oa.get("repository_institution")),
        }

    fields = {
        "doi": doi,
        "title": title,
        "is_oa": is_oa,
        "oa_status": oa_status,
        "best_oa_location": best_oa_location,
        "oa_locations_count": oa_locations_count,
        "journal_name": journal_name,
        "year": year,
        "updated": updated,
    }

    excerpt = None
    if best_oa_location and best_oa_location.get("url"):
        excerpt = f"Open Access ({oa_status or 'unknown'}): {best_oa_location['url']}"
    elif oa_status:
        excerpt = f"Open Access status: {oa_status}"

    rec = Evidence(
        status=Status.FOUND,
        question=question,
        source_id=SOURCE,
        url=safe_url,
        provider=PROVIDER,
        publisher_date=year,
        fields=fields,
        excerpt=excerpt,
        limitations=LIMITATION,
    )
    guardrails.validate_evidence_record(rec)
    return rec


def lookup(client: Client, doi: str, contact: str | None = None) -> Evidence:
    """Look up open-access metadata for a DOI in Unpaywall."""
    if guardrails.is_blank_query(doi):
        raise ValueError("DOI cannot be blank or whitespace-only")
    clean_doi = doi.strip()
    if ".." in clean_doi:
        raise ValueError("DOI cannot contain path traversal segments")
    question = f"What open-access locations and license metadata does Unpaywall index for DOI {clean_doi}?"

    email = contact or client.contact or os.environ.get("EVIDENCE_CONTACT")
    if not email and not client.dry_run:
        return Evidence(
            status=Status.ERROR,
            question=question,
            source_id=SOURCE,
            url=f"https://api.unpaywall.org/v2/{clean_doi}",
            provider=PROVIDER,
            fields={"doi": clean_doi, "error": "EVIDENCE_CONTACT not set; configure EVIDENCE_CONTACT in .env to query Unpaywall"},
            limitations="Unpaywall API requires a contact email address for queries. Set EVIDENCE_CONTACT in .env.",
        )

    # In dry-run mode, provide synthetic address so URL planning succeeds without opening sockets
    if client.dry_run and not email:
        email = "dry-run@example.org"

    path = quote(clean_doi, safe="/")
    params = {"email": email}
    f = client.get(SOURCE, path, params=params)
    safe_url = redact_url(f.url)

    if f.status is Status.NOT_FOUND:
        return Evidence(
            status=Status.NOT_FOUND,
            question=question,
            source_id=SOURCE,
            url=safe_url,
            provider=PROVIDER,
            fields={"doi": clean_doi, "http_status": f.http_status},
            limitations="Paper not found in Unpaywall database.",
        )
    if f.status is not Status.FOUND:
        return Evidence(
            status=f.status,
            question=question,
            source_id=SOURCE,
            url=safe_url,
            provider=PROVIDER,
            fields={"doi": clean_doi, "http_status": f.http_status},
            limitations="Unpaywall query did not return data; establishes nothing about open access availability.",
        )

    try:
        return parse_unpaywall(f.data, clean_doi, question, safe_url)
    except ShapeError as exc:
        return error_record(
            exc,
            question=question,
            source_id=SOURCE,
            url=safe_url,
            provider=PROVIDER,
            fields={"doi": clean_doi},
        )
