"""Scite Smart Citations provider with 3-tier Zero-Overage Quota Protection (T-0047).

Per https://docs.scite.ai/quickstart and https://docs.scite.ai/pricing-and-plans:
  1. Tier 1 — Public Unauthenticated REST (`source="scite-api"`, `GET /tallies/{doi}` & `GET /papers/{doi}`):
     Public endpoints require NO API key and consume ZERO of the 750 monthly REST API calls
     and ZERO of the 2,500 monthly MCP credits. Default for `scite <DOI>` when `--rest` is passed
     (or when unauthenticated).
  2. Tier 2 — Authenticated Scite Pro MCP (`source="scite-mcp"`, `POST https://api.scite.ai/mcp`):
     Uses ONLY the OAuth 2.0 PKCE token (`~/.gemini/config/scite_mcp_oauth.json`, never `SCITE_API_KEY`)
     so MCP calls only draw from the 2,500/month MCP bucket (which has no pay-as-you-go overage).
     Hard-capped fail-closed at `SCITE_MCP_DAILY_CAP=60` and `SCITE_MCP_MONTHLY_CAP=2400` (100-call buffer).
  3. Tier 3 — Authenticated Scite REST API (`SCITE_API_KEY`, 750 included calls/month; $0.08/call overage):
     Hard-capped fail-closed at `SCITE_REST_DAILY_CAP=20` and `SCITE_REST_MONTHLY_CAP=650` (100-call safety
     buffer below 750) so no script or agent can ever reach 750 calls or trigger pay-as-you-go billing.
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
from ..record import Evidence, Status, clean_for_terminal
from ..shape import ShapeError, count, error_record, need

PROVIDER = "scite/0.1"
SOURCE = "scite-mcp"
REST_SOURCE = "scite-api"
TOKEN_URL = "https://api.scite.ai/mcp/oauth/token"
DEFAULT_LIMIT = 5
MAX_LIMIT = 20
MAX_BATCH_CHUNK = 500
MAX_BATCH_TOTAL = 2000

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


def _resolve_bearer_token(*, allow_api_key: bool = True) -> str | None:
    """Resolve Scite bearer token.

    For MCP calls, prefers the OAuth 2.0 PKCE token in ~/.gemini/config/scite_mcp_oauth.json
    (with auto-refresh) so MCP calls draw from the 2,500/month MCP credit pool rather than the
    750/month REST API key pool. Falls back to SCITE_API_KEY only when allow_api_key=True.
    """
    oauth_path_str = os.environ.get("SCITE_MCP_OAUTH_FILE")
    oauth_path = Path(oauth_path_str) if oauth_path_str else DEFAULT_OAUTH_FILE
    if oauth_path.is_file():
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
            pass

    if allow_api_key:
        env_key = (os.environ.get("SCITE_API_KEY") or "").strip()
        if env_key and env_key != "your_key_here":
            return env_key
    return None


def _check_daily_cap(*, rest: bool = False) -> str | None:
    """Enforce fail-closed daily AND monthly hard caps (MCP: 60/day & 2400/month; REST: 20/day & 650/month)."""
    env_daily_name = "SCITE_REST_DAILY_CAP" if rest else "SCITE_MCP_DAILY_CAP"
    env_monthly_name = "SCITE_REST_MONTHLY_CAP" if rest else "SCITE_MCP_MONTHLY_CAP"
    default_daily = 20 if rest else 60
    default_monthly = 650 if rest else 2400

    try:
        daily_cap = int(os.environ.get(env_daily_name, str(default_daily)))
    except ValueError:
        daily_cap = default_daily
    try:
        monthly_cap = int(os.environ.get(env_monthly_name, str(default_monthly)))
    except ValueError:
        monthly_cap = default_monthly

    env_log_name = "SCITE_REST_USAGE_LOG" if rest else "SCITE_MCP_USAGE_LOG"
    log_str = os.environ.get(env_log_name)
    if log_str is None and os.environ.get("PYTEST_CURRENT_TEST"):
        return None
    log_path = Path(log_str) if log_str else (DEFAULT_REST_USAGE_LOG if rest else DEFAULT_USAGE_LOG)
    today = time.strftime("%Y-%m-%d", time.gmtime())
    month_prefix = today[:7]  # YYYY-MM
    daily_used = 0
    monthly_used = 0
    bucket = "REST" if rest else "MCP"

    if log_path.is_file():
        try:
            for line in log_path.read_text(encoding="utf-8").splitlines():
                if f'"date": "{today}"' in line:
                    daily_used += 1
                if f'"date": "{month_prefix}' in line:
                    monthly_used += 1
        except Exception as exc:
            return f"Scite {bucket} quota ledger unreadable (fail-closed to prevent overage): {exc}"

    if monthly_used >= monthly_cap:
        return (
            f"Scite {bucket} monthly hard cap reached ({monthly_used}/{monthly_cap} calls in {month_prefix}; "
            f"{env_monthly_name}={monthly_cap}) — fail-closed to prevent pay-as-you-go overage"
        )
    if daily_used >= daily_cap:
        return f"Scite {bucket} daily quota cap reached ({daily_used}/{daily_cap} calls today; {env_daily_name}={daily_cap})"

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
    except Exception as exc:
        return f"Scite {bucket} quota ledger write failed (fail-closed to prevent overage): {exc}"
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
    """Pure parser for Scite public REST GET /tallies/{doi} response (0 API/MCP quota cost)."""
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
            "quota_bucket": "scite-public-tallies-free",
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
    """Look up Smart Citation tallies via public unauthenticated Scite REST GET /tallies/{doi} (0 quota cost!).

    Per https://docs.scite.ai/quickstart, /tallies/{doi} is a public endpoint that requires no API key.
    Sending no Authorization header ensures zero calls are billed against the 750/month REST API key quota.
    """
    norm_doi = _normalize_doi(doi)
    q = f"What are the Scite public REST API supporting, contrasting, and mentioning citation tallies for DOI '{norm_doi}'?"
    path = f"tallies/{quote(norm_doi, safe='/')}"

    if client.dry_run:
        f = client.get(REST_SOURCE, path)
        return Evidence(
            status=Status.OUT_OF_SCOPE,
            question=q,
            source_id=REST_SOURCE,
            url=f.url,
            provider=PROVIDER,
            fields={"doi": norm_doi, "planned_endpoint": path, "quota_bucket": "scite-public-tallies-free"},
            limitations=LIMITATION,
        )

    f = client.get(REST_SOURCE, path)
    if f.status is not Status.FOUND:
        return _fail(f, q, {"doi": norm_doi}, source_id=REST_SOURCE)
    return parse_rest_tally(f.data, norm_doi, q, f.url)


def tally(client: Client, doi: str, *, use_rest: bool = False) -> Evidence:
    """Look up supporting, contrasting, and mentioning Smart Citation tallies for a DOI via Scite MCP (or public REST if use_rest=True)."""
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


def _classify_section_triage(
    contrasting: int,
    intro: int,
    methods: int,
    results: int,
    discussion: int,
    total: int,
) -> tuple[str, float]:
    """Compute section-weighted triage signal and Results/Methods citation share."""
    denom = max(1, total)
    rm_share = round((results + methods) / denom, 4)
    if contrasting > 0 and (results > 0 or methods > 0):
        return "EMPIRICAL_OR_METHODOLOGICAL_ATTENTION", rm_share
    if contrasting > 0:
        return "DISCURSIVE_DIFFERENCE", rm_share
    if total > 0 and intro >= 0.8 * denom:
        return "BACKGROUND_FRAMING", rm_share
    return "UNCONTESTED", rm_share


def parse_rest_sections(
    sec_data: Any,
    tally_data: Any | None,
    doi_query: str,
    question: str,
    url: str,
) -> Evidence:
    """Pure parser for Scite public REST GET /tallies/cited-by-sections/{doi} (+ optional /tallies/{doi})."""
    try:
        if not isinstance(sec_data, dict):
            raise ShapeError(f"Scite section tally response is {type(sec_data).__name__}, not an object")
        if "detail" in sec_data and not sec_data.get("doi"):
            raise ShapeError(f"Scite section tally error: {sec_data['detail']}")
        doi_val = sec_data.get("doi")
        if not doi_val or not isinstance(doi_val, str):
            raise ShapeError("Scite section tally missing string 'doi'")

        intro = count(sec_data.get("introduction", 0), "Scite section introduction")
        methods = count(sec_data.get("methods", 0), "Scite section methods")
        results = count(sec_data.get("results", 0), "Scite section results")
        discussion = count(sec_data.get("discussion", 0), "Scite section discussion")
        other = count(sec_data.get("other", 0), "Scite section other")
        sec_total = count(sec_data.get("total", 0), "Scite section total")

        supporting = 0
        contrasting = 0
        mentioning = 0
        unclassified = 0
        citing_pubs = 0
        if isinstance(tally_data, dict) and isinstance(tally_data.get("doi"), str):
            supporting = count(tally_data.get("supporting", 0), "Scite REST supporting")
            contrasting = count(
                tally_data.get("contradicting", tally_data.get("contrasting", 0)),
                "Scite REST contradicting",
            )
            mentioning = count(tally_data.get("mentioning", 0), "Scite REST mentioning")
            unclassified = count(tally_data.get("unclassified", 0), "Scite REST unclassified")
            citing_pubs = count(tally_data.get("citingPublications", 0), "Scite REST citingPublications")

        triage_label, rm_share = _classify_section_triage(
            contrasting=contrasting,
            intro=intro,
            methods=methods,
            results=results,
            discussion=discussion,
            total=sec_total,
        )

        fields: dict[str, Any] = {
            "doi": doi_val,
            "section_tallies": {
                "introduction": intro,
                "methods": methods,
                "results": results,
                "discussion": discussion,
                "other": other,
                "total": sec_total,
            },
            "supporting": supporting,
            "contrasting": contrasting,
            "mentioning": mentioning,
            "unclassified": unclassified,
            "citing_publications": citing_pubs,
            "results_methods_citation_share_computed": rm_share,
            "section_triage_computed": triage_label,
            "quota_bucket": "scite-public-tallies-free",
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
        return error_record(
            exc,
            question=question,
            source_id=REST_SOURCE,
            url=url,
            provider=PROVIDER,
            fields={"doi": doi_query},
        )


def tally_sections(client: Client, doi: str) -> Evidence:
    """Look up section-level citation breakdown + polarity via unauthenticated public REST (0 quota cost!)."""
    norm_doi = _normalize_doi(doi)
    q = f"How are citations to DOI '{norm_doi}' distributed across Introduction, Methods, Results, and Discussion sections in Scite?"
    sec_path = f"tallies/cited-by-sections/{quote(norm_doi, safe='/')}"
    tally_path = f"tallies/{quote(norm_doi, safe='/')}"

    if client.dry_run:
        f = client.get(REST_SOURCE, sec_path)
        client.get(REST_SOURCE, tally_path)
        return Evidence(
            status=Status.OUT_OF_SCOPE,
            question=q,
            source_id=REST_SOURCE,
            url=f.url,
            provider=PROVIDER,
            fields={
                "doi": norm_doi,
                "planned_endpoint": sec_path,
                "quota_bucket": "scite-public-tallies-free",
            },
            limitations=LIMITATION,
        )

    f_sec = client.get(REST_SOURCE, sec_path)
    if f_sec.status is not Status.FOUND:
        return _fail(f_sec, q, {"doi": norm_doi}, source_id=REST_SOURCE)
    f_tal = client.get(REST_SOURCE, tally_path)
    tally_payload = f_tal.data if f_tal.status is Status.FOUND else None
    return parse_rest_sections(f_sec.data, tally_payload, norm_doi, q, f_sec.url)


def parse_batch_tallies(
    tallies_data: Any,
    papers_data: Any | None,
    sections_data: Any | None,
    dois: list[str],
    question: str,
    url: str,
) -> list[Evidence]:
    """Pure parser for Scite public bulk POST /tallies (+ optional POST /papers and POST /tallies/cited-by-sections)."""
    try:
        if not isinstance(tallies_data, dict) or not isinstance(tallies_data.get("tallies"), dict):
            raise ShapeError("Scite bulk tallies response missing 'tallies' object")
        t_map: dict[str, Any] = {
            k.lower(): v for k, v in tallies_data["tallies"].items() if isinstance(k, str) and isinstance(v, dict)
        }
        p_map: dict[str, Any] = {}
        if isinstance(papers_data, dict) and isinstance(papers_data.get("papers"), dict):
            p_map = {
                k.lower(): v for k, v in papers_data["papers"].items() if isinstance(k, str) and isinstance(v, dict)
            }
        s_map: dict[str, Any] = {}
        if isinstance(sections_data, dict) and isinstance(sections_data.get("tallies"), dict):
            s_map = {
                k.lower(): v for k, v in sections_data["tallies"].items() if isinstance(k, str) and isinstance(v, dict)
            }

        out: list[Evidence] = []
        for raw_doi in dois:
            norm_doi = _normalize_doi(raw_doi)
            key = norm_doi.lower()
            t_obj = t_map.get(key)
            p_obj = p_map.get(key)
            s_obj = s_map.get(key)
            if t_obj is None and p_obj is None:
                out.append(
                    Evidence(
                        status=Status.NOT_FOUND,
                        question=question,
                        source_id=REST_SOURCE,
                        url=url,
                        provider=PROVIDER,
                        fields={"doi": norm_doi, "quota_bucket": "scite-public-tallies-free"},
                        limitations=LIMITATION,
                    )
                )
                continue

            t_dict = t_obj or {}
            doi_val = str(t_dict.get("doi") or (p_obj or {}).get("doi") or norm_doi)
            supporting = count(t_dict.get("supporting", 0), "Scite bulk supporting")
            contrasting = count(
                t_dict.get("contradicting", t_dict.get("contrasting", 0)),
                "Scite bulk contradicting",
            )
            mentioning = count(t_dict.get("mentioning", 0), "Scite bulk mentioning")
            unclassified = count(t_dict.get("unclassified", 0), "Scite bulk unclassified")
            total_cit = count(t_dict.get("total", 0), "Scite bulk total")
            citing_pubs = count(t_dict.get("citingPublications", 0), "Scite bulk citingPublications")

            fields: dict[str, Any] = {
                "doi": doi_val,
                "supporting": supporting,
                "contrasting": contrasting,
                "mentioning": mentioning,
                "unclassified": unclassified,
                "total_smart_citations": total_cit,
                "citing_publications": citing_pubs,
                "quota_bucket": "scite-public-tallies-free",
                "classification_provenance": "Scite ML citation classification",
            }
            pub_date: str | None = None
            if p_obj is not None:
                notices_raw = p_obj.get("editorialNotices")
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
                fields["title"] = p_obj.get("title")
                fields["journal"] = p_obj.get("journal")
                fields["year"] = p_obj.get("year")
                has_retracted_notice = any("retract" in str(n.get("status") or "").lower() for n in notices)
                fields["retracted"] = bool(p_obj.get("retracted", False)) or has_retracted_notice
                fields["editorial_notices"] = notices
                if p_obj.get("year") is not None:
                    pub_date = str(p_obj.get("year"))

            if s_obj is not None:
                intro = count(s_obj.get("introduction", 0), "Scite bulk section introduction")
                methods = count(s_obj.get("methods", 0), "Scite bulk section methods")
                results = count(s_obj.get("results", 0), "Scite bulk section results")
                discussion = count(s_obj.get("discussion", 0), "Scite bulk section discussion")
                other = count(s_obj.get("other", 0), "Scite bulk section other")
                sec_total = count(s_obj.get("total", 0), "Scite bulk section total")
                triage_label, rm_share = _classify_section_triage(
                    contrasting=contrasting,
                    intro=intro,
                    methods=methods,
                    results=results,
                    discussion=discussion,
                    total=sec_total,
                )
                fields["section_tallies"] = {
                    "introduction": intro,
                    "methods": methods,
                    "results": results,
                    "discussion": discussion,
                    "other": other,
                    "total": sec_total,
                }
                fields["results_methods_citation_share_computed"] = rm_share
                fields["section_triage_computed"] = triage_label

            out.append(
                Evidence(
                    status=Status.FOUND,
                    question=question,
                    source_id=REST_SOURCE,
                    url=f"https://scite.ai/reports/{doi_val}",
                    provider=PROVIDER,
                    publisher_date=pub_date,
                    fields=fields,
                    limitations=LIMITATION,
                )
            )
        return out
    except ShapeError as exc:
        return [
            error_record(
                exc,
                question=question,
                source_id=REST_SOURCE,
                url=url,
                provider=PROVIDER,
                fields={"dois_requested": len(dois)},
            )
        ]


def batch_tallies(
    client: Client,
    dois: list[str],
    *,
    include_papers: bool = False,
    include_sections: bool = False,
) -> list[Evidence]:
    """Screen up to 500 DOIs per request via unauthenticated public POST /tallies (+ optional /papers & /tallies/cited-by-sections) at 0 quota cost."""
    seen: set[str] = set()
    clean_dois: list[str] = []
    for d in dois:
        nd = _normalize_doi(d)
        if nd and nd.lower() not in seen:
            seen.add(nd.lower())
            clean_dois.append(nd)

    q = f"What are the Scite bulk Smart Citation tallies and editorial notices for {len(clean_dois)} DOI(s)?"
    if len(clean_dois) > MAX_BATCH_TOTAL:
        return [
            Evidence(
                status=Status.BLOCKED,
                question=q,
                source_id=REST_SOURCE,
                url=client._url(REST_SOURCE, "tallies"),
                provider=PROVIDER,
                fields={
                    "error": f"Refused: {len(clean_dois)} DOIs exceeds MAX_BATCH_TOTAL={MAX_BATCH_TOTAL}",
                    "dois_requested": len(clean_dois),
                },
                limitations=LIMITATION,
            )
        ]

    out: list[Evidence] = []
    for i in range(0, len(clean_dois), MAX_BATCH_CHUNK):
        chunk = clean_dois[i : i + MAX_BATCH_CHUNK]
        if client.dry_run:
            f = client.post(REST_SOURCE, "tallies", json=chunk)
            if include_papers:
                client.post(REST_SOURCE, "papers", json=chunk)
            if include_sections:
                client.post(REST_SOURCE, "tallies/cited-by-sections", json=chunk)
            out.append(
                Evidence(
                    status=Status.OUT_OF_SCOPE,
                    question=q,
                    source_id=REST_SOURCE,
                    url=f.url,
                    provider=PROVIDER,
                    fields={
                        "chunk_size": len(chunk),
                        "include_papers": include_papers,
                        "include_sections": include_sections,
                        "quota_bucket": "scite-public-tallies-free",
                    },
                    limitations=LIMITATION,
                )
            )
            continue

        f_tal = client.post(REST_SOURCE, "tallies", json=chunk)
        if f_tal.status is not Status.FOUND:
            out.append(_fail(f_tal, q, {"chunk_size": len(chunk)}, source_id=REST_SOURCE))
            continue

        p_data = None
        if include_papers:
            f_pap = client.post(REST_SOURCE, "papers", json=chunk)
            if f_pap.status is Status.FOUND:
                p_data = f_pap.data

        s_data = None
        if include_sections:
            f_sec = client.post(REST_SOURCE, "tallies/cited-by-sections", json=chunk)
            if f_sec.status is Status.FOUND:
                s_data = f_sec.data

        out.extend(parse_batch_tallies(f_tal.data, p_data, s_data, chunk, q, f_tal.url))
    return out


def _quarantine_excerpt(text: str, doi: str) -> str:
    """Sanitize terminal escape sequences and wrap untrusted full-text excerpts in <untrusted_data> tags."""
    cleaned = clean_for_terminal(text).strip()
    safe_doi = clean_for_terminal(doi).replace('"', "")
    return f'<untrusted_data source="scite" doi="{safe_doi}">{cleaned}</untrusted_data>'


def parse_excerpts(
    data: Any,
    doi_query: str,
    term_query: str,
    question: str,
    url: str,
    limit: int = DEFAULT_LIMIT,
) -> Evidence:
    """Pure parser for Scite MCP search_literature Mode C (in-paper fulltextExcerpts + citation snippets)."""
    try:
        inner = _unwrap_mcp_payload(data)
        hits = need(inner, "hits", "Scite excerpts response")
        if not isinstance(hits, list):
            raise ShapeError(f"Scite 'hits' is {type(hits).__name__}, not a list")
        if not hits:
            return Evidence(
                status=Status.NOT_FOUND,
                question=question,
                source_id=SOURCE,
                url=url,
                provider=PROVIDER,
                fields={"doi": doi_query, "query": term_query, "search_total": 0},
                limitations=LIMITATION,
            )
        if not isinstance(hits[0], dict):
            raise ShapeError("Scite hits[0] is not an object")
        hit = hits[0]
        base = _parse_hit(hit, question, url)
        doi_val = str(base.fields.get("doi") or doi_query)
        max_items = max(1, min(limit, MAX_LIMIT))

        raw_excerpts = hit.get("fulltextExcerpts")
        excerpts_out: list[str] = []
        if isinstance(raw_excerpts, list):
            for ex in raw_excerpts[:max_items]:
                if isinstance(ex, str) and ex.strip():
                    excerpts_out.append(_quarantine_excerpt(ex, doi_val))

        raw_citations = hit.get("citations")
        citations_out: list[dict[str, Any]] = []
        if isinstance(raw_citations, list):
            for cit in raw_citations[:max_items]:
                if isinstance(cit, dict):
                    snip = cit.get("snippet") or cit.get("quote")
                    citations_out.append(
                        {
                            "type": cit.get("type"),
                            "section": cit.get("section"),
                            "source_doi": cit.get("sourceDoi"),
                            "target_doi": cit.get("targetDoi"),
                            "snippet": _quarantine_excerpt(snip, str(cit.get("sourceDoi") or doi_val))
                            if isinstance(snip, str) and snip.strip()
                            else None,
                        }
                    )

        raw_abstract = hit.get("abstract")
        quarantined_abstract = (
            _quarantine_excerpt(raw_abstract, doi_val)
            if isinstance(raw_abstract, str) and raw_abstract.strip()
            else None
        )

        fields = dict(base.fields)
        fields["query"] = term_query
        fields["fulltext_excerpts"] = excerpts_out
        fields["abstract_quarantined"] = quarantined_abstract
        fields["content_denied"] = bool(hit.get("contentDenied", False))
        fields["access"] = hit.get("access") if isinstance(hit.get("access"), dict) else None
        fields["citation_snippets"] = citations_out
        fields["untrusted_data_quarantined"] = True
        fields["quota_bucket"] = "scite-mcp-2500"

        first_excerpt = (
            excerpts_out[0]
            if excerpts_out
            else (
                next((c["snippet"] for c in citations_out if c.get("snippet")), None)
                or quarantined_abstract
            )
        )
        return Evidence(
            status=Status.FOUND,
            question=question,
            source_id=SOURCE,
            url=base.url,
            provider=PROVIDER,
            publisher_date=base.publisher_date,
            fields=fields,
            excerpt=first_excerpt,
            limitations=LIMITATION,
        )
    except ShapeError as exc:
        return error_record(
            exc,
            question=question,
            source_id=SOURCE,
            url=url,
            provider=PROVIDER,
            fields={"doi": doi_query, "query": term_query},
        )


def excerpts(client: Client, doi: str, query: str, limit: int = DEFAULT_LIMIT) -> Evidence:
    """Retrieve in-paper full-text excerpts and citation snippets via Scite MCP Mode C (dois + term)."""
    norm_doi = _normalize_doi(doi)
    stripped = query.strip()
    max_items = max(1, min(limit, MAX_LIMIT))
    q = f"What full-text excerpts and citation statements in DOI '{norm_doi}' match '{stripped}'?"
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "search_literature",
            "arguments": {"dois": [norm_doi], "term": stripped, "limit": 1},
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
            fields={
                "doi": norm_doi,
                "planned_query": stripped,
                "planned_tool": "search_literature",
                "quota_bucket": "scite-mcp-2500",
            },
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
                "query": stripped,
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
            fields={"doi": norm_doi, "query": stripped, "error": cap_err},
            limitations=LIMITATION,
        )

    headers = {"Authorization": f"Bearer {token}"}
    f = client.post(SOURCE, "", json=payload, headers=headers)
    if f.status is not Status.FOUND:
        return _fail(f, q, {"doi": norm_doi, "query": stripped})
    return parse_excerpts(f.data, norm_doi, stripped, q, f.url, limit=max_items)


def parse_recommendations(
    data: Any,
    seed_doi: str,
    question: str,
    url: str,
    limit: int = DEFAULT_LIMIT,
) -> list[Evidence]:
    """Pure parser for Scite Partner REST GET /api_partner/recommend-papers/{doi}."""
    try:
        if not isinstance(data, dict):
            raise ShapeError(f"Scite recommendations response is {type(data).__name__}, not an object")
        if "detail" in data and "papers" not in data:
            raise ShapeError(f"Scite recommendations error: {data['detail']}")
        papers = need(data, "papers", "Scite recommendations response")
        if not isinstance(papers, list):
            raise ShapeError(f"Scite 'papers' is {type(papers).__name__}, not a list")
        if not papers:
            return [
                Evidence(
                    status=Status.NOT_FOUND,
                    question=question,
                    source_id=REST_SOURCE,
                    url=url,
                    provider=PROVIDER,
                    fields={"seed_doi": seed_doi, "recommendations_total": 0},
                    limitations=LIMITATION,
                )
            ]

        out: list[Evidence] = []
        max_items = max(1, min(limit, MAX_LIMIT))
        for idx, item in enumerate(papers[:max_items]):
            if not isinstance(item, dict):
                raise ShapeError(f"Scite recommendation {idx} is not an object")
            p_obj = item.get("paper") if isinstance(item.get("paper"), dict) else item
            doi_val = p_obj.get("doi")
            if not doi_val or not isinstance(doi_val, str):
                raise ShapeError(f"Scite recommendation {idx} missing string 'doi'")
            tally_obj = item.get("tally") if isinstance(item.get("tally"), dict) else (
                p_obj.get("tally") if isinstance(p_obj.get("tally"), dict) else {}
            )
            supporting = count(tally_obj.get("supporting", 0), "Scite rec supporting")
            contrasting = count(
                tally_obj.get("contradicting", tally_obj.get("contrasting", 0)),
                "Scite rec contradicting",
            )
            mentioning = count(tally_obj.get("mentioning", 0), "Scite rec mentioning")
            total_cit = count(tally_obj.get("total", 0), "Scite rec total")
            score_raw = item.get("score")
            rec_score = float(score_raw) if isinstance(score_raw, (int, float)) else None

            fields: dict[str, Any] = {
                "seed_doi": seed_doi,
                "doi": doi_val,
                "title": p_obj.get("title"),
                "journal": p_obj.get("journal"),
                "year": p_obj.get("year"),
                "recommendation_score": rec_score,
                "supporting": supporting,
                "contrasting": contrasting,
                "mentioning": mentioning,
                "total_smart_citations": total_cit,
                "quota_bucket": "scite-rest-partner-650",
                "classification_provenance": "Scite ML citation classification",
            }
            out.append(
                Evidence(
                    status=Status.FOUND,
                    question=question,
                    source_id=REST_SOURCE,
                    url=f"https://scite.ai/reports/{doi_val}",
                    provider=PROVIDER,
                    publisher_date=str(p_obj.get("year")) if p_obj.get("year") else None,
                    fields=fields,
                    limitations=LIMITATION,
                )
            )
        return out
    except ShapeError as exc:
        return [
            error_record(
                exc,
                question=question,
                source_id=REST_SOURCE,
                url=url,
                provider=PROVIDER,
                fields={"seed_doi": seed_doi},
            )
        ]


def recommend(client: Client, doi: str, limit: int = DEFAULT_LIMIT) -> list[Evidence]:
    """Recommend papers given a seed DOI via Scite Partner REST GET /api_partner/recommend-papers/{doi} (750/month bucket, capped at 20/day & 650/month)."""
    norm_doi = _normalize_doi(doi)
    max_items = max(1, min(limit, MAX_LIMIT))
    q = f"Which papers does Scite recommend based on seed DOI '{norm_doi}'?"
    path = f"api_partner/recommend-papers/{quote(norm_doi, safe='/')}"

    if client.dry_run:
        f = client.get(REST_SOURCE, path)
        return [
            Evidence(
                status=Status.OUT_OF_SCOPE,
                question=q,
                source_id=REST_SOURCE,
                url=f.url,
                provider=PROVIDER,
                fields={
                    "seed_doi": norm_doi,
                    "planned_endpoint": path,
                    "quota_bucket": "scite-rest-partner-650",
                },
                limitations=LIMITATION,
            )
        ]

    env_key = (os.environ.get("SCITE_API_KEY") or "").strip()
    token = env_key if (env_key and env_key != "your_key_here") else _resolve_bearer_token(allow_api_key=True)
    if not token:
        return [
            Evidence(
                status=Status.BLOCKED,
                question=q,
                source_id=REST_SOURCE,
                url=client._url(REST_SOURCE, path),
                provider=PROVIDER,
                fields={
                    "seed_doi": norm_doi,
                    "error": "Scite REST API key not found (set SCITE_API_KEY in .env)",
                },
                limitations=LIMITATION,
            )
        ]

    cap_err = _check_daily_cap(rest=True)
    if cap_err:
        return [
            Evidence(
                status=Status.BLOCKED,
                question=q,
                source_id=REST_SOURCE,
                url=client._url(REST_SOURCE, path),
                provider=PROVIDER,
                fields={"seed_doi": norm_doi, "error": cap_err},
                limitations=LIMITATION,
            )
        ]

    headers = {"Authorization": f"Bearer {token}"}
    f = client.get(REST_SOURCE, path, headers=headers)
    if f.status is not Status.FOUND:
        return [_fail(f, q, {"seed_doi": norm_doi}, source_id=REST_SOURCE)]
    return parse_recommendations(f.data, norm_doi, q, f.url, limit=max_items)

