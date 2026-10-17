"""UKRI Gateway to Research (GtR) API provider: UK publicly funded research.

Queries https://gtr.ukri.org/gtr/api/projects for research council funded projects
(MRC, EPSRC, BBSRC, ESRC, AHRC, NERC, STFC, Innovate UK, Research England).
Uses polite Client with source="ukri-gtr" under Open Government Licence v3.0 (OGL).
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

from .. import catalog
from ..http import Client, Fetch
from ..record import Evidence, Status
from ..shape import ShapeError, count, error_record, need

PROVIDER = "ukri_gtr/0.1"
SOURCE = "ukri-gtr"
ACCEPT_HEADER = "application/vnd.rcuk.gtr.json-v7"
OGL_LICENSE = "Open Government Licence v3.0 (OGL)"
OGL_ATTRIBUTION = "Contains UKRI Gateway to Research data licensed under the Open Government Licence v3.0"

LIMITATION = (
    f"{OGL_ATTRIBUTION}. "
    "UK publicly funded research grant metadata only; excludes charity (e.g. Cystic Fibrosis Trust), industry, "
    "and non-UK funders. Grant award metadata and abstracts reflect funded research proposals, "
    "not clinical outcomes, efficacy, or regulatory approval."
)

EXCERPT_CHARS = 700
DEFAULT_LIMIT = 25
MAX_LIMIT = 100
UUID_PATTERN = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def _projects_path() -> str:
    """Return relative path to projects endpoint based on catalog base_url."""
    base = catalog.base_url(SOURCE)
    if "gtr/api" in base.rstrip("/"):
        return "projects"
    return "../gtr/api/projects"


def _extract_grant_ref(project: dict) -> str | None:
    identifiers = project.get("identifiers")
    if isinstance(identifiers, dict):
        id_list = identifiers.get("identifier")
        if isinstance(id_list, list):
            for item in id_list:
                if isinstance(item, dict) and item.get("value"):
                    return str(item["value"])
    return None


def _epoch_ms_to_uk_date(epoch_ms: int | float) -> str:
    """Format epoch-ms timestamp as YYYY-MM-DD in Europe/London timezone.

    GtR timestamps reflect UK local time (midnight GMT or BST), so in summer
    midnight BST (UTC+1) is 23:00 UTC the previous day. Converting in Europe/London
    ensures the calendar date matches the official grant start/end date.
    """
    try:
        from zoneinfo import ZoneInfo
        return datetime.fromtimestamp(epoch_ms / 1000, ZoneInfo("Europe/London")).strftime("%Y-%m-%d")
    except Exception:
        pass
    dt_utc = datetime.fromtimestamp(epoch_ms / 1000, timezone.utc)
    y = dt_utc.year
    # In the UK, BST starts at 01:00 UTC on the last Sunday of March
    march_last_sun = 31 - (datetime(y, 3, 31).weekday() + 1) % 7
    bst_start = datetime(y, 3, march_last_sun, 1, 0, tzinfo=timezone.utc)
    # BST ends at 01:00 UTC on the last Sunday of October
    oct_last_sun = 31 - (datetime(y, 10, 31).weekday() + 1) % 7
    bst_end = datetime(y, 10, oct_last_sun, 1, 0, tzinfo=timezone.utc)
    if bst_start <= dt_utc < bst_end:
        dt_uk = dt_utc + timedelta(hours=1)
    else:
        dt_uk = dt_utc
    return dt_uk.strftime("%Y-%m-%d")


def _extract_fund_info(project: dict) -> tuple[str | None, str | None, int | None, int | None, int | None]:
    links = project.get("links")
    start_dt, end_dt, amount = None, None, None
    start_epoch, end_epoch = None, None
    if isinstance(links, dict):
        link_list = links.get("link")
        if isinstance(link_list, list):
            for lnk in link_list:
                if isinstance(lnk, dict) and lnk.get("rel") == "FUND":
                    s = lnk.get("start")
                    if isinstance(s, (int, float)) and s > 0:
                        start_epoch = int(s)
                        start_dt = _epoch_ms_to_uk_date(start_epoch)
                    e = lnk.get("end")
                    if isinstance(e, (int, float)) and e > 0:
                        end_epoch = int(e)
                        end_dt = _epoch_ms_to_uk_date(end_epoch)
    return start_dt, end_dt, amount, start_epoch, end_epoch


def _extract_link_href(project: dict, rel: str) -> str | None:
    links = project.get("links")
    if isinstance(links, dict):
        link_list = links.get("link")
        if isinstance(link_list, list):
            for lnk in link_list:
                if isinstance(lnk, dict) and lnk.get("rel") == rel:
                    return lnk.get("href")
    return None


def _parse_single_project(p: dict, question: str, url: str, total: int | None = None) -> Evidence:
    pid = p.get("id")
    title = p.get("title")
    status_text = p.get("status")
    funder = p.get("leadFunder")
    grant_cat = p.get("grantCategory")
    grant_ref = _extract_grant_ref(p)
    fund_start, fund_end, fund_amount, start_epoch, end_epoch = _extract_fund_info(p)

    created_epoch = p.get("created")
    created_str = (
        _epoch_ms_to_uk_date(created_epoch)
        if isinstance(created_epoch, (int, float)) and created_epoch > 0
        else None
    )
    pub_date = fund_start or created_str

    abstract = (p.get("abstractText") or "").strip()
    excerpt = None
    if abstract:
        excerpt = abstract[:EXCERPT_CHARS] + ("…" if len(abstract) > EXCERPT_CHARS else "")

    fields: dict[str, Any] = {
        "project_id": pid,
        "title": title,
        "status": status_text,
        "lead_funder": funder,
        "grant_category": grant_cat,
        "grant_reference": grant_ref,
        "start": fund_start,
        "end": fund_end,
        "start_epoch_ms": start_epoch,
        "end_epoch_ms": end_epoch,
        "award_amount": fund_amount,
        "license": OGL_LICENSE,
        "license_attribution": OGL_ATTRIBUTION,
    }
    if total is not None:
        fields["search_total"] = total

    project_url = p.get("href") or (f"https://gtr.ukri.org/projects?ref={grant_ref}" if grant_ref else url)

    return Evidence(
        status=Status.FOUND,
        question=question,
        source_id=SOURCE,
        url=project_url,
        provider=PROVIDER,
        publisher_date=pub_date,
        fields=fields,
        excerpt=excerpt,
        limitations=LIMITATION,
    )


def parse_projects(data: Any, question: str, url: str, limit: int | None = None) -> list[Evidence]:
    """Pure parsing of UKRI GTR search response with strict shape verification."""
    if not isinstance(data, dict):
        exc = ShapeError(f"UKRI GTR projects response is {type(data).__name__}, not an object")
        return [error_record(exc, question=question, source_id=SOURCE, url=url, provider=PROVIDER)]

    try:
        total_raw = need(data, "totalSize", "UKRI GTR projects search")
        total = count(total_raw, "UKRI GTR projects search totalSize")
        project_list = data.get("project")
        if project_list is None and total == 0:
            project_list = []
        if not isinstance(project_list, list):
            raise ShapeError(f"UKRI GTR projects search 'project' is {type(project_list).__name__}, not a list")
    except ShapeError as exc:
        return [error_record(exc, question=question, source_id=SOURCE, url=url, provider=PROVIDER)]

    if total == 0 or len(project_list) == 0:
        return [
            Evidence(
                status=Status.NOT_FOUND,
                question=question,
                source_id=SOURCE,
                url=url,
                provider=PROVIDER,
                fields={
                    "search_total": total,
                    "license": OGL_LICENSE,
                    "license_attribution": OGL_ATTRIBUTION,
                },
                limitations=LIMITATION,
            )
        ]

    # Finding 1.3: Slice project_list to requested limit while retaining search_total
    if limit is not None and limit > 0:
        project_list = project_list[:limit]

    out = []
    for idx, p in enumerate(project_list):
        if not isinstance(p, dict):
            exc = ShapeError(f"UKRI GTR project item {idx} is {type(p).__name__}, not an object")
            return [error_record(exc, question=question, source_id=SOURCE, url=url, provider=PROVIDER)]
        out.append(_parse_single_project(p, question, url, total=total))

    return out



def parse_project(data: Any, question: str, url: str) -> Evidence:
    """Pure parsing of a single UKRI GTR project record."""
    if not isinstance(data, dict):
        exc = ShapeError(f"UKRI GTR project response is {type(data).__name__}, not an object")
        return error_record(exc, question=question, source_id=SOURCE, url=url, provider=PROVIDER)

    try:
        need(data, "id", "UKRI GTR project")
        need(data, "title", "UKRI GTR project")
    except ShapeError as exc:
        return error_record(exc, question=question, source_id=SOURCE, url=url, provider=PROVIDER)

    return _parse_single_project(data, question, url)


def _fail(f: Fetch, question: str) -> Evidence:
    return Evidence(
        status=f.status,
        question=question,
        source_id=SOURCE,
        url=f.url,
        provider=PROVIDER,
        fields={"http_status": f.http_status, "license": OGL_LICENSE},
        limitations=LIMITATION,
    )


def search(client: Client, query: str, limit: int = DEFAULT_LIMIT) -> list[Evidence]:
    """Search UKRI Gateway to Research projects matching query."""
    q = f"Which UKRI projects match '{query}'?"
    # UKRI GTR requires page size (s) to be between 10 and 100
    safe_limit = max(10, min(limit, MAX_LIMIT))
    max_projects = max(1, min(limit, MAX_LIMIT))
    path = _projects_path()
    params = {"q": query, "s": safe_limit}
    headers = {"Accept": ACCEPT_HEADER}

    f = client.get(SOURCE, path, params=params, headers=headers)
    if f.dry_run:
        return [
            Evidence(
                status=Status.OUT_OF_SCOPE,
                question=q,
                source_id=SOURCE,
                url=f.url,
                provider=PROVIDER,
                fields={"planned_query": query, "license": OGL_LICENSE},
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
                fields={"query": query, "search_total": 0, "license": OGL_LICENSE},
                limitations=LIMITATION,
            )
        ]

    if f.status is not Status.FOUND:
        return [_fail(f, q)]

    return parse_projects(f.data, q, f.url, limit=max_projects)



def project(client: Client, project_id: str) -> Evidence:
    """Look up a single UKRI project by ID."""
    q = f"What is the UKRI project '{project_id}'?"
    path = f"{_projects_path()}/{project_id}"
    headers = {"Accept": ACCEPT_HEADER}

    f = client.get(SOURCE, path, headers=headers)
    if f.dry_run:
        return Evidence(
            status=Status.OUT_OF_SCOPE,
            question=q,
            source_id=SOURCE,
            url=f.url,
            provider=PROVIDER,
            fields={"project_id": project_id, "license": OGL_LICENSE},
            limitations=LIMITATION,
        )

    if f.status is Status.NOT_FOUND:
        return Evidence(
            status=Status.NOT_FOUND,
            question=q,
            source_id=SOURCE,
            url=f.url,
            provider=PROVIDER,
            fields={"project_id": project_id, "license": OGL_LICENSE},
            limitations=LIMITATION,
        )

    if f.status is not Status.FOUND:
        return _fail(f, q)

    return parse_project(f.data, q, f.url)


def search_or_get(client: Client, query: str, limit: int = DEFAULT_LIMIT) -> list[Evidence]:
    """Dispatch to single project lookup if query is a UUID, otherwise search."""
    stripped = query.strip()
    if UUID_PATTERN.match(stripped):
        rec = project(client, stripped)
        return [rec]
    return search(client, query, limit)
