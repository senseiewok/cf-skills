"""Offline tests for the EMA medicines provider (ema-medicines-json).

Verifies marketing authorisation date, status, limitations, positive control,
and strict offline execution without network connection.
"""

from __future__ import annotations

import json
import socket
from pathlib import Path
from unittest.mock import patch

import pytest

from evidence.providers import ema
from evidence.record import Evidence, Status

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "ema_medicines_slice.json"


def load_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_no_network_modules_imported():
    """ema provider must be pure offline file reader and never import network clients."""
    import sys

    # ema.py itself must not import http, requests, or urllib
    with open(ema.__file__, "r", encoding="utf-8") as f:
        src = f.read()
    assert "import requests" not in src
    assert "import urllib" not in src
    assert "from ..http" not in src
    assert "import socket" not in src


def test_zero_network_calls_during_lookup(monkeypatch, tmp_path):
    """Enforce that lookup never opens any socket or network connection."""
    def fail_socket(*args, **kwargs):
        raise RuntimeError("Network socket attempted during offline EMA lookup!")

    monkeypatch.setattr(socket, "socket", fail_socket)

    rec = ema.lookup("Kaftrio", file_path=FIXTURE_PATH)
    assert rec.status is Status.FOUND
    assert rec.publisher_date == "2020-08-21"


def test_known_authorised_products_dates_and_status():
    """A known authorised product returns its marketing authorisation date and status."""
    data = load_fixture()

    # Kaftrio: authorised 2020-08-21 (21/08/2020 in EMA report)
    rec_k = ema.parse(data, "Kaftrio", "question", file_timestamp="2026-10-04T18:02:25Z")
    assert rec_k.status is Status.FOUND
    assert rec_k.status == Status.OK  # Status.OK alias compatibility
    assert rec_k.publisher_date == "2020-08-21"
    assert rec_k.fields["marketing_authorisation_date"] == "2020-08-21"
    assert rec_k.fields["marketing_authorisation_date_raw"] == "21/08/2020"
    assert rec_k.fields["medicine_status"] == "Authorised"
    assert rec_k.fields["name_of_medicine"] == "Kaftrio"
    assert rec_k.fields["active_substance"] == "ivacaftor;tezacaftor;elexacaftor"
    assert rec_k.fields["inn"] == "ivacaftor;tezacaftor;elexacaftor"
    assert rec_k.fields["ema_product_number"] == "EMEA/H/C/005269"
    assert rec_k.fields["category"] == "Human"
    assert rec_k.fields["european_commission_decision_date"] == "2026-07-23"
    assert rec_k.fields["revision_number"] == "34"
    assert rec_k.fields["therapeutic_area"] == "Cystic Fibrosis"
    assert "Kaftrio" in (rec_k.excerpt or "")

    # Orkambi: authorised 2015-11-19 (19/11/2015 in EMA report)
    rec_o = ema.parse(data, "Orkambi", "question", file_timestamp="2026-10-04T18:02:25Z")
    assert rec_o.status is Status.FOUND
    assert rec_o.publisher_date == "2015-11-19"
    assert rec_o.fields["marketing_authorisation_date"] == "2015-11-19"
    assert rec_o.fields["medicine_status"] == "Authorised"
    assert rec_o.fields["ema_product_number"] == "EMEA/H/C/003954"

    # Kalydeco: authorised 2012-07-23 (23/07/2012 in EMA report)
    rec_kal = ema.parse(data, "Kalydeco", "question", file_timestamp="2026-10-04T18:02:25Z")
    assert rec_kal.status is Status.FOUND
    assert rec_kal.publisher_date == "2012-07-23"
    assert rec_kal.fields["medicine_status"] == "Authorised"

    # Symkevi: authorised 2018-10-31 (31/10/2018 in EMA report)
    rec_s = ema.parse(data, "Symkevi", "question", file_timestamp="2026-10-04T18:02:25Z")
    assert rec_s.status is Status.FOUND
    assert rec_s.publisher_date == "2018-10-31"
    assert rec_s.fields["medicine_status"] == "Authorised"


def test_missing_product_returns_not_found():
    """A missing product returns not_found."""
    data = load_fixture()
    rec = ema.parse(data, "UnknownMedicine12345", "question", file_timestamp="2026-10-04T18:02:25Z")
    assert rec.status is Status.NOT_FOUND
    assert "No medicine matching 'UnknownMedicine12345' found" in rec.limitations


def test_positive_control_deleting_record_causes_failure():
    """Mandatory positive control: delete the record from the fixture and the test must fail."""
    data = load_fixture()

    # Baseline: Kaftrio is present and FOUND
    rec_before = ema.parse(data, "Kaftrio", "question", file_timestamp="2026-10-04T18:02:25Z")
    assert rec_before.status is Status.FOUND

    # Remove Kaftrio from the data slice
    tampered_items = [
        item for item in data["data"]
        if (item.get("name_of_medicine") or "").strip().lower() != "kaftrio"
    ]
    assert len(tampered_items) == len(data["data"]) - 1

    tampered_data = {
        "meta": data["meta"],
        "data": tampered_items,
    }

    # With the record deleted, lookup must return NOT_FOUND
    rec_after = ema.parse(tampered_data, "Kaftrio", "question", file_timestamp="2026-10-04T18:02:25Z")
    assert rec_after.status is Status.NOT_FOUND

    # Direct proof that an assertion expecting FOUND fails when the record is deleted
    with pytest.raises(AssertionError):
        assert rec_after.status is Status.FOUND


def test_limitations_name_ema_and_file_timestamp():
    """Every record's limitations name EMA as the source and the file's own last-updated timestamp."""
    data = load_fixture()
    ts = data["meta"]["timestamp"]
    assert ts == "2026-10-04T18:02:25Z"

    # Found record
    rec_found = ema.parse(data, "Kaftrio", "question", file_timestamp=ts)
    assert "EMA" in rec_found.limitations or "European Medicines Agency" in rec_found.limitations
    assert ts in rec_found.limitations
    assert rec_found.fields["report_timestamp"] == ts

    # Not found record
    rec_nf = ema.parse(data, "NonExistentDrug", "question", file_timestamp=ts)
    assert "EMA" in rec_nf.limitations or "European Medicines Agency" in rec_nf.limitations
    assert ts in rec_nf.limitations


def test_file_lookup_with_explicit_path():
    """ema.lookup works with an explicit file_path."""
    rec = ema.lookup("Orkambi", file_path=FIXTURE_PATH)
    assert rec.status is Status.FOUND
    assert rec.publisher_date == "2015-11-19"
    assert rec.fields["name_of_medicine"] == "Orkambi"


def test_missing_file_returns_error(tmp_path):
    """Missing report file returns Status.ERROR with informative limitations."""
    non_existent = tmp_path / "does_not_exist.json"
    rec = ema.lookup("Kaftrio", file_path=non_existent)
    assert rec.status is Status.ERROR
    assert "not found" in rec.fields.get("error", "").lower()
    assert "European Medicines Agency" in rec.limitations


def test_corrupt_json_file_returns_error(tmp_path):
    """Corrupted JSON report file returns Status.ERROR."""
    corrupt = tmp_path / "corrupt.json"
    corrupt.write_text("not json at all {[]", encoding="utf-8")
    rec = ema.lookup("Kaftrio", file_path=corrupt)
    assert rec.status is Status.ERROR
    assert "European Medicines Agency" in rec.limitations


def test_invalid_shape_returns_error():
    """Non-dict root or non-list data returns Status.ERROR."""
    rec1 = ema.parse(["not", "a", "dict"], "Kaftrio", "question")  # type: ignore
    assert rec1.status is Status.ERROR

    rec2 = ema.parse({"meta": {}, "data": "not a list"}, "Kaftrio", "question")
    assert rec2.status is Status.ERROR


def test_empty_or_whitespace_drug_query_returns_not_found():
    """Finding 1.1: Empty or whitespace-only drug query must never match any medicine or return FOUND."""
    data = load_fixture()

    rec_empty_parse = ema.parse(data, "", "question")
    assert rec_empty_parse.status is Status.NOT_FOUND

    rec_space_parse = ema.parse(data, "   ", "question")
    assert rec_space_parse.status is Status.NOT_FOUND

    rec_empty_lookup = ema.lookup("", file_path=FIXTURE_PATH)
    assert rec_empty_lookup.status is Status.NOT_FOUND

    rec_space_lookup = ema.lookup("   ", file_path=FIXTURE_PATH)
    assert rec_space_lookup.status is Status.NOT_FOUND


def test_non_string_field_resilience():
    """Finding 1.2: Non-string values in EMA JSON fields must not crash with AttributeError."""
    malformed_data = {
        "meta": {"timestamp": "2026-10-04T18:02:25Z"},
        "data": [
            {
                "name_of_medicine": 12345,
                "category": None,
                "international_non_proprietary_name_common_name": ["list", "of", "names"],
                "active_substance": {"substance": "dict"},
                "marketing_authorisation_date": 20200821,
            },
            {
                "name_of_medicine": "TestMed",
                "category": "Human",
                "therapeutic_indication": 42,
            }
        ]
    }

    # Must parse without exception
    rec1 = ema.parse(malformed_data, "12345", "question")
    assert rec1.status is Status.NOT_FOUND

    rec2 = ema.parse(malformed_data, "TestMed", "question")
    assert rec2.status is Status.FOUND
    assert rec2.fields["name_of_medicine"] == "TestMed"


def test_token_and_substring_match_ranking():
    """Finding 1.4: Match ranking prioritises exact name > token > substring."""
    data = {
        "meta": {"timestamp": "2026-10-04T18:02:25Z"},
        "data": [
            {
                "name_of_medicine": "SubKaftrioExtra",
                "category": "Human",
                "marketing_authorisation_date": "01/01/2021",
            },
            {
                "name_of_medicine": "Kaftrio",
                "category": "Human",
                "marketing_authorisation_date": "21/08/2020",
            },
            {
                "name_of_medicine": "Other Kaftrio Product",
                "category": "Human",
                "marketing_authorisation_date": "01/01/2022",
            }
        ]
    }

    rec = ema.parse(data, "Kaftrio", "question")
    assert rec.status is Status.FOUND
    assert rec.fields["name_of_medicine"] == "Kaftrio"
    assert rec.publisher_date == "2020-08-21"

