"""Tests for paper-trail layer providers: Unpaywall and Semantic Scholar.

Deterministic unit and fixture tests verifying:
- Unpaywall OA location extraction, not_found, malformed shape, missing EVIDENCE_CONTACT.
- Semantic Scholar citation graph summary extraction, not_found, malformed shape.
- Strict conduct rule: EVIDENCE_CONTACT used for Unpaywall only, never sent to Semantic Scholar.
- Redaction of email parameter from URLs and records (zero leak of operator email).
- Positive controls: mutations / deletions trigger expected shape errors or validation failures.
- CLI subcommands: unpaywall, s2, semantic-scholar, paper-trail, paper.
"""

from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Enable direct execution via both pytest and python -m unittest
scripts_path = Path(__file__).resolve().parents[1] / "scripts"
if str(scripts_path) not in sys.path:
    sys.path.insert(0, str(scripts_path))

import pytest
from evidence import catalog, cli, guardrails, http
from evidence.http import PROJECT_UA, Client, Fetch
from evidence.providers import crossref, semantic_scholar, unpaywall
from evidence.record import Evidence, Status
from evidence.shape import ShapeError

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    with (FIXTURES_DIR / name).open("r", encoding="utf-8") as f:
        return json.load(f)


# ==============================================================================
# Unpaywall Provider Tests
# ==============================================================================

def test_unpaywall_parse_found():
    """Unpaywall parse extracts OA location, status, license, and metadata from fixture."""
    data = load_fixture("unpaywall_ng2745.json")
    rec = unpaywall.parse_unpaywall(
        data,
        "10.1038/ng.2745",
        "What OA locations exist for 10.1038/ng.2745?",
        "https://api.unpaywall.org/v2/10.1038/ng.2745?email=test@example.org",
    )

    assert rec.status is Status.FOUND
    assert rec.source_id == "unpaywall"
    assert rec.publisher_date == "2013"
    assert rec.fields["doi"] == "10.1038/ng.2745"
    assert rec.fields["is_oa"] is True
    assert rec.fields["oa_status"] == "green"
    assert rec.fields["journal_name"] == "Nature Genetics"
    assert rec.fields["oa_locations_count"] >= 1

    best_oa = rec.fields["best_oa_location"]
    assert isinstance(best_oa, dict)
    assert best_oa["url"] == "https://www.ncbi.nlm.nih.gov/pmc/articles/3874936"
    assert best_oa["host_type"] == "repository"
    assert best_oa["repository_institution"] == "National Institutes of Health"
    assert best_oa["version"] == "submittedVersion"

    assert "Unpaywall" in rec.limitations
    assert len(rec.limitations) >= 15
    assert guardrails.validate_evidence_record(rec) == []


def test_unpaywall_redacts_email_in_record():
    """Operator email must be redacted in the record's URL so it never enters ledgers or commits."""
    data = load_fixture("unpaywall_ng2745.json")
    secret_email = "diego-secret-operator@senseiewok.ai"
    raw_url = f"https://api.unpaywall.org/v2/10.1038/ng.2745?email={secret_email}"

    rec = unpaywall.parse_unpaywall(
        data,
        "10.1038/ng.2745",
        "What OA locations exist?",
        raw_url,
    )

    assert secret_email not in rec.url
    assert "email=<redacted>" in rec.url
    assert secret_email not in rec.to_json()
    assert secret_email not in str(rec.fields)


def test_unpaywall_missing_contact_fails_closed():
    """When EVIDENCE_CONTACT is unset outside dry-run, lookup returns Status.ERROR and refuses network."""
    client = Client(contact=None)
    with patch.dict(os.environ, {}, clear=True):
        rec = unpaywall.lookup(client, "10.1038/ng.2745", contact=None)

    assert rec.status is Status.ERROR
    assert "EVIDENCE_CONTACT not set" in rec.fields["error"]
    assert "Unpaywall" in rec.limitations


def test_unpaywall_dry_run_uses_placeholder():
    """Dry-run mode plans the request with synthetic contact and redacts in the planned URL."""
    with patch.dict(os.environ, {"EVIDENCE_DRY_RUN": "1"}):
        client = Client(contact=None)
        rec = unpaywall.lookup(client, "10.1038/ng.2745")

    assert rec.status is Status.OUT_OF_SCOPE
    assert "email=<redacted>" in rec.url


def test_unpaywall_not_found():
    """Unpaywall 404 response parses to Status.NOT_FOUND."""
    not_found_data = {"HTTP_status_code": 404, "message": "DOI not found"}
    rec = unpaywall.parse_unpaywall(
        not_found_data,
        "10.9999/nosuchdoi",
        "What OA locations exist?",
        "https://api.unpaywall.org/v2/10.9999/nosuchdoi?email=test@example.org",
    )
    assert rec.status is Status.NOT_FOUND
    assert rec.fields["doi"] == "10.9999/nosuchdoi"
    assert "not found" in rec.limitations.lower()


def test_unpaywall_malformed_shape_raises_or_returns_error():
    """Malformed Unpaywall response missing DOI or non-dict produces a shape error."""
    with pytest.raises(ShapeError):
        unpaywall.parse_unpaywall(
            "not-a-dict",
            "10.1038/ng.2745",
            "q",
            "u",
        )

    # Missing required 'doi' key in dict
    rec = unpaywall.parse_unpaywall(
        {"title": "Some Title without DOI"},
        "10.1038/ng.2745",
        "q",
        "u",
    )
    assert rec.status is Status.ERROR
    assert "shape_error" in rec.fields


# ==============================================================================
# Semantic Scholar Provider Tests
# ==============================================================================

def test_semantic_scholar_parse_found():
    """Semantic Scholar parse extracts citation counts and graph summary from fixture."""
    data = load_fixture("s2_ng2745.json")
    rec = semantic_scholar.parse_paper(
        data,
        "10.1038/ng.2745",
        "What does S2 hold for 10.1038/ng.2745?",
        "https://api.semanticscholar.org/graph/v1/paper/DOI:10.1038/ng.2745",
    )

    assert rec.status is Status.FOUND
    assert rec.source_id == "semantic-scholar"
    assert rec.publisher_date == "2013"
    assert rec.fields["paper_id"] == "789d766eb8218cf6e6337c7740aee90f9c932eaf"
    assert rec.fields["doi"] == "10.1038/ng.2745"
    assert "Defining the disease liability" in rec.fields["title"]
    assert rec.fields["venue"] == "Nature Genetics"
    assert rec.fields["is_open_access"] is True

    graph = rec.fields["citation_graph_summary"]
    assert isinstance(graph, dict)
    assert graph["citation_count"] >= 600
    assert graph["influential_citation_count"] >= 0
    assert graph["reference_count"] >= 90
    assert isinstance(graph["sample_citing_papers"], list)
    assert isinstance(graph["sample_references"], list)
    assert len(graph["sample_citing_papers"]) > 0
    assert len(graph["sample_references"]) > 0

    first_citing = graph["sample_citing_papers"][0]
    assert "paper_id" in first_citing
    assert "title" in first_citing
    assert "year" in first_citing

    assert "Semantic Scholar" in rec.limitations
    assert len(rec.limitations) >= 15
    assert guardrails.validate_evidence_record(rec) == []


def test_semantic_scholar_never_sends_evidence_contact():
    """EVIDENCE_CONTACT is for Unpaywall only; Semantic Scholar requests MUST NOT send mailto: or email."""
    client = Client(contact="operator-private@senseiewok.ai")
    assert "operator-private@senseiewok.ai" in client.session.headers["User-Agent"]

    captured_headers = {}

    def mock_send(method, url, params, json, headers=None):
        nonlocal captured_headers
        captured_headers = headers or {}
        resp = MagicMock()
        resp.status_code = 200
        resp.url = url
        resp.text = json_dumps if (json_dumps := '{"paperId": "abc"}') else ""
        resp.json.return_value = {"paperId": "abc"}
        return resp

    with patch.object(client, "_send", side_effect=mock_send):
        semantic_scholar.paper(client, "10.1038/ng.2745")

    # Header passed to request overrides session User-Agent: no mailto!
    assert "User-Agent" in captured_headers
    assert captured_headers["User-Agent"] == PROJECT_UA
    assert "mailto:" not in captured_headers["User-Agent"]
    assert "operator-private" not in captured_headers["User-Agent"]


def test_semantic_scholar_optional_api_key():
    """Optional S2_API_KEY is read at runtime if present, never required or committed."""
    client = Client(contact=None)
    captured_headers = {}

    def mock_send(method, url, params, json, headers=None):
        nonlocal captured_headers
        captured_headers = headers or {}
        resp = MagicMock()
        resp.status_code = 200
        resp.url = url
        resp.text = '{"paperId": "abc"}'
        resp.json.return_value = {"paperId": "abc"}
        return resp

    # 1. Without S2_API_KEY
    with patch.dict(os.environ, {}, clear=True):
        with patch.object(client, "_send", side_effect=mock_send):
            semantic_scholar.paper(client, "10.1038/ng.2745")
        assert "x-api-key" not in captured_headers

    # 2. With S2_API_KEY
    with patch.dict(os.environ, {"S2_API_KEY": "synthetic-runtime-key"}):
        with patch.object(client, "_send", side_effect=mock_send):
            rec = semantic_scholar.paper(client, "10.1038/ng.2745")
        assert captured_headers.get("x-api-key") == "synthetic-runtime-key"
        assert "synthetic-runtime-key" not in rec.to_json()


def test_semantic_scholar_not_found():
    """Semantic Scholar 404 or error response parses to Status.NOT_FOUND."""
    rec = semantic_scholar.parse_paper(
        {"error": "Paper not found"},
        "10.9999/nosuchpaper",
        "q",
        "https://api.semanticscholar.org/graph/v1/paper/DOI:10.9999/nosuchpaper",
    )
    assert rec.status is Status.NOT_FOUND
    assert rec.fields["doi"] == "10.9999/nosuchpaper"


def test_semantic_scholar_malformed_shape():
    """Malformed Semantic Scholar response raises or returns error record."""
    with pytest.raises(ShapeError):
        semantic_scholar.parse_paper("not-a-dict", "10.1038/ng.2745", "q", "u")

    rec = semantic_scholar.parse_paper(
        {"title": "Missing paperId"},
        "10.1038/ng.2745",
        "q",
        "u",
    )
    assert rec.status is Status.ERROR
    assert "shape_error" in rec.fields


# ==============================================================================
# Positive Controls & Mutation Tests
# ==============================================================================

def test_mutation_positive_control_unpaywall_missing_best_oa():
    """Removing best_oa_location leaves it as None (never stringified null) and sets closed/no-url excerpt."""
    data = load_fixture("unpaywall_ng2745.json")
    mutated = dict(data)
    mutated["best_oa_location"] = None
    mutated["is_oa"] = False
    mutated["oa_status"] = "closed"

    rec = unpaywall.parse_unpaywall(mutated, "10.1038/ng.2745", "q", "u")
    assert rec.status is Status.FOUND
    assert rec.fields["best_oa_location"] is None
    assert rec.fields["is_oa"] is False
    assert rec.fields["oa_status"] == "closed"
    assert rec.excerpt == "Open Access status: closed"
    assert guardrails.validate_evidence_record(rec) == []


def test_mutation_positive_control_prohibited_stringified_null():
    """Injecting stringified 'null' or 'none' triggers guardrail violation."""
    rec = Evidence(
        status=Status.FOUND,
        question="What is this DOI?",
        source_id="unpaywall",
        url="https://api.unpaywall.org/v2/10.1038/ng.2745",
        provider="unpaywall/0.1",
        fields={"doi": "10.1038/ng.2745", "license": "null"},
        limitations="Unpaywall indexes open access metadata only.",
    )
    errors = guardrails.validate_evidence_record(rec)
    assert any("prohibited stringified null" in e for e in errors)


def test_mutation_positive_control_s2_non_numeric_citation_count():
    """Mutating S2 citationCount to a non-numeric string triggers ShapeError."""
    data = load_fixture("s2_ng2745.json")
    mutated = dict(data)
    mutated["citationCount"] = "one-thousand-citations"

    with pytest.raises(ShapeError) as exc_info:
        semantic_scholar.parse_paper(mutated, "10.1038/ng.2745", "q", "u")
    assert "not a number" in str(exc_info.value)


# ==============================================================================
# CLI Integration Tests
# ==============================================================================

def _planned_urls(stderr_text: str) -> list[str]:
    urls: list[str] = []
    for line in stderr_text.splitlines():
        prefix = "planned: GET "
        if line.startswith(prefix):
            urls.append(line[len(prefix) :].strip())
    return urls


def test_cli_unpaywall_dry_run(capsys):
    """CLI unpaywall subcommand executes in dry-run mode and lists planned URL."""
    from urllib.parse import urlparse

    with patch.dict(os.environ, {"EVIDENCE_DRY_RUN": "1"}):
        ret = cli.main(["unpaywall", "10.1038/ng.2745", "--contact", "test@example.org"])
    assert ret == 0
    err = capsys.readouterr().err
    parsed = [urlparse(u) for u in _planned_urls(err)]
    assert any(
        p.scheme == "https"
        and p.hostname == "api.unpaywall.org"
        and p.path == "/v2/10.1038/ng.2745"
        and p.query == "email=<redacted>"
        for p in parsed
    )


def test_cli_s2_dry_run(capsys):
    """CLI s2 subcommand executes in dry-run mode and lists planned S2 URL."""
    from urllib.parse import urlparse

    with patch.dict(os.environ, {"EVIDENCE_DRY_RUN": "1"}):
        ret = cli.main(["s2", "10.1038/ng.2745"])
    assert ret == 0
    err = capsys.readouterr().err
    parsed = [urlparse(u) for u in _planned_urls(err)]
    assert any(
        p.scheme == "https"
        and p.hostname == "api.semanticscholar.org"
        and p.path == "/graph/v1/paper/DOI:10.1038/ng.2745"
        for p in parsed
    )


def test_cli_paper_trail_dry_run(capsys):
    """CLI paper-trail subcommand plans Crossref, Unpaywall, and Semantic Scholar requests."""
    from urllib.parse import urlparse

    with patch.dict(os.environ, {"EVIDENCE_DRY_RUN": "1"}):
        ret = cli.main(["paper-trail", "10.1038/ng.2745", "--contact", "test@example.org"])
    assert ret == 0
    err = capsys.readouterr().err
    parsed = [urlparse(u) for u in _planned_urls(err)]
    hosts = {p.hostname for p in parsed if p.scheme == "https"}
    assert "api.crossref.org" in hosts
    assert "api.unpaywall.org" in hosts
    assert "api.semanticscholar.org" in hosts
    assert any(p.hostname == "api.unpaywall.org" and p.query == "email=<redacted>" for p in parsed)


def test_cli_blank_queries_rejected(capsys):
    """Blank or whitespace-only DOIs for unpaywall and s2 are rejected before network."""
    ret_u = cli.main(["unpaywall", "   "])
    assert ret_u == 2
    err_u = capsys.readouterr().err
    assert "cannot be blank or whitespace-only" in err_u

    ret_s = cli.main(["s2", "   "])
    assert ret_s == 2
    err_s = capsys.readouterr().err
    assert "cannot be blank or whitespace-only" in err_s


class TestPaperTrailProviders(unittest.TestCase):
    """Standard unittest wrapper for CI runners that execute without pytest."""

    def test_unpaywall_parse_found(self):
        test_unpaywall_parse_found()

    def test_unpaywall_redacts_email_in_record(self):
        test_unpaywall_redacts_email_in_record()

    def test_unpaywall_missing_contact_fails_closed(self):
        test_unpaywall_missing_contact_fails_closed()

    def test_unpaywall_dry_run_uses_placeholder(self):
        test_unpaywall_dry_run_uses_placeholder()

    def test_unpaywall_not_found(self):
        test_unpaywall_not_found()

    def test_unpaywall_malformed_shape_raises_or_returns_error(self):
        test_unpaywall_malformed_shape_raises_or_returns_error()

    def test_semantic_scholar_parse_found(self):
        test_semantic_scholar_parse_found()

    def test_semantic_scholar_never_sends_evidence_contact(self):
        test_semantic_scholar_never_sends_evidence_contact()

    def test_semantic_scholar_optional_api_key(self):
        test_semantic_scholar_optional_api_key()

    def test_semantic_scholar_not_found(self):
        test_semantic_scholar_not_found()

    def test_semantic_scholar_malformed_shape(self):
        test_semantic_scholar_malformed_shape()

    def test_mutation_positive_control_unpaywall_missing_best_oa(self):
        test_mutation_positive_control_unpaywall_missing_best_oa()

    def test_mutation_positive_control_prohibited_stringified_null(self):
        test_mutation_positive_control_prohibited_stringified_null()

    def test_mutation_positive_control_s2_non_numeric_citation_count(self):
        test_mutation_positive_control_s2_non_numeric_citation_count()


if __name__ == "__main__":
    unittest.main()
