"""Tests for UKRI Gateway to Research (GtR) API provider.

Covers offline parsing, shape checks (non-dict root, non-numeric totalSize,
non-list project), empty result handling, OGL licence and limitations statements,
and dry-run behaviour.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from evidence.http import Client
from evidence.providers import ukri_gtr
from evidence.record import Evidence, Status
from evidence.shape import ShapeError

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "ukri_gtr_projects.json"


def load_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_parse_projects_from_fixture():
    """Offline parsing of saved fixture returns valid Evidence records."""
    data = load_fixture()
    url = "https://gtr.ukri.org/gtr/api/projects?q=cystic+fibrosis&s=25"
    recs = ukri_gtr.parse_projects(data, "Which UKRI projects match 'cystic fibrosis'?", url)

    assert len(recs) == 3
    r0 = recs[0]

    assert r0.status is Status.FOUND
    assert r0.source_id == "ukri-gtr"
    assert r0.fields["project_id"] == "94470A9D-6805-479F-BAF8-EAB3496D32BC"
    assert "cystic fibrosis" in r0.fields["title"].lower()
    assert r0.fields["lead_funder"] == "MRC"
    assert r0.fields["grant_category"] == "Fellowship"
    assert r0.fields["grant_reference"] == "G0802448/1"
    assert r0.fields["status"] == "Closed"
    assert r0.fields["start"] == "2009-09-01"
    assert r0.fields["start_epoch_ms"] == 1251759600000
    assert r0.fields["search_total"] == 724
    assert r0.publisher_date == "2009-09-01"
    assert r0.excerpt is not None and len(r0.excerpt) > 0


def test_ogl_licence_and_limitations_stated():
    """Every record explicitly states Open Government Licence v3.0 and scope limitations."""
    data = load_fixture()
    url = "https://gtr.ukri.org/gtr/api/projects?q=cystic+fibrosis&s=25"
    recs = ukri_gtr.parse_projects(data, "question", url)

    for r in recs:
        # Check licence in fields
        assert r.fields["license"] == "Open Government Licence v3.0 (OGL)"
        assert "Open Government Licence v3.0" in r.fields["license_attribution"]

        # Check limitations explicitly mentions OGL and proposal scope
        assert "Open Government Licence v3.0" in r.limitations
        assert "UKRI Gateway to Research" in r.limitations
        assert "proposals" in r.limitations
        assert "clinical outcomes" in r.limitations or "regulatory approval" in r.limitations


def test_shape_check_rejects_non_dict_root():
    """Shape verification rejects non-dict root with Status.ERROR."""
    recs = ukri_gtr.parse_projects(["not", "a", "dict"], "question", "https://example.org")  # type: ignore
    assert len(recs) == 1
    assert recs[0].status is Status.ERROR
    assert "not an object" in recs[0].fields.get("shape_error", "")
    assert "Unexpected response shape" in recs[0].limitations


def test_shape_check_rejects_non_numeric_totalsize():
    """Shape verification rejects non-numeric totalSize with Status.ERROR."""
    data = {
        "totalSize": "not_a_number",
        "project": [],
    }
    recs = ukri_gtr.parse_projects(data, "question", "https://example.org")
    assert len(recs) == 1
    assert recs[0].status is Status.ERROR
    assert "totalSize" in recs[0].fields.get("shape_error", "")


def test_shape_check_rejects_non_list_project():
    """Shape verification rejects non-list 'project' field with Status.ERROR."""
    data = {
        "totalSize": 10,
        "project": "should_be_a_list",
    }
    recs = ukri_gtr.parse_projects(data, "question", "https://example.org")
    assert len(recs) == 1
    assert recs[0].status is Status.ERROR
    assert "'project' is str, not a list" in recs[0].fields.get("shape_error", "")


def test_shape_check_rejects_non_dict_project_item():
    """Shape verification rejects non-dict project items with Status.ERROR."""
    data = {
        "totalSize": 1,
        "project": ["not_a_project_dict"],
    }
    recs = ukri_gtr.parse_projects(data, "question", "https://example.org")
    assert len(recs) == 1
    assert recs[0].status is Status.ERROR
    assert "item 0 is str, not an object" in recs[0].fields.get("shape_error", "")


def test_empty_search_returns_not_found():
    """Empty search (totalSize == 0, project == []) returns Status.NOT_FOUND."""
    data = {
        "totalSize": 0,
        "project": [],
    }
    recs = ukri_gtr.parse_projects(data, "question", "https://example.org")
    assert len(recs) == 1
    assert recs[0].status is Status.NOT_FOUND
    assert recs[0].fields["search_total"] == 0
    assert recs[0].fields["license"] == "Open Government Licence v3.0 (OGL)"
    assert "Open Government Licence v3.0" in recs[0].limitations


def test_parse_single_project():
    """Single project lookup parsing."""
    data = load_fixture()
    proj0 = data["project"][0]
    rec = ukri_gtr.parse_project(proj0, "question", "https://gtr.ukri.org/gtr/api/projects/94470A9D-6805-479F-BAF8-EAB3496D32BC")
    assert rec.status is Status.FOUND
    assert rec.fields["project_id"] == "94470A9D-6805-479F-BAF8-EAB3496D32BC"
    assert rec.fields["lead_funder"] == "MRC"
    assert rec.fields["license"] == "Open Government Licence v3.0 (OGL)"


def test_dry_run_plans_request(monkeypatch):
    """Dry-run does not open network sockets and records planned request."""
    monkeypatch.setenv("EVIDENCE_DRY_RUN", "1")
    client = Client()
    assert client.dry_run is True

    recs = ukri_gtr.search(client, "cystic fibrosis")
    assert len(recs) == 1
    assert recs[0].status is Status.OUT_OF_SCOPE
    assert recs[0].fields["planned_query"] == "cystic fibrosis"
    assert len(client.planned) == 1
    method, url = client.planned[0]
    assert method == "GET"
    assert "https://gtr.ukri.org/gtr/api/projects?q=cystic+fibrosis" in url


def test_parse_projects_respects_limit_slicing():
    """Finding 1.3: parse_projects with limit=2 returns at most 2 projects while preserving search_total."""
    data = load_fixture()
    assert len(data["project"]) == 3
    assert data["totalSize"] == 724

    recs = ukri_gtr.parse_projects(data, "question", "https://example.org", limit=2)
    assert len(recs) == 2
    assert recs[0].fields["search_total"] == 724
    assert recs[1].fields["search_total"] == 724


def test_search_respects_limit_via_mock(monkeypatch):
    """Finding 1.3: search with limit=2 returns 2 projects even though API page size is 10."""
    from evidence.http import Fetch

    data = load_fixture()
    assert len(data["project"]) == 3

    client = Client()

    def mock_get(source_id, path, params=None, headers=None):
        assert params["s"] == 10  # GtR safe minimum page size
        return Fetch(Status.FOUND, 200, "https://gtr.ukri.org/gtr/api/projects", data=data)

    monkeypatch.setattr(client, "get", mock_get)

    recs = ukri_gtr.search(client, "cystic fibrosis", limit=2)
    assert len(recs) == 2
    assert recs[0].fields["search_total"] == 724

