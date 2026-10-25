"""UniProt REST API provider for protein sequence, domain topology, and natural variant annotations.

Catalog source: `uniprot-rest` (`https://rest.uniprot.org/`).
Licensed under Creative Commons Attribution 4.0 International (CC BY 4.0) per https://www.uniprot.org/help/license.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

from ..http import Client, Fetch
from ..record import Evidence, Status
from ..shape import ShapeError, count, error_record, need

PROVIDER = "uniprot/0.1"
SOURCE = "uniprot-rest"
DEFAULT_LIMIT = 5
MAX_LIMIT = 10
_ACCESSION_RE = re.compile(r"^[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9]([A-Z][A-Z0-9]{2}[0-9]){1,2}$", re.IGNORECASE)

LIMITATION = (
    "UniProtKB protein sequence, domain boundaries, and natural variant annotations are licensed under CC BY 4.0 "
    "(UniProt Consortium). Variant entries are protein-level sequence annotations for research and educational use only, "
    "not a clinical classification, frequency, severity statement, or substitute for professional medical advice."
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


def _parse_entry_dict(entry: dict[str, Any], question: str, url: str) -> Evidence:
    acc = need(entry, "primaryAccession", "UniProtKB entry")
    if not isinstance(acc, str) or not acc.strip():
        raise ShapeError("UniProtKB 'primaryAccession' is not a non-empty string")
    uniprot_id = entry.get("uniProtkbId")
    seq_obj = entry.get("sequence") if isinstance(entry.get("sequence"), dict) else {}
    seq_len = count(seq_obj.get("length", 0), "UniProtKB sequence.length")

    gene_symbol = None
    genes = entry.get("genes")
    if isinstance(genes, list) and genes and isinstance(genes[0], dict):
        gname = genes[0].get("geneName")
        if isinstance(gname, dict):
            gene_symbol = gname.get("value")

    protein_name = None
    pdesc = entry.get("proteinDescription")
    if isinstance(pdesc, dict):
        rec_name = pdesc.get("recommendedName")
        if isinstance(rec_name, dict) and isinstance(rec_name.get("fullName"), dict):
            protein_name = rec_name["fullName"].get("value")

    domains: list[dict[str, Any]] = []
    tm_count = 0
    variant_count = 0
    features = entry.get("features")
    if isinstance(features, list):
        for feat in features:
            if not isinstance(feat, dict):
                continue
            ftype = str(feat.get("type") or "")
            if ftype == "Natural variant":
                variant_count += 1
            elif ftype == "Transmembrane":
                tm_count += 1
            elif ftype in ("Domain", "Topological domain", "Region", "Binding site"):
                loc = feat.get("location") if isinstance(feat.get("location"), dict) else {}
                start_obj = loc.get("start") if isinstance(loc.get("start"), dict) else {}
                end_obj = loc.get("end") if isinstance(loc.get("end"), dict) else {}
                if len(domains) < 12:
                    domains.append(
                        {
                            "type": ftype,
                            "description": feat.get("description"),
                            "start": start_obj.get("value"),
                            "end": end_obj.get("value"),
                        }
                    )

    audit = entry.get("entryAudit") if isinstance(entry.get("entryAudit"), dict) else {}
    pub_date = audit.get("lastAnnotationUpdateDate") or audit.get("lastSequenceUpdateDate")

    return Evidence(
        status=Status.FOUND,
        question=question,
        source_id=SOURCE,
        url=f"https://www.uniprot.org/uniprotkb/{acc}",
        provider=PROVIDER,
        publisher_date=str(pub_date) if pub_date else None,
        fields={
            "accession": acc,
            "uniprot_id": uniprot_id,
            "gene_symbol": gene_symbol,
            "protein_name": protein_name,
            "sequence_length": seq_len,
            "transmembrane_segments_counted": tm_count,
            "natural_variants_counted": variant_count,
            "domains": domains,
            "license": "CC BY 4.0",
            "license_attribution": "UniProt Consortium (https://www.uniprot.org/help/license)",
        },
        limitations=LIMITATION,
    )


def parse_entry(data: Any, accession: str, question: str, url: str) -> Evidence:
    """Pure parser for a single UniProtKB JSON record (GET uniprotkb/{accession}.json)."""
    try:
        if not isinstance(data, dict):
            raise ShapeError(f"UniProtKB response is {type(data).__name__}, not an object")
        return _parse_entry_dict(data, question, url)
    except ShapeError as exc:
        return error_record(exc, question=question, source_id=SOURCE, url=url, provider=PROVIDER, fields={"accession": accession})


def parse_search(data: Any, query: str, question: str, url: str, limit: int = DEFAULT_LIMIT) -> list[Evidence]:
    """Pure parser for UniProtKB search JSON response (GET uniprotkb/search)."""
    try:
        if not isinstance(data, dict):
            raise ShapeError(f"UniProtKB search response is {type(data).__name__}, not an object")
        results = need(data, "results", "UniProtKB search response")
        if not isinstance(results, list):
            raise ShapeError(f"UniProtKB 'results' is {type(results).__name__}, not a list")
        if not results:
            return [
                Evidence(
                    status=Status.NOT_FOUND,
                    question=question,
                    source_id=SOURCE,
                    url=url,
                    provider=PROVIDER,
                    fields={"query": query, "results_returned": 0},
                    limitations=LIMITATION,
                )
            ]
        out: list[Evidence] = []
        max_items = max(1, min(limit, MAX_LIMIT))
        for idx, item in enumerate(results[:max_items]):
            if not isinstance(item, dict):
                raise ShapeError(f"UniProtKB results[{idx}] is not an object")
            out.append(_parse_entry_dict(item, question, url))
        return out
    except ShapeError as exc:
        return [error_record(exc, question=question, source_id=SOURCE, url=url, provider=PROVIDER, fields={"query": query})]


def lookup(client: Client, query: str, limit: int = DEFAULT_LIMIT) -> list[Evidence]:
    """Look up a UniProtKB accession (e.g. P13569) or search human UniProtKB entries by gene/protein term."""
    q_str = query.strip()
    max_items = max(1, min(limit, MAX_LIMIT))

    if _ACCESSION_RE.fullmatch(q_str):
        acc = q_str.upper()
        question = f"What is the UniProtKB protein annotation and domain topology record for accession '{acc}'?"
        path = f"uniprotkb/{quote(acc, safe='')}.json"
        if client.dry_run:
            f = client.get(SOURCE, path)
            return [
                Evidence(
                    status=Status.OUT_OF_SCOPE,
                    question=question,
                    source_id=SOURCE,
                    url=f.url,
                    provider=PROVIDER,
                    fields={"accession": acc, "planned_endpoint": path},
                    limitations=LIMITATION,
                )
            ]
        f = client.get(SOURCE, path)
        if f.status is not Status.FOUND:
            return [_fail(f, question, {"accession": acc})]
        return [parse_entry(f.data, acc, question, f.url)]

    question = f"Which human UniProtKB entries match '{q_str}'?"
    params = {"query": f"({q_str}) AND (organism_id:9606)", "size": max_items, "format": "json"}
    if client.dry_run:
        f = client.get(SOURCE, "uniprotkb/search", params=params)
        return [
            Evidence(
                status=Status.OUT_OF_SCOPE,
                question=question,
                source_id=SOURCE,
                url=f.url,
                provider=PROVIDER,
                fields={"query": q_str, "planned_endpoint": "uniprotkb/search"},
                limitations=LIMITATION,
            )
        ]
    f = client.get(SOURCE, "uniprotkb/search", params=params)
    if f.status is not Status.FOUND:
        return [_fail(f, question, {"query": q_str})]
    return parse_search(f.data, q_str, question, f.url, limit=max_items)
