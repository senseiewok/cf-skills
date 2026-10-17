"""Deterministic anti-hallucination and provenance guardrails test suite.

Tests:
1. Positive controls: validate_evidence_record passes with 0 errors across all 14 provider fixtures.
2. Negative controls: validate_evidence_record flags empty limitations (<15 chars), empty fields dict,
   and stringified nulls ('None', 'null', 'undefined') across top-level and nested structures.
3. Query validation: is_blank_query accurately identifies empty, whitespace, None, and non-string queries.
4. Grounding contract: constants present in briefs summary and text, footer preserved.
5. CLI rejection: cli.main refuses blank queries across subcommands with exit code 2 before network/file operations.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from evidence import briefs, cli, guardrails
from evidence.providers import (
    clinvar,
    crossref,
    datacommons,
    ema,
    europepmc,
    gnomad,
    myvariant,
    openalex,
    openfda,
    preprints,
    pubmed,
    reporter,
    trials,
    ukri_gtr,
)
from evidence.record import Evidence, Status

FX = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict | list:
    return json.loads((FX / name).read_text(encoding="utf-8"))


# ==============================================================================
# 1. Positive Controls: All 14 Providers via Fixtures
# ==============================================================================


def test_positive_control_all_14_providers():
    """Verify that parsed records from all 14 provider fixtures satisfy all guardrails."""
    records_by_provider: dict[str, list[Evidence]] = {}

    # 1. ClinVar
    records_by_provider["clinvar"] = clinvar.parse_summaries(
        load_fixture("clinvar_esummary.json"), "question", "https://example.test"
    )

    # 2. Crossref
    records_by_provider["crossref"] = [
        crossref.parse_work(load_fixture("crossref_work.json"), "question", "https://example.test")
    ] + crossref.parse_updates(
        load_fixture("crossref_updates_clean.json"), "10.1038/ng.2745", "question", "https://example.test"
    ) + crossref.parse_updates(
        load_fixture("crossref_updates_retracted.json"), "10.1016/S0140-6736(97)11096-0", "question", "https://example.test"
    )

    # 3. Data Commons
    records_by_provider["datacommons"] = [
        datacommons.parse_observation(
            load_fixture("datacommons_observation.json"), "country/USA", "Count_Person", "question", "https://example.test"
        )
    ]

    # 4. EMA
    records_by_provider["ema"] = [
        ema.parse(load_fixture("ema_medicines_slice.json"), "Kaftrio", "question", file_timestamp="2026-10-04T18:02:25Z")
    ]

    # 5. Europe PMC
    records_by_provider["europepmc"] = europepmc.parse_search(
        load_fixture("europepmc_search.json"), "question", "https://example.test"
    )

    # 6. gnomAD
    records_by_provider["gnomad"] = [
        gnomad.parse_gnomad_record(
            load_fixture("gnomad_variant.json"), "question", "https://example.test"
        )
    ]

    # 7. MyVariant.info
    records_by_provider["myvariant"] = [
        myvariant.parse_myvariant_record(
            load_fixture("myvariant_hit.json")["hits"][0], "question", "https://example.test"
        )
    ]

    # 8. OpenAlex
    records_by_provider["openalex"] = [
        openalex.parse_work(load_fixture("openalex_work.json"), "question", "https://example.test")
    ]

    # 9. openFDA
    records_by_provider["openfda"] = [
        openfda.parse_approval(load_fixture("openfda_drugsfda.json"), "TRIKAFTA", "question", "https://example.test"),
        openfda.parse_label(load_fixture("openfda_label.json"), "ALYFTREK", ("indications_and_usage",), "question", "https://example.test"),
    ]

    # 10. Preprints
    records_by_provider["preprints"] = preprints.parse_details(
        load_fixture("preprints_details.json"), "medrxiv", "question", "https://example.test"
    )

    # 11. PubMed
    records_by_provider["pubmed"] = pubmed.parse_summaries(
        load_fixture("pubmed_esummary.json"), "question", "https://example.test"
    )

    # 12. NIH RePORTER
    records_by_provider["reporter"] = reporter.parse_projects(
        load_fixture("reporter_projects.json"), "question", "https://example.test"
    )

    # 13. ClinicalTrials.gov
    records_by_provider["trials"] = trials.parse_studies(
        load_fixture("trials_study.json"), "question", "https://example.test"
    )

    # 14. UKRI Gateway to Research
    records_by_provider["ukri_gtr"] = ukri_gtr.parse_projects(
        load_fixture("ukri_gtr_projects.json"), "question", "https://example.test"
    )

    assert len(records_by_provider) == 14, "All 14 providers must be tested"

    for provider_name, recs in records_by_provider.items():
        assert len(recs) > 0, f"Provider {provider_name} yielded 0 records"
        for rec in recs:
            errors = guardrails.validate_evidence_record(rec)
            assert errors == [], f"Provider {provider_name} failed guardrails: {errors}"
            if rec.status == Status.FOUND:
                assert len(rec.limitations) >= 15
                assert len(rec.fields) > 0


# ==============================================================================
# 2. Negative Controls: validate_evidence_record
# ==============================================================================


def test_validate_record_rejects_non_evidence():
    errors = guardrails.validate_evidence_record({"status": "found"})  # type: ignore
    assert len(errors) == 1
    assert "expected Evidence instance" in errors[0]


def test_validate_record_rejects_empty_source():
    rec = Evidence(
        status=Status.FOUND,
        question="What is the dosage?",
        source_id="test_source",
        url="https://example.test",
        provider="test/0.1",
        fields={"val": 1},
        limitations="At least fifteen characters of limitations.",
    )
    rec.source_id = ""
    errors = guardrails.validate_evidence_record(rec)
    assert any("source/source_id must be a non-empty string" in e for e in errors)


def test_validate_record_rejects_empty_question():
    rec = Evidence(
        status=Status.FOUND,
        question="Valid question here?",
        source_id="test_source",
        url="https://example.test",
        provider="test/0.1",
        fields={"val": 1},
        limitations="At least fifteen characters of limitations.",
    )
    rec.question = "   "
    errors = guardrails.validate_evidence_record(rec)
    assert any("question must be a non-empty string" in e for e in errors)


def test_validate_record_rejects_short_limitations_on_found():
    rec = Evidence(
        status=Status.FOUND,
        question="Valid question?",
        source_id="test_source",
        url="https://example.test",
        provider="test/0.1",
        fields={"key": "value"},
        limitations="Valid fifteen char limit.",
    )
    rec.limitations = "too short"
    errors = guardrails.validate_evidence_record(rec)
    assert any("limitations must be a non-empty string with at least 15 characters" in e for e in errors)


def test_validate_record_rejects_empty_fields_on_found():
    rec = Evidence(
        status=Status.FOUND,
        question="Valid question?",
        source_id="test_source",
        url="https://example.test",
        provider="test/0.1",
        fields={"key": "value"},
        limitations="At least fifteen characters of limitations.",
    )
    rec.fields = {}
    errors = guardrails.validate_evidence_record(rec)
    assert any("fields must be a non-empty dict" in e for e in errors)


@pytest.mark.parametrize(
    "bad_value",
    ["None", "none", "NONE", "null", "NULL", "undefined", " undefined ", "\tNone\n"],
)
def test_validate_record_rejects_stringified_nulls_top_level(bad_value):
    rec = Evidence(
        status=Status.FOUND,
        question="Valid question?",
        source_id="test_source",
        url="https://example.test",
        provider="test/0.1",
        fields={"bad_field": bad_value},
        limitations="At least fifteen characters of limitations.",
    )
    errors = guardrails.validate_evidence_record(rec)
    assert any("prohibited stringified null value" in e for e in errors)


def test_validate_record_rejects_stringified_nulls_nested():
    rec = Evidence(
        status=Status.FOUND,
        question="Valid question?",
        source_id="test_source",
        url="https://example.test",
        provider="test/0.1",
        fields={
            "nested_dict": {"subfield": "null"},
            "nested_list": ["valid", "None"],
            "dict_in_list": [{"inner": "undefined"}],
        },
        limitations="At least fifteen characters of limitations.",
    )
    errors = guardrails.validate_evidence_record(rec)
    assert len(errors) == 3
    assert any("nested_dict.subfield" in e for e in errors)
    assert any("nested_list[1]" in e for e in errors)
    assert any("dict_in_list[0].inner" in e for e in errors)


def test_validate_record_allows_legitimate_phrases():
    """Legitimate descriptive text containing 'none' or 'null' as substrings must not be flagged."""
    rec = Evidence(
        status=Status.FOUND,
        question="Valid question?",
        source_id="test_source",
        url="https://example.test",
        provider="test/0.1",
        fields={
            "desc": "none of the participants experienced serious adverse effects",
            "stat": "the null hypothesis was rejected with p < 0.001",
            "state": "not stated",
        },
        limitations="At least fifteen characters of limitations.",
    )
    errors = guardrails.validate_evidence_record(rec)
    assert errors == []


# ==============================================================================
# 3. Blank Query Validation (is_blank_query)
# ==============================================================================


@pytest.mark.parametrize(
    "query",
    ["", " ", "   ", "\t", "\n", "\r\n", None, 123, [], {}, ()],
)
def test_is_blank_query_positive(query):
    assert guardrails.is_blank_query(query) is True


@pytest.mark.parametrize(
    "query",
    ["cystic fibrosis", "CFTR", "TRIKAFTA", " 10.1038/ng.2745 ", "a"],
)
def test_is_blank_query_negative(query):
    assert guardrails.is_blank_query(query) is False


# ==============================================================================
# 4. Grounding Contract & Brief Invariants
# ==============================================================================


def test_grounding_contract_constant():
    assert isinstance(guardrails.GROUNDING_CONTRACT, str)
    assert len(guardrails.GROUNDING_CONTRACT) > 30
    assert "GROUNDING CONTRACT" in guardrails.GROUNDING_CONTRACT
    assert "not stated" in guardrails.GROUNDING_CONTRACT


def test_grounding_contract_in_briefs():
    b = briefs.Brief(recipe="drug", subject="TESTDRUG")
    summary = b.summary()
    assert "grounding_contract" in summary["brief"]
    assert summary["brief"]["grounding_contract"] == guardrails.GROUNDING_CONTRACT

    text = b.text()
    assert guardrails.GROUNDING_CONTRACT in text
    assert text.rstrip().endswith(briefs.FOOTER)


# ==============================================================================
# 5. CLI Blank Query Rejection
# ==============================================================================


@pytest.mark.parametrize(
    "subcommand_args",
    [
        ["doi", "   "],
        ["retractions", "   "],
        ["approval", "   "],
        ["label", "   "],
        ["preprint", "medrxiv", "   "],
        ["preprints", "medrxiv", "   ", "2026-09-30"],
        ["variants", "   "],
        ["myvariant", "   "],
        ["gnomad", "   "],
        ["grants", "   "],
        ["pubmed", "   "],
        ["reviews", "   "],
        ["trial", "   "],
        ["trials", "   "],
        ["epmc", "   "],
        ["cited", "   "],
        ["population", "   "],
        ["openalex", "   "],
        ["openalex-search", "   "],
        ["ema", "   "],
        ["ukri", "   "],
        ["brief", "drug", "   "],
        ["read-page", "   "],
        ["cite-check", "   "],
    ],
)
def test_cli_rejects_blank_queries_without_network_or_io(subcommand_args, capsys):
    with patch("evidence.cli.Client") as mock_client, patch("evidence.page_reader.PageReader") as mock_reader:
        rc = cli.main(subcommand_args)
        assert rc == 2
        mock_client.assert_not_called()
        mock_reader.assert_not_called()
        captured = capsys.readouterr()
        assert "refused:" in captured.err
        assert "blank or whitespace" in captured.err or "empty or blank" in captured.err
