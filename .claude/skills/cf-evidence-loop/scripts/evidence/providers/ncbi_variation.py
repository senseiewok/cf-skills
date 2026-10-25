"""NCBI Variation Services (SPDI and HGVS contextual allele normalisation) provider.

Catalog source: `ncbi-variation` (`https://api.ncbi.nlm.nih.gov/variation/v0/`).
Resolves HGVS expressions (e.g. `NM_000492.4:c.1521_1523del` or `NC_000007.14:g.117559590_117559592del`)
or SPDI strings (`NC_000007.14:117559589:ATCT:A`) to canonical contextual SPDI alleles at 0 Scite quota cost.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from ..http import Client, Fetch
from ..record import Evidence, Status
from ..shape import ShapeError, count, error_record, need

PROVIDER = "ncbi-variation/0.1"
SOURCE = "ncbi-variation"
MAX_SPDIS = 10

LIMITATION = (
    "NCBI Variation Services normalizes sequence coordinates (SPDI and HGVS contextual alleles) in the public domain. "
    "Coordinate normalization is a technical sequence mapping, not a statement of pathogenicity, clinical significance, "
    "or therapy eligibility for any person."
)


def _fail(f: Fetch, question: str, extra: dict[str, Any]) -> Evidence:
    return Evidence(
        status=f.status,
        question=question,
        source_id=SOURCE,
        url=f.url,
        provider=PROVIDER,
        fields={"http_status": f.http_status, **extra},
        limitations=LIMITATION,
    )


def parse_hgvs(data: Any, query: str, question: str, url: str) -> Evidence:
    """Pure parser for NCBI Variation Services GET hgvs/{hgvs}/contextuals response."""
    try:
        if not isinstance(data, dict):
            raise ShapeError(f"NCBI Variation response is {type(data).__name__}, not an object")
        if "error" in data and isinstance(data["error"], dict):
            msg = data["error"].get("message") or str(data["error"])
            raise ShapeError(f"NCBI Variation API error: {msg}")
        inner = need(data, "data", "NCBI Variation response")
        if not isinstance(inner, dict):
            raise ShapeError(f"NCBI Variation 'data' is {type(inner).__name__}, not an object")
        spdis = need(inner, "spdis", "NCBI Variation data")
        if not isinstance(spdis, list):
            raise ShapeError(f"NCBI Variation 'spdis' is {type(spdis).__name__}, not a list")
        if not spdis:
            return Evidence(
                status=Status.NOT_FOUND,
                question=question,
                source_id=SOURCE,
                url=url,
                provider=PROVIDER,
                fields={"query": query, "spdi_count": 0},
                limitations=LIMITATION,
            )

        parsed_spdis: list[dict[str, Any]] = []
        for idx, item in enumerate(spdis[:MAX_SPDIS]):
            if not isinstance(item, dict):
                raise ShapeError(f"NCBI Variation spdis[{idx}] is not an object")
            seq_id = need(item, "seq_id", f"spdis[{idx}]")
            pos = count(item.get("position", 0), f"spdis[{idx}].position")
            del_seq = str(item.get("deleted_sequence") or "")
            ins_seq = str(item.get("inserted_sequence") or "")
            parsed_spdis.append(
                {
                    "seq_id": str(seq_id),
                    "position": pos,
                    "deleted_sequence": del_seq,
                    "inserted_sequence": ins_seq,
                    "spdi": f"{seq_id}:{pos}:{del_seq}:{ins_seq}",
                }
            )

        primary = parsed_spdis[0]
        return Evidence(
            status=Status.FOUND,
            question=question,
            source_id=SOURCE,
            url=url,
            provider=PROVIDER,
            fields={
                "query": query,
                "canonical_spdi": primary["spdi"],
                "seq_id": primary["seq_id"],
                "position": primary["position"],
                "deleted_sequence": primary["deleted_sequence"],
                "inserted_sequence": primary["inserted_sequence"],
                "spdi_count": len(spdis),
                "contextual_spdis": parsed_spdis,
                "license": "US Public Domain (NCBI)",
            },
            limitations=LIMITATION,
        )
    except ShapeError as exc:
        return error_record(exc, question=question, source_id=SOURCE, url=url, provider=PROVIDER, fields={"query": query})


def normalize(client: Client, hgvs_or_spdi: str) -> Evidence:
    """Resolve an HGVS expression (or SPDI) to contextual SPDI coordinates via NCBI Variation Services."""
    q_str = hgvs_or_spdi.strip()
    question = f"What are the NCBI Variation Services contextual SPDI coordinates for '{q_str}'?"
    path = f"hgvs/{quote(q_str, safe=':')}/contextuals"

    if client.dry_run:
        f = client.get(SOURCE, path)
        return Evidence(
            status=Status.OUT_OF_SCOPE,
            question=question,
            source_id=SOURCE,
            url=f.url,
            provider=PROVIDER,
            fields={"query": q_str, "planned_endpoint": path},
            limitations=LIMITATION,
        )

    f = client.get(SOURCE, path)
    if f.status is not Status.FOUND:
        return _fail(f, question, {"query": q_str})
    return parse_hgvs(f.data, q_str, question, f.url)
