"""Scite Smart Citations provider via Scite Pro MCP (https://api.scite.ai/mcp) and REST API (https://api.scite.ai/).

Supports both quota buckets included in the Scite Personal Pro subscription (board task T-0047):
  1. MCP Bucket (`source="scite-mcp"`, 2,500 MCP tool uses/month, `SCITE_MCP_DAILY_CAP=60`).
  2. REST API Bucket (`source="scite-api"`, 750 Included REST API calls/month, `SCITE_REST_DAILY_CAP=20`).

Automatically refreshes expired OAuth 2.0 PKCE tokens in `~/.gemini/config/scite_mcp_oauth.json`
when `refresh_token` and `client_id` are present, and returns Evidence records with supporting,
contrasting, and mentioning citation tallies plus the mandatory `[observed: Scite ML citation classification]`
provenance limitation.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

from ..http import Client, Fetch
from ..record import Evidence, Status
from ..shape import ShapeError, count, error_record, need

PROVIDER = "scite/0.1"
SOURCE = "scite-mcp"
REST_SOURCE = "scite-api"
TOKEN_URL = "https://api.scite.ai/mcp/oauth/token"
DEFAULT_LIMIT = 5
MAX_LIMIT = 20

DEFAULT_OAUTH_FILE = Path.home() / ".gemini" / "config" / "scite_mcp_oauth.json"
DEFAULT_USAGE_LOG = Path.home() / ".gemini" / "config" / "scite_mcp_usage.jsonl"
DEFAULT_REST_USAGE_LOG = Path.home() / ".gemini" / "config" / "scite_rest_usage.jsonl"

LIMITATION = (
    "[observed: Scite ML citation classification]. Scite supporting, contrasting, and mentioning "
    "counts and citation statement classifications are produced by Scite's automated machine-learning "
    "model over indexed full-text and bibliographic corpora. Classifier labels can misclassify hedging "
    "or methodological discussion, and do not establish clinical replication, methodological validity, "
    "or therapeutic efficacy; confirm every flagged contrasting or supporting claim on the primary source."
)


def _resolve_bearer_token() -> str | None:
    """Resolve Scite bearer token from SCITE_API_KEY env var or ~/.gemini/config/scite_mcp_oauth.json (with auto-refresh)."""
    env_key = (os.environ.get("SCITE_API_KEY") or "").strip()
    if env_key and env_key != "your_key_here":
        return env_key

    oauth_path_str = os.environ.get("SCITE_MCP_OAUTH_FILE")
    oauth_path = Path(oauth_path_str) if oauth_path_str else DEFAULT_OAUTH_FILE
    if not oauth_path.is_file():
        return None
    try:
        data = json.loads(oauth_path.read_text(encoding="utf-8"))
        token = (data.get("access_token") or "").strip()
        expires_at = float(data.get("expires_at") or 0)
        if token and (expires_at == 0 or time.time() < expires_at - 30):
            return token

        refresh_token = (data.get("refresh_token") or "").strip()
        client_id = (data.get("client_id") or "").strip()
        if refresh_token and client_id and not os.environ.get("PYTEST_CURRENT_TEST"):
            resp = requests.post(
                TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": client_id,
                },
                timeout=15,
            )
            if resp.status_code == 200:
                tok = resp.json()
                new_token = (tok.get("access_token") or "").strip()
                if new_token:
                    data["access_token"] = new_token
                    if tok.get("refresh_token"):
                        data["refresh_token"] = tok["refresh_token"]
                    data["expires_at"] = time.time() + int(tok.get("expires_in", 3600))
                    oauth_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
                    return new_token
    except Exception:
        return None
    return None


def _check_daily_cap(*, rest: bool = False) -> str | None:
    """Enforce SCITE_MCP_DAILY_CAP (default 60/day) or SCITE_REST_DAILY_CAP (default 20/day)."""
    env_cap_name = "SCITE_REST_DAILY_CAP" if rest else "SCITE_MCP_DAILY_CAP"
    default_cap = 20 if rest else 60
    cap_str = os.environ.get(env_cap_name, str(default_cap))
    try:
        cap = int(cap_str)
    except ValueError:
        cap = default_cap

    env_log_name = "SCITE_REST_USAGE_LOG" if rest else "SCITE_MCP_USAGE_LOG"
    log_str = os.environ.get(env_log_name)
    if log_str is None and os.environ.get("PYTEST_CURRENT_TEST"):
        return None
    log_path = Path(log_str) if log_str else (DEFAULT_REST_USAGE_LOG if rest else DEFAULT_USAGE_LOG)
    today = time.strftime("%Y-%m-%d", time.gmtime())
    used = 0
    if log_path.is_file():
        try:
            for line in log_path.read_text(encoding="utf-8").splitlines():
                if f'"date": "{today}"' in line:
                    used += 1
        except Exception:
            pass
    if used >= cap:
        bucket = "REST" if rest else "MCP"
        return f"Scite {bucket} daily quota cap reached ({used}/{cap} calls today; {env_cap_name}={cap})"
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(
                json.dumps(
                    {
                        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "date": today,
                        "tool": "evidence_cli.scite_rest" if rest else "evidence_cli.scite",
                    }
                )
                + "\n"
            )
    except Exception:
        pass
    return None


def _unwrap_mcp_payload(data: Any) -> dict[str, Any]:
    """Extract the inner JSON object from an MCP tools/call response or direct JSON object."""
    if not isinstance(data, dict):
        raise ShapeError(f"Scite response is {type(data).__name__}, not an object")
    if "error" in data and data["error"]:
        err = data["error"]
        msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
        raise ShapeError(f"Scite MCP error: {msg}")
    if "result" in data and isinstance(data["result"], dict):
        res = data["result"]
        if res.get("isError"):
            raise ShapeError(f"Scite MCP tool error: {res.get('content')}")
        content = need(res, "content", "Scite MCP result")
        if not isinstance(content, list) or not content:
            raise ShapeError("Scite MCP result 'content' is empty or not a list")
        first = content[0]
        if not isinstance(first, dict) or not isinstance(first.get("text"), str):
            raise ShapeError("Scite MCP content[0] lacks 'text' string")
        txt = first["text"].strip()
        if txt.lower().startswith("no results") or txt.lower().startswith("no publications"):
            return {"hits": [], "total": 0}
        try:
            inner = json.loads(txt)
        except ValueError as exc:
            raise ShapeError(f"Scite MCP content[0].text is not valid JSON: {exc}") from exc
        if not isinstance(inner, dict):
            raise ShapeError(f"Scite MCP inner payload is {type(inner).__name__}, not an object")
        if inner.get("total") == 0 and "hits" not in inner:
            return {"hits": [], "total": 0}
        return inner
    if data.get("total") == 0 and "hits" not in data:
        return {"hits": [], "total": 0}
    return data


def _parse_hit(hit: dict[str, Any], question: str, url: str, search_total: int | None = None) -> Evidence:
    doi_val = hit.get("doi")
    if not doi_val or not isinstance(doi_val, str):
        raise ShapeError("Scite hit missing string 'doi'")
    tally = hit.get("tally") if isinstance(hit.get("tally"), dict) else {}
    supporting = count(tally.get("supporting", 0), "Scite tally.supporting")
    contrasting_raw = tally.get("contrasting", tally.get("contradicting", 0))
    contrasting = count(contrasting_raw, "Scite tally.contrasting")
    mentioning = count(tally.get("mentioning", 0), "Scite tally.mentioning")
    total_cit = count(tally.get("total", 0), "Scite tally.total")
    citing_pubs = count(tally.get("citingPublications", 0), "Scite tally.citingPublications")

    notices_raw = hit.get("editorialNotices")
    notices: list[dict[str, Any]] = []
    if isinstance(notices_raw, list):
        for n in notices_raw[:5]:
            if isinstance(n, dict):
                notices.append(
                    {
                        "status": n.get("status"),
                        "notice_doi": n.get("noticeDoi"),
                        "date": n.get("date"),
                    }
                )

    pub_date = str(hit.get("date") or hit.get("year") or "") or None
    fields: dict[str, Any] = {
        "doi": doi_val,
        "supporting": supporting,
        "contrasting": contrasting,
        "mentioning": mentioning,
        "total_smart_citations": total_cit,
        "citing_publications": citing_pubs,
        "title": hit.get("title"),
        "journal": hit.get("journal"),
        "year": hit.get("year"),
        "editorial_notices": notices,
        "is_oa": hit.get("isOa") if isinstance(hit.get("isOa"), bool) else None,
        "oa_status": hit.get("oaStatus"),
        "classification_provenance": "Scite ML citation classification",
    }
    if search_total is not None:
        fields["search_total"] = search_total

    report_url = f"https://scite.ai/reports/{doi_val}"
    return Evidence(
        status=Status.FOUND,
        question=question,
        source_id=SOURCE,
        url=report_url,
        provider=PROVIDER,
        publisher_date=pub_date,
        fields=fields,
        limitations=LIMITATION,
    )


def parse_rest_tally(data: Any, doi_query: str, question: str, url: str) -> Evidence:
    """Pure parser for Scite REST GET /tallies/{doi} response (750/month REST API bucket)."""
    try:
        if not isinstance(data, dict):
            raise ShapeError(f"Scite REST tally response is {type(data).__name__}, not an object")
        if "detail" in data and not data.get("doi"):
            raise ShapeError(f"Scite REST error: {data['detail']}")
        doi_val = data.get("doi")
        if not doi_val or not isinstance(doi_val, str):
            raise ShapeError("Scite REST tally missing string 'doi'")
        supporting = count(data.get("supporting", 0), "Scite REST supporting")
        contrasting_raw = data.get("contradicting", data.get("contrasting", 0))
        contrasting = count(contrasting_raw, "Scite REST contradicting")
        mentioning = count(data.get("mentioning", 0), "Scite REST mentioning")
        unclassified = count(data.get("unclassified", 0), "Scite REST unclassified")
        total_cit = count(data.get("total", 0), "Scite REST total")
        citing_pubs = count(data.get("citingPublications", 0), "Scite REST citingPublications")

        fields: dict[str, Any] = {
            "doi": doi_val,
            "supporting": supporting,
            "contrasting": contrasting,
            "mentioning": mentioning,
            "unclassified": unclassified,
            "total_smart_citations": total_cit,
            "citing_publications": citing_pubs,
            "quota_bucket": "scite-api-rest-750",
            "classification_provenance": "Scite ML citation classification",
        }
        return Evidence(
            status=Status.FOUND,
            question=question,
            source_id=REST_SOURCE,
            url=f"https://scite.ai/reports/{doi_val}",
            provider=PROVIDER,
            fields=fields,
            limitations=LIMITATION,
        )
    except ShapeError as exc:
        return error_record(exc, question=question, source_id=REST_SOURCE, url=url, provider=PROVIDER, fields={"doi": doi_query})


def parse_tally(data: Any, doi_query: str, question: str, url: str) -> Evidence:
    """Pure parser for a single DOI Scite Smart Citation tally lookup."""
    try:
        inner = _unwrap_mcp_payload(data)
        hits = need(inner, "hits", "Scite response")
        if not isinstance(hits, list):
            raise ShapeError(f"Scite 'hits' is {type(hits).__name__}, not a list")
        if not hits:
            return Evidence(
                status=Status.NOT_FOUND,
                question=question,
                source_id=SOURCE,
                url=url,
                provider=PROVIDER,
                fields={"doi": doi_query, "search_total": 0},
                limitations=LIMITATION,
            )
        if not isinstance(hits[0], dict):
            raise ShapeError("Scite hits[0] is not an object")
        return _parse_hit(hits[0], question, url)
    except ShapeError as exc:
        return error_record(exc, question=question, source_id=SOURCE, url=url, provider=PROVIDER, fields={"doi": doi_query})


def parse_search(data: Any, query: str, question: str, url: str, limit: int = DEFAULT_LIMIT) -> list[Evidence]:
    """Pure parser for a Scite literature search with Smart Citation tallies."""
    try:
        inner = _unwrap_mcp_payload(data)
        hits = need(inner, "hits", "Scite search response")
        if not isinstance(hits, list):
            raise ShapeError(f"Scite 'hits' is {type(hits).__name__}, not a list")
        total = count(inner.get("total", len(hits)), "Scite search total")
        if total == 0 or not hits:
            return [
                Evidence(
                    status=Status.NOT_FOUND,
                    question=question,
                    source_id=SOURCE,
                    url=url,
                    provider=PROVIDER,
                    fields={"query": query, "search_total": 0},
                    limitations=LIMITATION,
                )
            ]
        out: list[Evidence] = []
        for idx, h in enumerate(hits[: max(1, min(limit, MAX_LIMIT))]):
            if not isinstance(h, dict):
                raise ShapeError(f"Scite hit {idx} is not an object")
            out.append(_parse_hit(h, question, url, search_total=total))
        return out
    except ShapeError as exc:
        return [error_record(exc, question=question, source_id=SOURCE, url=url, provider=PROVIDER, fields={"query": query})]


def _fail(f: Fetch, question: str, extra: dict[str, Any], source_id: str = SOURCE) -> Evidence:
    return Evidence(
        status=f.status,
        question=question,
        source_id=source_id,
        url=f.url,
        provider=PROVIDER,
        fields={"http_status": f.http_status, **extra},
        limitations=LIMITATION,
    )


def _normalize_doi(doi: str) -> str:
    norm_doi = doi.strip()
    if norm_doi.lower().startswith("https://doi.org/"):
        norm_doi = norm_doi[16:].strip()
    elif norm_doi.lower().startswith("doi:"):
        norm_doi = norm_doi[4:].strip()
    return norm_doi


def tally_rest(client: Client, doi: str) -> Evidence:
    """Look up Smart Citation tallies via Scite REST API GET /tallies/{doi} (750/month Included API calls bucket)."""
    norm_doi = _normalize_doi(doi)
    q = f"What are the Scite REST API supporting, contrasting, and mentioning citation tallies for DOI '{norm_doi}'?"
    path = f"tallies/{quote(norm_doi, safe='/')}"

    if client.dry_run:
        f = client.get(REST_SOURCE, path)
        return Evidence(
            status=Status.OUT_OF_SCOPE,
            question=q,
            source_id=REST_SOURCE,
            url=f.url,
            provider=PROVIDER,
            fields={"doi": norm_doi, "planned_endpoint": path, "quota_bucket": "scite-api-rest-750"},
            limitations=LIMITATION,
        )

    token = _resolve_bearer_token()
    if not token:
        return Evidence(
            status=Status.BLOCKED,
            question=q,
            source_id=REST_SOURCE,
            url=client._url(REST_SOURCE, path),
            provider=PROVIDER,
            fields={
                "doi": norm_doi,
                "error": "Scite credentials not found (set SCITE_API_KEY or authenticate ~/.gemini/config/scite_mcp_oauth.json)",
            },
            limitations=LIMITATION,
        )

    cap_err = _check_daily_cap(rest=True)
    if cap_err:
        return Evidence(
            status=Status.BLOCKED,
            question=q,
            source_id=REST_SOURCE,
            url=client._url(REST_SOURCE, path),
            provider=PROVIDER,
            fields={"doi": norm_doi, "error": cap_err},
            limitations=LIMITATION,
        )

    headers = {"Authorization": f"Bearer {token}"}
    f = client.get(REST_SOURCE, path, headers=headers)
    if f.status is not Status.FOUND:
        return _fail(f, q, {"doi": norm_doi}, source_id=REST_SOURCE)
    return parse_rest_tally(f.data, norm_doi, q, f.url)


def tally(client: Client, doi: str, *, use_rest: bool = False) -> Evidence:
    """Look up supporting, contrasting, and mentioning Smart Citation tallies for a DOI via Scite MCP (or REST if use_rest=True)."""
    if use_rest:
        return tally_rest(client, doi)

    norm_doi = _normalize_doi(doi)
    q = f"What are the Scite supporting, contrasting, and mentioning citation tallies for DOI '{norm_doi}'?"
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "search_literature",
            "arguments": {"dois": [norm_doi], "limit": 1},
        },
    }

    if client.dry_run:
        f = client.post(SOURCE, "", json=payload)
        return Evidence(
            status=Status.OUT_OF_SCOPE,
            question=q,
            source_id=SOURCE,
            url=f.url,
            provider=PROVIDER,
            fields={"doi": norm_doi, "planned_tool": "search_literature", "quota_bucket": "scite-mcp-2500"},
            limitations=LIMITATION,
        )

    token = _resolve_bearer_token()
    if not token:
        return Evidence(
            status=Status.BLOCKED,
            question=q,
            source_id=SOURCE,
            url=client._url(SOURCE, ""),
            provider=PROVIDER,
            fields={
                "doi": norm_doi,
                "error": "Scite credentials not found (set SCITE_API_KEY or authenticate ~/.gemini/config/scite_mcp_oauth.json)",
            },
            limitations=LIMITATION,
        )

    cap_err = _check_daily_cap(rest=False)
    if cap_err:
        return Evidence(
            status=Status.BLOCKED,
            question=q,
            source_id=SOURCE,
            url=client._url(SOURCE, ""),
            provider=PROVIDER,
            fields={"doi": norm_doi, "error": cap_err},
            limitations=LIMITATION,
        )

    headers = {"Authorization": f"Bearer {token}"}
    f = client.post(SOURCE, "", json=payload, headers=headers)
    if f.status is not Status.FOUND:
        return _fail(f, q, {"doi": norm_doi})
    return parse_tally(f.data, norm_doi, q, f.url)


def search(client: Client, query: str, limit: int = DEFAULT_LIMIT) -> list[Evidence]:
    """Search literature with Scite Smart Citation tallies via Scite MCP."""
    stripped = query.strip()
    max_items = max(1, min(limit, MAX_LIMIT))
    q = f"Which publications in Scite match '{stripped}'?"
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "search_literature",
            "arguments": {"term": stripped, "limit": max_items},
        },
    }

    if client.dry_run:
        f = client.post(SOURCE, "", json=payload)
        return [
            Evidence(
                status=Status.OUT_OF_SCOPE,
                question=q,
                source_id=SOURCE,
                url=f.url,
                provider=PROVIDER,
                fields={"planned_query": stripped, "planned_tool": "search_literature"},
                limitations=LIMITATION,
            )
        ]

    token = _resolve_bearer_token()
    if not token:
        return [
            Evidence(
                status=Status.BLOCKED,
                question=q,
                source_id=SOURCE,
                url=client._url(SOURCE, ""),
                provider=PROVIDER,
                fields={
                    "query": stripped,
                    "error": "Scite credentials not found (set SCITE_API_KEY or authenticate ~/.gemini/config/scite_mcp_oauth.json)",
                },
                limitations=LIMITATION,
            )
        ]

    cap_err = _check_daily_cap(rest=False)
    if cap_err:
        return [
            Evidence(
                status=Status.BLOCKED,
                question=q,
                source_id=SOURCE,
                url=client._url(SOURCE, ""),
                provider=PROVIDER,
                fields={"query": stripped, "error": cap_err},
                limitations=LIMITATION,
            )
        ]

    headers = {"Authorization": f"Bearer {token}"}
    f = client.post(SOURCE, "", json=payload, headers=headers)
    if f.status is not Status.FOUND:
        return [_fail(f, q, {"query": stripped})]
    return parse_search(f.data, stripped, q, f.url, limit=max_items)
