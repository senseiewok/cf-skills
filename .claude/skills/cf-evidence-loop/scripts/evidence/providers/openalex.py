"""OpenAlex: literature, citation graphs, institutional affiliations, and retraction surveillance.

Layer 1/2 provider for scientific publications, cross-source citation counts, open-access
availability, and author institutions. Key required per catalog.yaml (auth: api_key_required).
"""

from __future__ import annotations

import os

from ..http import Client
from ..record import Evidence, Status

PROVIDER = "openalex/0.1"
SOURCE = "openalex"

LIMITATION = (
    "OpenAlex index record. Metrics (cited_by_count) and open-access status reflect OpenAlex's "
    "aggregation across Crossref, PubMed Central, institutional repositories, and publisher metadata. "
    "is_retracted reflects retraction notices ingested into OpenAlex. Bibliographic and bibliometric index only; "
    "does not evaluate clinical safety or therapeutic efficacy."
)


def parse_work(data: dict, question: str, url: str) -> Evidence:
    if not data or not isinstance(data, dict):
        return Evidence(
            status=Status.NOT_FOUND,
            question=question,
            source_id=SOURCE,
            url=url,
            provider=PROVIDER,
            fields={},
            limitations="No work record found in OpenAlex response.",
        )

    work_id = data.get("id")
    doi = data.get("doi")
    title = data.get("title") or data.get("display_name")
    if not work_id and not doi and not title:
        return Evidence(
            status=Status.NOT_FOUND,
            question=question,
            source_id=SOURCE,
            url=url,
            provider=PROVIDER,
            fields={},
            limitations="Empty or unrecognized work record in OpenAlex.",
        )

    pub_year = data.get("publication_year")
    pub_date = data.get("publication_date")
    cited_by = data.get("cited_by_count", 0)
    is_retracted = bool(data.get("is_retracted", False))
    doc_type = data.get("type")

    # Primary location and venue
    prim_loc = data.get("primary_location") or {}
    src = prim_loc.get("source") or {}
    venue = src.get("display_name")
    issn = src.get("issn_l")

    # Open access
    oa = data.get("open_access") or {}
    is_oa = bool(oa.get("is_oa", False))
    oa_status = oa.get("oa_status")
    oa_url = oa.get("oa_url") or prim_loc.get("pdf_url")

    # Authors and institutions
    authorships = data.get("authorships") or []
    first_author = authorships[0].get("author", {}).get("display_name") if authorships else None
    last_author = authorships[-1].get("author", {}).get("display_name") if len(authorships) > 1 else None
    author_count = len(authorships)

    seen_inst = set()
    institutions: list[str] = []
    for a in authorships:
        for inst in a.get("institutions") or []:
            name = inst.get("display_name")
            if name and name not in seen_inst:
                seen_inst.add(name)
                institutions.append(name)
                if len(institutions) >= 5:
                    break
        if len(institutions) >= 5:
            break

    # MeSH terms & high-level concepts
    mesh_terms = [
        m.get("descriptor_name")
        for m in (data.get("mesh") or [])
        if m.get("descriptor_name")
    ][:5]
    concepts = [
        c.get("display_name")
        for c in (data.get("concepts") or [])
        if c.get("display_name")
    ][:5]
    grants = [
        g.get("funder_display_name")
        for g in (data.get("grants") or [])
        if g.get("funder_display_name")
    ][:5]

    return Evidence(
        status=Status.FOUND,
        question=question,
        source_id=SOURCE,
        url=url,
        provider=PROVIDER,
        publisher_date=pub_date or (str(pub_year) if pub_year else None),
        fields={
            "id": work_id,
            "doi": doi,
            "title": title,
            "year": pub_year,
            "publication_date": pub_date,
            "type": doc_type,
            "venue": venue,
            "issn": issn,
            "cited_by": cited_by,
            "is_retracted": is_retracted,
            "is_oa": is_oa,
            "oa_status": oa_status,
            "oa_url": oa_url,
            "first_author": first_author,
            "last_author": last_author,
            "author_count": author_count,
            "institutions": institutions,
            "mesh_terms": mesh_terms,
            "concepts": concepts,
            "grants": grants,
        },
        limitations=LIMITATION,
    )


def parse_search(data: dict, question: str, url: str) -> list[Evidence]:
    results = (data or {}).get("results") or []
    return [parse_work(r, question, url) for r in results]


def _format_target_path(target: str) -> str:
    target = target.strip()
    if target.startswith("10."):
        return f"works/https://doi.org/{target}"
    elif target.startswith("http"):
        return f"works/{target}"
    elif target.startswith("W") and target[1:].isdigit():
        return f"works/{target}"
    elif "/" in target:
        return f"works/https://doi.org/{target}"
    return f"works/{target}"


def work(client: Client, target: str) -> Evidence:
    path = _format_target_path(target)
    q = f"What does OpenAlex hold for {target}?"
    key = os.environ.get("OPENALEX_API_KEY")
    if not key or key == "your_key_here":
        return Evidence(
            status=Status.BLOCKED,
            question=q,
            source_id=SOURCE,
            url=client._url(SOURCE, path),
            provider=PROVIDER,
            fields={"error": "OPENALEX_API_KEY is not set in environment or .env"},
            limitations="API key required for OpenAlex API per catalog.yaml. Add OPENALEX_API_KEY to .env.",
        )

    headers = {"api-key": key}
    f = client.get(SOURCE, path, headers=headers)
    if f.status is not Status.FOUND:
        return Evidence(
            status=f.status,
            question=q,
            source_id=SOURCE,
            url=f.url,
            provider=PROVIDER,
            fields={"http_status": f.http_status, "target": target},
            limitations="OpenAlex API request failed; establishes nothing.",
        )
    return parse_work(f.data or {}, q, f.url)


def search(client: Client, query: str, limit: int = 10) -> list[Evidence]:
    q = f"Which OpenAlex works match '{query}'?"
    key = os.environ.get("OPENALEX_API_KEY")
    if not key or key == "your_key_here":
        return [
            Evidence(
                status=Status.BLOCKED,
                question=q,
                source_id=SOURCE,
                url=client._url(SOURCE, "works"),
                provider=PROVIDER,
                fields={"error": "OPENALEX_API_KEY is not set in environment or .env"},
                limitations="API key required for OpenAlex API per catalog.yaml. Add OPENALEX_API_KEY to .env.",
            )
        ]

    params = {"search": query, "per_page": min(limit, 50)}
    headers = {"api-key": key}
    f = client.get(SOURCE, "works", params=params, headers=headers)
    if f.status is not Status.FOUND:
        return [
            Evidence(
                status=f.status,
                question=q,
                source_id=SOURCE,
                url=f.url,
                provider=PROVIDER,
                fields={"http_status": f.http_status, "query": query},
                limitations="OpenAlex search failed; establishes nothing.",
            )
        ]

    recs = parse_search(f.data, q, f.url)
    total = (f.data or {}).get("meta", {}).get("count")
    for r in recs:
        r.fields["search_total"] = total
    return recs or [
        Evidence(
            status=Status.NOT_FOUND,
            question=q,
            source_id=SOURCE,
            url=f.url,
            provider=PROVIDER,
            fields={"query": query, "search_total": total},
            limitations="No works matched the query in OpenAlex.",
        )
    ]
