"""Ensembl REST API provider for genomic coordinates, canonical transcripts, and variant consequences.

Catalog source: `ensembl-rest` (`https://rest.ensembl.org/`).
Uses Ensembl REST endpoints that return JSON objects (`variation/human/{rsid}`, `lookup/id/{id}`,
and `lookup/symbol/homo_sapiens/{symbol}`).
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

from ..http import Client, Fetch
from ..record import Evidence, Status
from ..shape import ShapeError, count, error_record, need

PROVIDER = "ensembl/0.1"
SOURCE = "ensembl-rest"
_ENSEMBL_ID_RE = re.compile(r"^ENS[GTPE]\d{11}(?:\.\d+)?$", re.IGNORECASE)
_VARIATION_ID_RE = re.compile(r"^(?:rs\d+|COS[MV]\d+|CM\d+|CD\d+)$", re.IGNORECASE)

LIMITATION = (
    "Ensembl REST API genomic coordinates, canonical transcript mappings, and variant consequence terms "
    "(EMBL-EBI, Apache 2.0 / CC BY 4.0) are reference genome annotations (GRCh38), not clinical diagnoses "
    "or statements of therapeutic eligibility for any person."
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


def parse_variation(data: Any, query: str, question: str, url: str) -> Evidence:
    """Pure parser for Ensembl GET variation/human/{id} response."""
    try:
        if not isinstance(data, dict):
            raise ShapeError(f"Ensembl variation response is {type(data).__name__}, not an object")
        if "error" in data and not data.get("name"):
            raise ShapeError(f"Ensembl variation error: {data['error']}")
        name = need(data, "name", "Ensembl variation response")
        if not isinstance(name, str) or not name.strip():
            raise ShapeError("Ensembl variation 'name' is not a non-empty string")

        mappings_raw = data.get("mappings")
        mappings: list[dict[str, Any]] = []
        if isinstance(mappings_raw, list):
            for m in mappings_raw[:5]:
                if isinstance(m, dict):
                    mappings.append(
                        {
                            "location": m.get("location"),
                            "allele_string": m.get("allele_string"),
                            "assembly_name": m.get("assembly_name"),
                            "seq_region_name": m.get("seq_region_name"),
                            "start": m.get("start"),
                            "end": m.get("end"),
                        }
                    )

        clin_sig = data.get("clinical_significance")
        clin_list = [str(x) for x in clin_sig if isinstance(x, str)] if isinstance(clin_sig, list) else []
        syns = data.get("synonyms")
        syn_list = [str(x) for x in syns[:15] if isinstance(x, str)] if isinstance(syns, list) else []

        return Evidence(
            status=Status.FOUND,
            question=question,
            source_id=SOURCE,
            url=url,
            provider=PROVIDER,
            fields={
                "entity": "variation",
                "id": name,
                "most_severe_consequence": data.get("most_severe_consequence"),
                "var_class": data.get("var_class"),
                "clinical_significance": clin_list,
                "mappings": mappings,
                "synonyms": syn_list,
                "license": "CC BY 4.0 / Apache 2.0 (EMBL-EBI Ensembl)",
            },
            limitations=LIMITATION,
        )
    except ShapeError as exc:
        return error_record(exc, question=question, source_id=SOURCE, url=url, provider=PROVIDER, fields={"query": query})


def parse_lookup(data: Any, query: str, question: str, url: str) -> Evidence:
    """Pure parser for Ensembl GET lookup/id/{id} or lookup/symbol/homo_sapiens/{symbol} response."""
    try:
        if not isinstance(data, dict):
            raise ShapeError(f"Ensembl lookup response is {type(data).__name__}, not an object")
        if "error" in data and not data.get("id"):
            raise ShapeError(f"Ensembl lookup error: {data['error']}")
        ens_id = need(data, "id", "Ensembl lookup response")
        if not isinstance(ens_id, str) or not ens_id.strip():
            raise ShapeError("Ensembl lookup 'id' is not a non-empty string")

        start = count(data.get("start", 0), "Ensembl start") if data.get("start") is not None else None
        end = count(data.get("end", 0), "Ensembl end") if data.get("end") is not None else None
        transcripts_raw = data.get("Transcript")
        tx_count = len(transcripts_raw) if isinstance(transcripts_raw, list) else 0

        return Evidence(
            status=Status.FOUND,
            question=question,
            source_id=SOURCE,
            url=url,
            provider=PROVIDER,
            fields={
                "entity": str(data.get("object_type") or "Gene").lower(),
                "id": ens_id,
                "display_name": data.get("display_name"),
                "description": data.get("description"),
                "biotype": data.get("biotype"),
                "assembly_name": data.get("assembly_name"),
                "seq_region_name": data.get("seq_region_name"),
                "start": start,
                "end": end,
                "strand": data.get("strand"),
                "canonical_transcript": data.get("canonical_transcript"),
                "transcripts_counted": tx_count,
                "license": "CC BY 4.0 / Apache 2.0 (EMBL-EBI Ensembl)",
            },
            limitations=LIMITATION,
        )
    except ShapeError as exc:
        return error_record(exc, question=question, source_id=SOURCE, url=url, provider=PROVIDER, fields={"query": query})


def lookup(client: Client, query: str) -> Evidence:
    """Look up a variant (rsID, e.g. rs113993960), Ensembl stable ID (ENSG00000001626), or human gene symbol (CFTR)."""
    q_str = query.strip()

    if _VARIATION_ID_RE.fullmatch(q_str):
        vid = q_str.lower() if q_str.lower().startswith("rs") else q_str
        question = f"What is the Ensembl variation consequence and GRCh38 mapping record for '{vid}'?"
        path = f"variation/human/{quote(vid, safe='')}"
        if client.dry_run:
            f = client.get(SOURCE, path, params={"content-type": "application/json"})
            return Evidence(
                status=Status.OUT_OF_SCOPE,
                question=question,
                source_id=SOURCE,
                url=f.url,
                provider=PROVIDER,
                fields={"query": vid, "planned_endpoint": path},
                limitations=LIMITATION,
            )
        f = client.get(SOURCE, path, params={"content-type": "application/json"})
        if f.status is not Status.FOUND:
            return _fail(f, question, {"query": vid})
        return parse_variation(f.data, vid, question, f.url)

    if _ENSEMBL_ID_RE.fullmatch(q_str):
        eid = q_str.split(".")[0].upper()
        question = f"What is the Ensembl genomic coordinate and canonical transcript record for '{eid}'?"
        path = f"lookup/id/{quote(eid, safe='')}"
    else:
        sym = q_str.upper()
        question = f"What is the Ensembl human gene and canonical transcript record for symbol '{sym}'?"
        path = f"lookup/symbol/homo_sapiens/{quote(sym, safe='')}"

    params = {"expand": "1", "content-type": "application/json"}
    if client.dry_run:
        f = client.get(SOURCE, path, params=params)
        return Evidence(
            status=Status.OUT_OF_SCOPE,
            question=question,
            source_id=SOURCE,
            url=f.url,
            provider=PROVIDER,
            fields={"query": q_str, "planned_endpoint": path},
            limitations=LIMITATION,
        )

    f = client.get(SOURCE, path, params=params)
    if f.status is not Status.FOUND:
        return _fail(f, question, {"query": q_str})
    return parse_lookup(f.data, q_str, question, f.url)
