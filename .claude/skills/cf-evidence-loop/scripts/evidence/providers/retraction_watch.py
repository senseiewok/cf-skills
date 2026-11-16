"""Retraction Watch daily data and OpenAlex cross-check surveillance.

Crossref hosts the daily Retraction Watch dataset at gitlab.com/crossref/retraction-watch-data.
This module ingests and caches the dataset, diffs daily updates, cross-checks flagged DOIs
with OpenAlex is_retracted, and audits the cf-research source catalog.
Deterministic execution only: never uses a model's judgement of retraction status.
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from ..http import Client
from ..record import Evidence, Status
from ..shape import ShapeError, need

PROVIDER = "retraction_watch/0.1"
SOURCE = "retraction_watch"

DEFAULT_GITLAB_URL = "https://gitlab.com/crossref/retraction-watch-data/-/raw/main/retraction_watch.csv"
DEFAULT_CACHE_DIR = Path.home() / ".cache" / "cf-evidence-loop" / "retraction_watch"

CRITICAL_NATURES = frozenset({
    "retraction",
    "correction",
    "expression of concern",
    "expression_of_concern",
    "retracted",
    "corrected",
    "reinstatement",
})

LIMITATION = (
    "Retraction Watch daily dataset cross-checked with OpenAlex is_retracted. "
    "Flags reflect publisher and editorial notices ingested by Retraction Watch / Crossref "
    "and OpenAlex. Bibliographic integrity surveillance only; does not evaluate clinical efficacy. "
    "Never uses a model's own judgement of retraction status."
)


def normalize_doi(doi: str | None) -> str:
    """Normalize a DOI to lower case without resolver prefixes or trailing punctuation."""
    if not doi:
        return ""
    s = str(doi).strip()
    s = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", s, flags=re.I)
    s = s.strip()
    # Strip common trailing punctuation
    while s and s[-1] in ".,;:!?*~":
        s = s[:-1]
    return s.lower()


@dataclass
class RetractionRecord:
    record_id: str
    original_paper_doi: str
    original_paper_title: str
    retraction_doi: str
    retraction_nature: str
    reason: str
    original_paper_date: str
    retraction_date: str
    is_retracted: bool
    is_correction: bool
    is_expression_of_concern: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_retraction_watch_csv(
    content_or_file: str | io.TextIOBase,
) -> dict[str, list[RetractionRecord]]:
    """Parse Retraction Watch CSV into an index keyed by normalized original paper DOI."""
    if isinstance(content_or_file, str):
        reader = csv.DictReader(io.StringIO(content_or_file))
    else:
        reader = csv.DictReader(content_or_file)

    index: dict[str, list[RetractionRecord]] = {}
    if not reader.fieldnames:
        return index

    # Normalize header mapping
    header_map = {fn.strip().lower(): fn for fn in reader.fieldnames if fn}

    doi_key = None
    for cand in ("originalpaperdoi", "original_paper_doi", "originaldoi", "doi"):
        if cand in header_map:
            doi_key = header_map[cand]
            break

    id_key = None
    for cand in ("record id", "record_id", "recordid"):
        if cand in header_map:
            id_key = header_map[cand]
            break

    nature_key = None
    for cand in ("retractionnature", "retraction_nature", "nature"):
        if cand in header_map:
            nature_key = header_map[cand]
            break

    title_key = None
    for cand in ("originalpapertitle", "original_paper_title", "title"):
        if cand in header_map:
            title_key = header_map[cand]
            break

    ret_doi_key = None
    for cand in ("retractiondoi", "retraction_doi"):
        if cand in header_map:
            ret_doi_key = header_map[cand]
            break

    reason_key = None
    for cand in ("reason", "reasons"):
        if cand in header_map:
            reason_key = header_map[cand]
            break

    paper_date_key = None
    for cand in ("originalpaperdate", "original_paper_date", "paperdate"):
        if cand in header_map:
            paper_date_key = header_map[cand]
            break

    ret_date_key = None
    for cand in ("retractiondate", "retraction_date"):
        if cand in header_map:
            ret_date_key = header_map[cand]
            break

    if not doi_key:
        return index

    for row in reader:
        raw_doi = row.get(doi_key, "")
        norm_doi = normalize_doi(raw_doi)
        if not norm_doi:
            continue

        nature = str(row.get(nature_key, "") if nature_key else "").strip()
        nature_lower = nature.lower()
        is_ret = "retract" in nature_lower or "withdrawn" in nature_lower
        is_corr = "correct" in nature_lower or "errat" in nature_lower
        is_eoc = "concern" in nature_lower

        record = RetractionRecord(
            record_id=str(row.get(id_key, "") if id_key else "").strip(),
            original_paper_doi=norm_doi,
            original_paper_title=str(row.get(title_key, "") if title_key else "").strip(),
            retraction_doi=normalize_doi(row.get(ret_doi_key, "") if ret_doi_key else ""),
            retraction_nature=nature or "Unknown",
            reason=str(row.get(reason_key, "") if reason_key else "").strip(),
            original_paper_date=str(row.get(paper_date_key, "") if paper_date_key else "").strip(),
            retraction_date=str(row.get(ret_date_key, "") if ret_date_key else "").strip(),
            is_retracted=is_ret,
            is_correction=is_corr,
            is_expression_of_concern=is_eoc,
        )

        if norm_doi not in index:
            index[norm_doi] = []
        index[norm_doi].append(record)

    return index


def diff_snapshots(
    old_index: dict[str, list[RetractionRecord]],
    new_index: dict[str, list[RetractionRecord]],
) -> dict[str, Any]:
    """Diff two snapshots of Retraction Watch data to detect newly added or escalated notices."""
    old_dois = set(old_index.keys())
    new_dois = set(new_index.keys())

    added_dois = sorted(new_dois - old_dois)
    removed_dois = sorted(old_dois - new_dois)

    escalated: list[dict[str, Any]] = []
    for doi in sorted(new_dois & old_dois):
        old_recs = old_index[doi]
        new_recs = new_index[doi]
        old_was_retracted = any(r.is_retracted for r in old_recs)
        new_is_retracted = any(r.is_retracted for r in new_recs)
        if not old_was_retracted and new_is_retracted:
            escalated.append({
                "doi": doi,
                "previous_natures": [r.retraction_nature for r in old_recs],
                "new_natures": [r.retraction_nature for r in new_recs],
            })

    new_flags: list[dict[str, Any]] = []
    for doi in added_dois:
        recs = new_index[doi]
        new_flags.append({
            "doi": doi,
            "natures": [r.retraction_nature for r in recs],
            "titles": [r.original_paper_title for r in recs if r.original_paper_title][:1],
            "is_retracted": any(r.is_retracted for r in recs),
        })

    return {
        "new_dois_count": len(added_dois),
        "removed_dois_count": len(removed_dois),
        "escalated_count": len(escalated),
        "total_previous": len(old_dois),
        "total_current": len(new_dois),
        "new_flags": new_flags,
        "escalated": escalated,
    }


def cross_check_openalex(
    doi: str,
    rw_records: list[RetractionRecord] | None = None,
    openalex_is_retracted: bool | None = None,
) -> dict[str, Any]:
    """Cross-check Retraction Watch records with OpenAlex is_retracted status."""
    norm_doi = normalize_doi(doi)
    rw_recs = rw_records or []
    rw_natures = [r.retraction_nature for r in rw_recs]
    rw_is_retracted = any(r.is_retracted for r in rw_recs)
    rw_is_corr = any(r.is_correction for r in rw_recs)
    rw_is_eoc = any(r.is_expression_of_concern for r in rw_recs)

    concordance: str
    verdict: str

    if rw_is_retracted and openalex_is_retracted is True:
        concordance = "CONFIRMED_RETRACTED"
        verdict = "RETRACTED"
    elif rw_is_retracted:
        concordance = "RETRACTION_WATCH_ONLY"
        verdict = "RETRACTED"
    elif openalex_is_retracted is True:
        concordance = "OPENALEX_ONLY"
        verdict = "RETRACTED"
    elif rw_is_eoc:
        concordance = "EXPRESSION_OF_CONCERN"
        verdict = "EXPRESSION_OF_CONCERN"
    elif rw_is_corr:
        concordance = "CORRECTION"
        verdict = "CORRECTION"
    else:
        concordance = "CLEAN"
        verdict = "CLEAN"

    return {
        "doi": norm_doi,
        "verdict": verdict,
        "concordance": concordance,
        "retraction_watch_flagged": bool(rw_recs),
        "retraction_watch_natures": rw_natures,
        "openalex_is_retracted": openalex_is_retracted,
        "records": [r.to_dict() for r in rw_recs],
    }


def check_doi(
    doi: str,
    rw_index: dict[str, list[RetractionRecord]],
    openalex_work_record: dict | None = None,
) -> Evidence:
    """Build an Evidence record for a DOI by checking Retraction Watch and OpenAlex."""
    norm_doi = normalize_doi(doi)
    recs = rw_index.get(norm_doi, [])
    openalex_retracted: bool | None = None
    if openalex_work_record is not None:
        openalex_retracted = bool(openalex_work_record.get("is_retracted", False))

    res = cross_check_openalex(norm_doi, recs, openalex_retracted)
    q = f"Does the Retraction Watch daily data or OpenAlex flag DOI {doi} as retracted, corrected, or under concern?"

    title = recs[0].original_paper_title if recs else (openalex_work_record.get("title") if openalex_work_record else None)
    excerpt = None
    if res["verdict"] == "RETRACTED":
        reasons = "; ".join(r.reason for r in recs if r.reason)
        excerpt = f"Flagged as retracted ({res['concordance']}). Reasons: {reasons or 'not stated'}"
    elif res["verdict"] in ("CORRECTION", "EXPRESSION_OF_CONCERN"):
        excerpt = f"Flagged with notice: {', '.join(res['retraction_watch_natures'])}"

    return Evidence(
        status=Status.FOUND,
        question=q,
        source_id=SOURCE,
        url=f"{DEFAULT_GITLAB_URL}#{norm_doi}",
        provider=PROVIDER,
        publisher_date=recs[0].retraction_date if recs and recs[0].retraction_date else None,
        fields={
            "doi": norm_doi,
            "title": title,
            "verdict": res["verdict"],
            "concordance": res["concordance"],
            "retraction_watch_flagged": res["retraction_watch_flagged"],
            "retraction_watch_natures": res["retraction_watch_natures"],
            "openalex_is_retracted": res["openalex_is_retracted"],
            "records_count": len(recs),
        },
        excerpt=excerpt,
        limitations=LIMITATION,
    )


def audit_catalog_sources(
    catalog_path: Path | str,
    rw_index: dict[str, list[RetractionRecord]],
    openalex_cache: dict[str, bool] | None = None,
) -> dict[str, Any]:
    """Audit every DOI cited in a sources/catalog.yaml file against Retraction Watch & OpenAlex."""
    import yaml

    cat_p = Path(catalog_path)
    if not cat_p.exists():
        raise FileNotFoundError(f"Source catalog not found at {catalog_path}")

    raw_yaml = cat_p.read_text(encoding="utf-8")
    data = yaml.safe_load(raw_yaml)
    sources = data.get("sources", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])

    checked_dois: set[str] = set()
    flagged: list[dict[str, Any]] = []
    clean: list[dict[str, Any]] = []

    oa_cache = openalex_cache or {}

    for src in sources:
        if not isinstance(src, dict):
            continue
        sid = src.get("id") or "unknown"
        title = src.get("title") or "unknown"

        # Find DOIs in fields, landing_page, url, notes
        found_dois: list[str] = []
        for key in ("doi", "landing_page", "url", "terms_url", "notes"):
            val = str(src.get(key) or "")
            for m in re.finditer(r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+\b", val):
                nd = normalize_doi(m.group(0))
                if nd and nd not in found_dois:
                    found_dois.append(nd)

        for d in found_dois:
            checked_dois.add(d)
            rw_recs = rw_index.get(d, [])
            oa_ret = oa_cache.get(d)
            res = cross_check_openalex(d, rw_recs, oa_ret)

            info = {
                "source_id": sid,
                "source_title": title,
                "doi": d,
                "verdict": res["verdict"],
                "concordance": res["concordance"],
                "natures": res["retraction_watch_natures"],
                "openalex_is_retracted": res["openalex_is_retracted"],
            }
            if res["verdict"] != "CLEAN":
                flagged.append(info)
            else:
                clean.append(info)

    return {
        "catalog_path": str(cat_p),
        "total_sources_scanned": len(sources),
        "unique_dois_checked": len(checked_dois),
        "clean_dois_count": len(clean),
        "flagged_dois_count": len(flagged),
        "flagged": flagged,
    }
