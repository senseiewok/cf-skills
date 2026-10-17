"""Semantic Scholar Academic Graph API provider.

Queries https://api.semanticscholar.org/graph/v1/paper/DOI:<doi> for paper metadata,
citation graphs, influential citation counts, and open-access links.
Under lab conduct rules:
- EVIDENCE_CONTACT is used for Unpaywall ONLY; never sent to Semantic Scholar.
- No API key is required or committed. Optional S2_API_KEY read from environment if present.
- Citation metrics are graph indices; do not establish clinical validity or replication.
"""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import quote

from .. import guardrails
from ..http import PROJECT_UA, Client, Fetch
from ..record import Evidence, Status
from ..shape import ShapeError, count, error_record, need

PROVIDER = "semantic_scholar/0.1"
SOURCE = "semantic-scholar"

LIMITATION = (
    "Semantic Scholar Academic Graph record. Citation counts, influential citation metrics, and "
    "graph connections are bibliographic graph indicators from automated citation indexing. "
    "They do not establish clinical validity, methodological replication, or therapeutic efficacy."
)

S2_FIELDS = (
    "paperId,title,year,venue,isOpenAccess,openAccessPdf,"
    "citationCount,influentialCitationCount,referenceCount,"
    "citations.paperId,citations.title,citations.year,"
    "references.paperId,references.title,references.year"
)


def _clean_str(val: Any) -> str | None:
    """Return string value, converting prohibited stringified nulls to None."""
    if val is None:
        return None
    s = str(val).strip()
    if s.lower() in guardrails.PROHIBITED_NULL_STRINGS:
        return None
    return s


def parse_paper(data: Any, doi_query: str, question: str, url: str) -> Evidence:
    """Parse Semantic Scholar paper response into a validated Evidence record."""
    if not isinstance(data, dict):
        raise ShapeError(f"Semantic Scholar response is {type(data).__name__}, not an object")

    # 404 / not found response vs API error response
    err_text = f"{data.get('error', '')} {data.get('message', '')}".lower()
    if "not found" in err_text:
        return Evidence(
            status=Status.NOT_FOUND,
            question=question,
            source_id=SOURCE,
            url=url,
            provider=PROVIDER,
            fields={"doi": doi_query},
            limitations="Paper not found in Semantic Scholar Academic Graph.",
        )
    if "error" in data:
        return error_record(
            ShapeError(f"Semantic Scholar error response: {data.get('error')}"),
            question=question,
            source_id=SOURCE,
            url=url,
            provider=PROVIDER,
            fields={"doi": doi_query},
        )

    try:
        paper_id = need(data, "paperId", "Semantic Scholar response")
        if not isinstance(paper_id, str):
            raise ShapeError(f"Semantic Scholar response paperId is {type(paper_id).__name__}, not a string")
    except ShapeError as exc:
        return error_record(
            exc,
            question=question,
            source_id=SOURCE,
            url=url,
            provider=PROVIDER,
            fields={"doi": doi_query},
        )

    title = _clean_str(data.get("title"))
    year = str(data["year"]) if data.get("year") is not None else None
    venue = _clean_str(data.get("venue"))
    raw_is_oa = data.get("isOpenAccess")
    is_oa = raw_is_oa if isinstance(raw_is_oa, bool) else None

    oa_pdf = None
    if isinstance(data.get("openAccessPdf"), dict):
        oa_pdf = {
            "url": _clean_str(data["openAccessPdf"].get("url")),
            "status": _clean_str(data["openAccessPdf"].get("status")),
        }

    citation_count = count(data["citationCount"], "Semantic Scholar citationCount") if data.get("citationCount") is not None else None
    influential_count = count(data["influentialCitationCount"], "Semantic Scholar influentialCitationCount") if data.get("influentialCitationCount") is not None else None
    reference_count = count(data["referenceCount"], "Semantic Scholar referenceCount") if data.get("referenceCount") is not None else None

    citations = data.get("citations") or []
    sample_citations: list[dict[str, Any]] = []
    if isinstance(citations, list):
        for c in citations[:5]:
            if isinstance(c, dict):
                sample_citations.append({
                    "paper_id": _clean_str(c.get("paperId")),
                    "title": _clean_str(c.get("title")),
                    "year": str(c["year"]) if c.get("year") is not None else None,
                })

    references = data.get("references") or []
    sample_references: list[dict[str, Any]] = []
    if isinstance(references, list):
        for r in references[:5]:
            if isinstance(r, dict):
                sample_references.append({
                    "paper_id": _clean_str(r.get("paperId")),
                    "title": _clean_str(r.get("title")),
                    "year": str(r["year"]) if r.get("year") is not None else None,
                })

    citation_graph_summary = {
        "citation_count": citation_count,
        "influential_citation_count": influential_count,
        "reference_count": reference_count,
        "sample_citing_papers": sample_citations,
        "sample_references": sample_references,
    }

    fields = {
        "paper_id": paper_id,
        "doi": doi_query,
        "title": title,
        "year": year,
        "venue": venue,
        "is_open_access": is_oa,
        "open_access_pdf": oa_pdf,
        "citation_graph_summary": citation_graph_summary,
    }

    c_disp = citation_count if citation_count is not None else "not stated"
    i_disp = influential_count if influential_count is not None else "not stated"
    r_disp = reference_count if reference_count is not None else "not stated"
    excerpt = f"Computed summary: Citations: {c_disp} (influential: {i_disp}), References: {r_disp}"

    rec = Evidence(
        status=Status.FOUND,
        question=question,
        source_id=SOURCE,
        url=url,
        provider=PROVIDER,
        publisher_date=year,
        fields=fields,
        excerpt=excerpt,
        limitations=LIMITATION,
    )
    guardrails.validate_evidence_record(rec)
    return rec


def paper(client: Client, doi: str) -> Evidence:
    """Look up paper metadata and citation graph for a DOI in Semantic Scholar."""
    if guardrails.is_blank_query(doi):
        raise ValueError("DOI cannot be blank or whitespace-only")
    clean_doi = doi.strip()
    if ".." in clean_doi:
        raise ValueError("DOI cannot contain path traversal segments")
    question = f"What does Semantic Scholar hold for DOI {clean_doi} (citation graph, open access)?"

    path = f"paper/DOI:{quote(clean_doi, safe='/')}"
    params = {"fields": S2_FIELDS}

    # Strict privacy: EVIDENCE_CONTACT is never sent to Semantic Scholar.
    # Override User-Agent to ensure no mailto: is present.
    headers = {"User-Agent": PROJECT_UA}
    api_key = os.environ.get("S2_API_KEY")
    if api_key and api_key.strip():
        headers["x-api-key"] = api_key.strip()

    f = client.get(SOURCE, path, params=params, headers=headers)

    if f.status is Status.NOT_FOUND:
        return Evidence(
            status=Status.NOT_FOUND,
            question=question,
            source_id=SOURCE,
            url=f.url,
            provider=PROVIDER,
            fields={"doi": clean_doi, "http_status": f.http_status},
            limitations="Paper not found in Semantic Scholar Academic Graph.",
        )
    if f.status is not Status.FOUND:
        return Evidence(
            status=f.status,
            question=question,
            source_id=SOURCE,
            url=f.url,
            provider=PROVIDER,
            fields={"doi": clean_doi, "http_status": f.http_status},
            limitations="Semantic Scholar query did not return data; establishes nothing about citations.",
        )

    try:
        return parse_paper(f.data, clean_doi, question, f.url)
    except ShapeError as exc:
        return error_record(
            exc,
            question=question,
            source_id=SOURCE,
            url=f.url,
            provider=PROVIDER,
            fields={"doi": clean_doi},
        )
