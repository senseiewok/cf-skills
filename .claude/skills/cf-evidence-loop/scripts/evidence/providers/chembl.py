"""EMBL-EBI ChEMBL API provider: bioactive molecules, clinical development phases, and quantitative assays.

Queries https://www.ebi.ac.uk/chembl/api/data/ for small-molecule metadata, ATC classifications,
molecular properties, and quantitative bioactivity assays (EC50, IC50, Ki, Kd, pChEMBL) on targets
such as CFTR (CHEMBL4051). Uses polite Client with source="chembl" under CC BY-SA 3.0.
"""

from __future__ import annotations

import re
from typing import Any

from ..http import Client, Fetch
from ..record import Evidence, Status
from ..shape import ShapeError, count, error_record, need

PROVIDER = "chembl/0.1"
SOURCE = "chembl"
CFTR_CHEMBL_ID = "CHEMBL4051"
DEFAULT_LIMIT = 5
DEFAULT_ACTIVITY_LIMIT = 10
MAX_LIMIT = 50
EXCERPT_CHARS = 700
CHEMBL_ID_PATTERN = re.compile(r"^CHEMBL[0-9]+$", re.IGNORECASE)

CC_BY_SA_LICENSE = "CC BY-SA 3.0"
CC_BY_SA_ATTRIBUTION = (
    "Contains EMBL-EBI ChEMBL data licensed under Creative Commons Attribution-ShareAlike 3.0 Unported (CC BY-SA 3.0)"
)

LIMITATION = (
    f"{CC_BY_SA_ATTRIBUTION}. "
    "ChEMBL compound properties, clinical development phases, and experimental bioactivity measurements "
    "(EC50, IC50, Ki, Kd, pChEMBL) are literature-extracted and deposited assay records. Assay values "
    "depend on cell system, genotype, and experimental protocol, and do not establish clinical efficacy, "
    "safety, dosing, or regulatory approval for any individual patient."
)


def _parse_single_molecule(m: dict[str, Any], question: str, url: str, total: int | None = None) -> Evidence:
    chembl_id = m.get("molecule_chembl_id")
    pref_name = m.get("pref_name")
    mol_type = m.get("molecule_type")
    max_phase = m.get("max_phase")
    first_approval = m.get("first_approval")
    black_box = bool(m.get("black_box_warning"))
    withdrawn = bool(m.get("withdrawn_flag"))
    oral = bool(m.get("oral"))

    props = m.get("molecule_properties") if isinstance(m.get("molecule_properties"), dict) else {}
    structs = m.get("molecule_structures") if isinstance(m.get("molecule_structures"), dict) else {}
    atc_raw = m.get("atc_classifications")
    atc_codes = [str(c) for c in atc_raw if c] if isinstance(atc_raw, list) else []

    synonyms: list[str] = []
    syn_raw = m.get("molecule_synonyms")
    if isinstance(syn_raw, list):
        seen: set[str] = set()
        for item in syn_raw:
            if isinstance(item, dict):
                s = (item.get("molecule_synonym") or item.get("synonyms") or "").strip()
                if s and s.lower() not in seen:
                    seen.add(s.lower())
                    synonyms.append(s)
                    if len(synonyms) >= 8:
                        break

    pub_date = str(first_approval) if first_approval else None
    fields: dict[str, Any] = {
        "molecule_chembl_id": chembl_id,
        "pref_name": pref_name,
        "molecule_type": mol_type,
        "max_phase": max_phase,
        "first_approval": first_approval,
        "oral": oral,
        "black_box_warning": black_box,
        "withdrawn_flag": withdrawn,
        "atc_classifications": atc_codes,
        "full_molformula": props.get("full_molformula"),
        "full_mwt": props.get("full_mwt"),
        "alogp": props.get("alogp"),
        "psa": props.get("psa"),
        "ro3_pass": props.get("ro3_pass"),
        "num_ro5_violations": props.get("num_ro5_violations"),
        "canonical_smiles": structs.get("canonical_smiles"),
        "standard_inchi_key": structs.get("standard_inchi_key"),
        "synonyms": synonyms,
        "license": CC_BY_SA_LICENSE,
        "license_attribution": CC_BY_SA_ATTRIBUTION,
    }
    if total is not None:
        fields["search_total"] = total

    mol_url = (
        f"https://www.ebi.ac.uk/chembl/compound_report_card/{chembl_id}/"
        if chembl_id
        else url
    )

    return Evidence(
        status=Status.FOUND,
        question=question,
        source_id=SOURCE,
        url=mol_url,
        provider=PROVIDER,
        publisher_date=pub_date,
        fields=fields,
        limitations=LIMITATION,
    )


def parse_molecule(data: Any, question: str, url: str) -> Evidence:
    """Pure parsing of a single ChEMBL molecule response with strict shape verification."""
    if not isinstance(data, dict):
        exc = ShapeError(f"ChEMBL molecule response is {type(data).__name__}, not an object")
        return error_record(exc, question=question, source_id=SOURCE, url=url, provider=PROVIDER)

    try:
        chembl_id = need(data, "molecule_chembl_id", "ChEMBL molecule")
        if not chembl_id or not isinstance(chembl_id, str):
            raise ShapeError("ChEMBL molecule 'molecule_chembl_id' is empty or not a string")
    except ShapeError as exc:
        return error_record(exc, question=question, source_id=SOURCE, url=url, provider=PROVIDER)

    return _parse_single_molecule(data, question, url)


def parse_molecules(data: Any, question: str, url: str, limit: int | None = None) -> list[Evidence]:
    """Pure parsing of a ChEMBL molecule search response with strict shape verification."""
    if not isinstance(data, dict):
        exc = ShapeError(f"ChEMBL molecule search response is {type(data).__name__}, not an object")
        return [error_record(exc, question=question, source_id=SOURCE, url=url, provider=PROVIDER)]

    try:
        mol_list = need(data, "molecules", "ChEMBL molecule search")
        if not isinstance(mol_list, list):
            raise ShapeError(f"ChEMBL molecule search 'molecules' is {type(mol_list).__name__}, not a list")
        page_meta = data.get("page_meta")
        if page_meta is not None and isinstance(page_meta, dict) and "total_count" in page_meta:
            total = count(page_meta["total_count"], "ChEMBL molecule search page_meta.total_count")
        else:
            total = len(mol_list)
    except ShapeError as exc:
        return [error_record(exc, question=question, source_id=SOURCE, url=url, provider=PROVIDER)]

    if total == 0 or len(mol_list) == 0:
        return [
            Evidence(
                status=Status.NOT_FOUND,
                question=question,
                source_id=SOURCE,
                url=url,
                provider=PROVIDER,
                fields={
                    "search_total": total,
                    "license": CC_BY_SA_LICENSE,
                    "license_attribution": CC_BY_SA_ATTRIBUTION,
                },
                limitations=LIMITATION,
            )
        ]

    if limit is not None and limit > 0:
        mol_list = mol_list[:limit]

    out: list[Evidence] = []
    for idx, m in enumerate(mol_list):
        if not isinstance(m, dict):
            exc = ShapeError(f"ChEMBL molecule item {idx} is {type(m).__name__}, not an object")
            return [error_record(exc, question=question, source_id=SOURCE, url=url, provider=PROVIDER)]
        try:
            need(m, "molecule_chembl_id", f"ChEMBL molecule item {idx}")
        except ShapeError as exc:
            return [error_record(exc, question=question, source_id=SOURCE, url=url, provider=PROVIDER)]
        out.append(_parse_single_molecule(m, question, url, total=total))

    return out


def parse_activities(data: Any, question: str, url: str, limit: int | None = None) -> list[Evidence]:
    """Pure parsing of a ChEMBL activity response with strict shape verification."""
    if not isinstance(data, dict):
        exc = ShapeError(f"ChEMBL activity response is {type(data).__name__}, not an object")
        return [error_record(exc, question=question, source_id=SOURCE, url=url, provider=PROVIDER)]

    try:
        act_list = need(data, "activities", "ChEMBL activity search")
        if not isinstance(act_list, list):
            raise ShapeError(f"ChEMBL activity search 'activities' is {type(act_list).__name__}, not a list")
        page_meta = data.get("page_meta")
        if page_meta is not None and isinstance(page_meta, dict) and "total_count" in page_meta:
            total = count(page_meta["total_count"], "ChEMBL activity search page_meta.total_count")
        else:
            total = len(act_list)
    except ShapeError as exc:
        return [error_record(exc, question=question, source_id=SOURCE, url=url, provider=PROVIDER)]

    if total == 0 or len(act_list) == 0:
        return [
            Evidence(
                status=Status.NOT_FOUND,
                question=question,
                source_id=SOURCE,
                url=url,
                provider=PROVIDER,
                fields={
                    "search_total": total,
                    "license": CC_BY_SA_LICENSE,
                    "license_attribution": CC_BY_SA_ATTRIBUTION,
                },
                limitations=LIMITATION,
            )
        ]

    if limit is not None and limit > 0:
        act_list = act_list[:limit]

    out: list[Evidence] = []
    for idx, act in enumerate(act_list):
        if not isinstance(act, dict):
            exc = ShapeError(f"ChEMBL activity item {idx} is {type(act).__name__}, not an object")
            return [error_record(exc, question=question, source_id=SOURCE, url=url, provider=PROVIDER)]
        try:
            need(act, "activity_id", f"ChEMBL activity item {idx}")
        except ShapeError as exc:
            return [error_record(exc, question=question, source_id=SOURCE, url=url, provider=PROVIDER)]

        doc_year = act.get("document_year")
        pub_date = str(doc_year) if doc_year else None
        desc = (act.get("assay_description") or "").strip()
        excerpt = (desc[:EXCERPT_CHARS] + ("…" if len(desc) > EXCERPT_CHARS else "")) if desc else None

        fields: dict[str, Any] = {
            "activity_id": act.get("activity_id"),
            "molecule_chembl_id": act.get("molecule_chembl_id"),
            "molecule_pref_name": act.get("molecule_pref_name"),
            "target_chembl_id": act.get("target_chembl_id"),
            "target_pref_name": act.get("target_pref_name"),
            "target_organism": act.get("target_organism"),
            "assay_chembl_id": act.get("assay_chembl_id"),
            "assay_type": act.get("assay_type"),
            "assay_variant_accession": act.get("assay_variant_accession"),
            "assay_variant_mutation": act.get("assay_variant_mutation"),
            "standard_type": act.get("standard_type"),
            "standard_relation": act.get("standard_relation"),
            "standard_value": act.get("standard_value"),
            "standard_units": act.get("standard_units"),
            "pchembl_value": act.get("pchembl_value"),
            "document_chembl_id": act.get("document_chembl_id"),
            "document_journal": act.get("document_journal"),
            "document_year": doc_year,
            "search_total": total,
            "license": CC_BY_SA_LICENSE,
            "license_attribution": CC_BY_SA_ATTRIBUTION,
        }

        out.append(
            Evidence(
                status=Status.FOUND,
                question=question,
                source_id=SOURCE,
                url=url,
                provider=PROVIDER,
                publisher_date=pub_date,
                fields=fields,
                excerpt=excerpt,
                limitations=LIMITATION,
            )
        )

    return out


def _fail(f: Fetch, question: str) -> Evidence:
    return Evidence(
        status=f.status,
        question=question,
        source_id=SOURCE,
        url=f.url,
        provider=PROVIDER,
        fields={"http_status": f.http_status, "license": CC_BY_SA_LICENSE},
        limitations=LIMITATION,
    )


def molecule(client: Client, query: str, limit: int = DEFAULT_LIMIT) -> list[Evidence]:
    """Look up a ChEMBL molecule by ChEMBL ID or search by name/synonym."""
    stripped = query.strip()
    max_items = max(1, min(limit, MAX_LIMIT))

    if CHEMBL_ID_PATTERN.match(stripped):
        chembl_id = stripped.upper()
        q = f"What is the ChEMBL molecule record for '{chembl_id}'?"
        f = client.get(SOURCE, f"molecule/{chembl_id}.json")
        if f.dry_run:
            return [
                Evidence(
                    status=Status.OUT_OF_SCOPE,
                    question=q,
                    source_id=SOURCE,
                    url=f.url,
                    provider=PROVIDER,
                    fields={"molecule_chembl_id": chembl_id, "license": CC_BY_SA_LICENSE},
                    limitations=LIMITATION,
                )
            ]
        if f.status is Status.NOT_FOUND:
            return [
                Evidence(
                    status=Status.NOT_FOUND,
                    question=q,
                    source_id=SOURCE,
                    url=f.url,
                    provider=PROVIDER,
                    fields={"molecule_chembl_id": chembl_id, "license": CC_BY_SA_LICENSE},
                    limitations=LIMITATION,
                )
            ]
        if f.status is not Status.FOUND:
            return [_fail(f, q)]
        return [parse_molecule(f.data, q, f.url)]

    q = f"Which ChEMBL molecules match '{stripped}'?"
    f = client.get(SOURCE, "molecule/search.json", params={"q": stripped, "limit": max_items})
    if f.dry_run:
        return [
            Evidence(
                status=Status.OUT_OF_SCOPE,
                question=q,
                source_id=SOURCE,
                url=f.url,
                provider=PROVIDER,
                fields={"planned_query": stripped, "license": CC_BY_SA_LICENSE},
                limitations=LIMITATION,
            )
        ]
    if f.status is Status.NOT_FOUND:
        return [
            Evidence(
                status=Status.NOT_FOUND,
                question=q,
                source_id=SOURCE,
                url=f.url,
                provider=PROVIDER,
                fields={"query": stripped, "search_total": 0, "license": CC_BY_SA_LICENSE},
                limitations=LIMITATION,
            )
        ]
    if f.status is not Status.FOUND:
        return [_fail(f, q)]
    return parse_molecules(f.data, q, f.url, limit=max_items)


def activities(
    client: Client,
    query: str,
    target_id: str | None = CFTR_CHEMBL_ID,
    limit: int = DEFAULT_ACTIVITY_LIMIT,
) -> list[Evidence]:
    """Query ChEMBL quantitative bioactivity assays (EC50, IC50, Ki, Kd) for a molecule and optional target."""
    stripped = query.strip()
    max_items = max(1, min(limit, MAX_LIMIT))
    norm_target = target_id.strip().upper() if target_id and target_id.strip().lower() not in ("all", "*", "none") else None

    target_clause = f" on target {norm_target}" if norm_target else ""
    q = f"What ChEMBL bioactivity assays (EC50, IC50, Ki, Kd) match '{stripped}'{target_clause}?"

    params: dict[str, Any] = {
        "standard_type__in": "EC50,IC50,Ki,Kd",
        "limit": max_items,
    }
    if CHEMBL_ID_PATTERN.match(stripped):
        params["molecule_chembl_id"] = stripped.upper()
    else:
        params["molecule_pref_name__iexact"] = stripped
    if norm_target:
        params["target_chembl_id"] = norm_target

    f = client.get(SOURCE, "activity.json", params=params)
    if f.dry_run:
        return [
            Evidence(
                status=Status.OUT_OF_SCOPE,
                question=q,
                source_id=SOURCE,
                url=f.url,
                provider=PROVIDER,
                fields={"planned_query": stripped, "target_chembl_id": norm_target, "license": CC_BY_SA_LICENSE},
                limitations=LIMITATION,
            )
        ]
    if f.status is Status.NOT_FOUND:
        return [
            Evidence(
                status=Status.NOT_FOUND,
                question=q,
                source_id=SOURCE,
                url=f.url,
                provider=PROVIDER,
                fields={"query": stripped, "target_chembl_id": norm_target, "search_total": 0, "license": CC_BY_SA_LICENSE},
                limitations=LIMITATION,
            )
        ]
    if f.status is not Status.FOUND:
        return [_fail(f, q)]
    return parse_activities(f.data, q, f.url, limit=max_items)
