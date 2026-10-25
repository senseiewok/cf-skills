"""DailyMed RESTful web services v2 provider for Structured Product Labels (SPL).

Catalog source: `dailymed-web-services` (`https://dailymed.nlm.nih.gov/dailymed/services/v2/`).
Complements openFDA drug labels with NLM DailyMed SPL set_id, version, and publication date metadata.
"""

from __future__ import annotations

from typing import Any

from ..http import Client, Fetch
from ..record import Evidence, Status
from ..shape import ShapeError, count, error_record, need

PROVIDER = "dailymed/0.1"
SOURCE = "dailymed-web-services"
DEFAULT_LIMIT = 5
MAX_LIMIT = 20

LIMITATION = (
    "DailyMed Structured Product Label (SPL) metadata is provided by the U.S. National Library of Medicine (NLM) "
    "without warranty or endorsement. It reflects US drug package insert listings only, not clinical advice for any person."
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


def parse_spls(data: Any, drug_name: str, question: str, url: str, limit: int = DEFAULT_LIMIT) -> list[Evidence]:
    """Pure parser for DailyMed GET spls.json?drug_name={drug_name} response."""
    try:
        if not isinstance(data, dict):
            raise ShapeError(f"DailyMed response is {type(data).__name__}, not an object")
        rows = need(data, "data", "DailyMed spls response")
        if not isinstance(rows, list):
            raise ShapeError(f"DailyMed 'data' is {type(rows).__name__}, not a list")
        meta = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
        total_raw = meta.get("total_elements", len(rows))
        total = count(total_raw, "DailyMed metadata.total_elements")

        if total == 0 or not rows:
            return [
                Evidence(
                    status=Status.NOT_FOUND,
                    question=question,
                    source_id=SOURCE,
                    url=url,
                    provider=PROVIDER,
                    fields={"drug_name": drug_name, "search_total": 0},
                    limitations=LIMITATION,
                )
            ]

        out: list[Evidence] = []
        max_items = max(1, min(limit, MAX_LIMIT))
        for idx, row in enumerate(rows[:max_items]):
            if not isinstance(row, dict):
                raise ShapeError(f"DailyMed data[{idx}] is not an object")
            setid = need(row, "setid", f"DailyMed data[{idx}]")
            if not isinstance(setid, str) or not setid.strip():
                raise ShapeError(f"DailyMed data[{idx}].setid is not a non-empty string")
            title = row.get("title")
            pub_date = row.get("published_date")
            spl_ver = row.get("spl_version")
            out.append(
                Evidence(
                    status=Status.FOUND,
                    question=question,
                    source_id=SOURCE,
                    url=f"https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid={setid}",
                    provider=PROVIDER,
                    publisher_date=str(pub_date) if pub_date else None,
                    fields={
                        "drug_name": drug_name,
                        "set_id": setid,
                        "title": title,
                        "published_date": pub_date,
                        "spl_version": spl_ver,
                        "search_total": total,
                        "source_acknowledgment": "U.S. National Library of Medicine (DailyMed)",
                    },
                    limitations=LIMITATION,
                )
            )
        return out
    except ShapeError as exc:
        return [error_record(exc, question=question, source_id=SOURCE, url=url, provider=PROVIDER, fields={"drug_name": drug_name})]


def spls(client: Client, drug_name: str, limit: int = DEFAULT_LIMIT) -> list[Evidence]:
    """Search DailyMed Structured Product Labels (SPLs) by drug name."""
    q_str = drug_name.strip()
    max_items = max(1, min(limit, MAX_LIMIT))
    question = f"Which DailyMed Structured Product Labels (SPLs) match drug '{q_str}'?"
    params = {"drug_name": q_str, "pagesize": max_items}

    if client.dry_run:
        f = client.get(SOURCE, "spls.json", params=params)
        return [
            Evidence(
                status=Status.OUT_OF_SCOPE,
                question=question,
                source_id=SOURCE,
                url=f.url,
                provider=PROVIDER,
                fields={"drug_name": q_str, "planned_endpoint": "spls.json"},
                limitations=LIMITATION,
            )
        ]

    f = client.get(SOURCE, "spls.json", params=params)
    if f.status is not Status.FOUND:
        return [_fail(f, question, {"drug_name": q_str})]
    return parse_spls(f.data, q_str, question, f.url, limit=max_items)
