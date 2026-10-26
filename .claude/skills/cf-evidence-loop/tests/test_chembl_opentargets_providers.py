"""Tests for EMBL-EBI ChEMBL and Open Targets Platform v4 GraphQL providers.

Covers offline fixture parsing, strict shape checks, empty result handling,
CC BY-SA 3.0 and CC0 1.0 licence and limitation statements, ClinGen/gnomAD
exclusion, CLI dispatch, and dry-run behaviour.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from evidence import cli
from evidence.http import Client
from evidence.providers import chembl, open_targets, scite
from evidence.record import Status

FX = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    return json.loads((FX / name).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# ChEMBL provider tests
# ---------------------------------------------------------------------------


def test_chembl_parse_molecules_from_fixture():
    data = load_fixture("chembl_molecule_ivacaftor.json")
    url = "https://www.ebi.ac.uk/chembl/api/data/molecule/search.json?q=ivacaftor&limit=5"
    recs = chembl.parse_molecules(data, "Which ChEMBL molecules match 'ivacaftor'?", url)

    assert len(recs) == 1
    r = recs[0]
    assert r.status is Status.FOUND
    assert r.source_id == "chembl"
    assert r.publisher_date == "2012"
    assert r.fields["molecule_chembl_id"] == "CHEMBL2010601"
    assert r.fields["pref_name"] == "IVACAFTOR"
    assert r.fields["max_phase"] == "4.0"
    assert r.fields["first_approval"] == 2012
    assert r.fields["atc_classifications"] == ["R07AX02"]
    assert r.fields["full_molformula"] == "C24H28N2O3"
    assert r.fields["alogp"] == "5.08"
    assert "Kalydeco" in r.fields["synonyms"]
    assert "VX-770" in r.fields["synonyms"]
    assert r.fields["search_total"] == 2
    assert r.fields["license"] == "CC BY-SA 3.0"
    assert "CC BY-SA 3.0" in r.fields["license_attribution"]
    assert "CC BY-SA 3.0" in r.limitations
    assert "clinical efficacy" in r.limitations


def test_chembl_parse_single_molecule():
    data = load_fixture("chembl_molecule_ivacaftor.json")["molecules"][0]
    url = "https://www.ebi.ac.uk/chembl/api/data/molecule/CHEMBL2010601.json"
    r = chembl.parse_molecule(data, "What is the ChEMBL molecule record for 'CHEMBL2010601'?", url)
    assert r.status is Status.FOUND
    assert r.fields["molecule_chembl_id"] == "CHEMBL2010601"
    assert r.url == "https://www.ebi.ac.uk/chembl/compound_report_card/CHEMBL2010601/"


def test_chembl_parse_activities_from_fixture():
    data = load_fixture("chembl_activities_cftr.json")
    url = "https://www.ebi.ac.uk/chembl/api/data/activity.json"
    recs = chembl.parse_activities(data, "What ChEMBL bioactivity assays match 'ivacaftor'?", url)

    assert len(recs) == 2
    r0 = recs[0]
    assert r0.status is Status.FOUND
    assert r0.source_id == "chembl"
    assert r0.publisher_date == "2014"
    assert r0.fields["activity_id"] == 15065262
    assert r0.fields["molecule_chembl_id"] == "CHEMBL2010601"
    assert r0.fields["target_chembl_id"] == "CHEMBL4051"
    assert r0.fields["assay_variant_mutation"] == "F508del,G551D"
    assert r0.fields["standard_type"] == "EC50"
    assert r0.fields["standard_value"] == "22.0"
    assert r0.fields["standard_units"] == "nM"
    assert r0.fields["pchembl_value"] == "7.66"
    assert r0.fields["search_total"] == 21
    assert r0.excerpt is not None and "Ussing chambers" in r0.excerpt
    assert r0.fields["license"] == "CC BY-SA 3.0"


def test_chembl_shape_errors():
    r_mol = chembl.parse_molecule(["bad"], "q", "https://example.org")
    assert r_mol.status is Status.ERROR
    assert "not an object" in r_mol.fields.get("shape_error", "")

    r_mol_missing = chembl.parse_molecule({"pref_name": "X"}, "q", "https://example.org")
    assert r_mol_missing.status is Status.ERROR
    assert "molecule_chembl_id" in r_mol_missing.fields.get("shape_error", "")

    recs_mols = chembl.parse_molecules({"molecules": "not_a_list"}, "q", "https://example.org")
    assert len(recs_mols) == 1 and recs_mols[0].status is Status.ERROR

    recs_acts = chembl.parse_activities(
        {"activities": [], "page_meta": {"total_count": "nan"}}, "q", "https://example.org"
    )
    assert len(recs_acts) == 1 and recs_acts[0].status is Status.ERROR


def test_chembl_empty_results_return_not_found():
    recs_mols = chembl.parse_molecules(
        {"molecules": [], "page_meta": {"total_count": 0}}, "q", "https://example.org"
    )
    assert len(recs_mols) == 1 and recs_mols[0].status is Status.NOT_FOUND
    assert recs_mols[0].fields["search_total"] == 0

    recs_acts = chembl.parse_activities(
        {"activities": [], "page_meta": {"total_count": 0}}, "q", "https://example.org"
    )
    assert len(recs_acts) == 1 and recs_acts[0].status is Status.NOT_FOUND
    assert recs_acts[0].fields["search_total"] == 0


def test_chembl_synonym_resolution_for_molecule_and_activities(monkeypatch):
    from test_conduct import FakeResponse, Script, make_client

    mol_fx = load_fixture("chembl_molecule_ivacaftor.json")
    act_fx = load_fixture("chembl_activities_cftr.json")
    empty_acts = {"activities": [], "page_meta": {"total_count": 0}}

    # 1. molecule('VX-770') resolves directly via molecule.json?molecule_synonyms__molecule_synonym__iexact=VX-770
    s_mol = Script([FakeResponse(200, body=mol_fx)])
    c_mol = make_client(monkeypatch, s_mol)
    recs_mol = chembl.molecule(c_mol, "VX-770", limit=3)
    assert len(recs_mol) == 1
    assert recs_mol[0].status is Status.FOUND
    assert recs_mol[0].fields["molecule_chembl_id"] == "CHEMBL2010601"
    assert recs_mol[0].fields["pref_name"] == "IVACAFTOR"
    assert len(s_mol.calls) == 1

    # 2. activities('VX-770') recognizes research code pattern, resolves synonym to CHEMBL2010601 first, and fetches CFTR activities in 2 calls
    s_code = Script(
        [
            FakeResponse(200, body=mol_fx),
            FakeResponse(200, body=act_fx),
        ]
    )
    c_code = make_client(monkeypatch, s_code)
    recs_code = chembl.activities(c_code, "VX-770", target_id="CHEMBL4051", limit=2)
    assert len(recs_code) == 2
    assert recs_code[0].status is Status.FOUND
    assert recs_code[0].fields["molecule_chembl_id"] == "CHEMBL2010601"
    assert recs_code[0].fields["standard_value"] == "22.0"
    assert len(s_code.calls) == 2

    # 3. activities('Kalydeco') (brand synonym) gets 0 hits on molecule_pref_name__iexact, resolves synonym to CHEMBL2010601, and fetches CFTR activities
    s_brand = Script(
        [
            FakeResponse(200, body=empty_acts),
            FakeResponse(200, body=mol_fx),
            FakeResponse(200, body=act_fx),
        ]
    )
    c_brand = make_client(monkeypatch, s_brand)
    recs_brand = chembl.activities(c_brand, "Kalydeco", target_id="CHEMBL4051", limit=2)
    assert len(recs_brand) == 2
    assert recs_brand[0].status is Status.FOUND
    assert recs_brand[0].fields["molecule_chembl_id"] == "CHEMBL2010601"
    assert len(s_brand.calls) == 3

    # 4. R2-01 regression test: if activity retry returns HTTP 500, it must return Status.ERROR (never mask as NOT_FOUND)
    s_err = Script(
        [
            FakeResponse(200, body=empty_acts),
            FakeResponse(200, body=mol_fx),
            FakeResponse(500, text="Internal Server Error"),
        ]
    )
    c_err = make_client(monkeypatch, s_err)
    recs_err = chembl.activities(c_err, "Kalydeco", target_id="CHEMBL4051", limit=2)
    assert len(recs_err) == 1
    assert recs_err[0].status is Status.ERROR
    assert recs_err[0].fields["http_status"] == 500


def test_chembl_dry_run(monkeypatch):
    monkeypatch.setenv("EVIDENCE_DRY_RUN", "1")
    client = Client()

    r_id = chembl.molecule(client, "CHEMBL2010601")
    assert len(r_id) == 1 and r_id[0].status is Status.OUT_OF_SCOPE
    assert "molecule/CHEMBL2010601.json" in r_id[0].url

    r_search = chembl.molecule(client, "ivacaftor", limit=3)
    assert len(r_search) == 1 and r_search[0].status is Status.OUT_OF_SCOPE
    assert "molecule/search.json" in r_search[0].url

    r_act = chembl.activities(client, "ivacaftor", target_id="CHEMBL4051", limit=4)
    assert len(r_act) == 1 and r_act[0].status is Status.OUT_OF_SCOPE
    assert "activity.json" in r_act[0].url


# ---------------------------------------------------------------------------
# Open Targets provider tests
# ---------------------------------------------------------------------------


def test_open_targets_parse_search_from_fixture():
    data = load_fixture("open_targets_search_cftr.json")
    url = "https://api.platform.opentargets.org/api/v4/graphql"
    recs = open_targets.parse_search(data, "Which Open Targets entities match 'CFTR'?", url)

    assert len(recs) == 3
    by_entity = {r.fields["entity"]: r for r in recs}

    tgt = by_entity["target"]
    assert tgt.status is Status.FOUND
    assert tgt.fields["id"] == "ENSG00000001626"
    assert tgt.fields["approved_symbol"] == "CFTR"
    assert "SM:Approved Drug" in tgt.fields["tractability_positive"]
    assert "PR:Small Molecule Binder" in tgt.fields["tractability_positive"]
    assert "AB:Clinical Precedence" not in tgt.fields["tractability_positive"]
    assert tgt.fields["safety_liabilities"] == ["adverse events"]
    assert tgt.fields["top_associated_diseases"][0]["disease_id"] == "MONDO_0009061"
    assert tgt.fields["top_associated_diseases"][0]["score"] == 0.9211
    assert tgt.url == "https://platform.opentargets.org/target/ENSG00000001626"

    dis = by_entity["disease"]
    assert dis.status is Status.FOUND
    assert dis.fields["id"] == "MONDO_0009061"
    assert dis.fields["top_associated_targets"][0]["approved_symbol"] == "CFTR"
    assert dis.excerpt is not None and "genetic disorder" in dis.excerpt
    assert dis.url == "https://platform.opentargets.org/disease/MONDO_0009061"

    drg = by_entity["drug"]
    assert drg.status is Status.FOUND
    assert drg.fields["id"] == "CHEMBL2010601"
    assert drg.fields["maximum_clinical_stage"] == "APPROVAL"
    assert drg.fields["mechanisms_of_action"][0]["action_type"] == "POSITIVE MODULATOR"
    assert drg.fields["top_adverse_events"][0]["log_lr"] == 9317.7
    assert drg.url == "https://platform.opentargets.org/drug/CHEMBL2010601"

    for r in recs:
        assert r.fields["license"] == "CC0 1.0"
        assert "CC0 1.0" in r.limitations
        assert "ClinGen and gnomAD excluded" in r.limitations


def test_open_targets_direct_entity_parsers_and_not_found():
    fx = load_fixture("open_targets_search_cftr.json")["data"]["search"]["hits"]
    url = "https://api.platform.opentargets.org/api/v4/graphql"

    r_tgt = open_targets.parse_target({"data": {"target": fx[0]["object"]}}, "q", url, "ENSG00000001626")
    assert r_tgt.status is Status.FOUND and r_tgt.fields["approved_symbol"] == "CFTR"

    r_dis = open_targets.parse_disease({"data": {"disease": fx[1]["object"]}}, "q", url, "MONDO_0009061")
    assert r_dis.status is Status.FOUND and r_dis.fields["name"] == "cystic fibrosis"

    r_drg = open_targets.parse_drug({"data": {"drug": fx[2]["object"]}}, "q", url, "CHEMBL2010601")
    assert r_drg.status is Status.FOUND and r_drg.fields["name"] == "IVACAFTOR"

    assert open_targets.parse_target({"data": {"target": None}}, "q", url, "ENSG00000000000").status is Status.NOT_FOUND
    assert open_targets.parse_disease({"data": {"disease": None}}, "q", url, "MONDO_0000000").status is Status.NOT_FOUND
    assert open_targets.parse_drug({"data": {"drug": None}}, "q", url, "CHEMBL0").status is Status.NOT_FOUND


def test_open_targets_excludes_clingen_and_gnomad():
    """Verify GraphQL queries never request ClinGen or gnomAD variant datasources."""
    for gql in (
        open_targets.TARGET_QUERY,
        open_targets.DISEASE_QUERY,
        open_targets.DRUG_QUERY,
        open_targets.SEARCH_QUERY,
    ):
        lower = gql.lower()
        assert "clingen" not in lower
        assert "gnomad" not in lower
        assert "credible" not in lower


def test_open_targets_graphql_errors_and_shape_checks():
    url = "https://api.platform.opentargets.org/api/v4/graphql"

    gql_err = {"errors": [{"message": "Cannot query field 'badField' on type 'Drug'."}]}
    recs = open_targets.parse_search(gql_err, "q", url)
    assert len(recs) == 1 and recs[0].status is Status.ERROR
    assert "GraphQL error" in recs[0].fields.get("shape_error", "")

    bad_total = {"data": {"search": {"total": "nan", "hits": []}}}
    recs_bad = open_targets.parse_search(bad_total, "q", url)
    assert len(recs_bad) == 1 and recs_bad[0].status is Status.ERROR

    empty = {"data": {"search": {"total": 0, "hits": []}}}
    recs_empty = open_targets.parse_search(empty, "q", url)
    assert len(recs_empty) == 1 and recs_empty[0].status is Status.NOT_FOUND


def test_open_targets_dry_run_and_cli_dispatch(monkeypatch, capsys):
    monkeypatch.setenv("EVIDENCE_DRY_RUN", "1")

    assert cli.main(["chembl", "CHEMBL2010601"]) == 0
    assert cli.main(["chembl-activity", "ivacaftor", "--target", "CHEMBL4051"]) == 0
    assert cli.main(["opentargets", "ENSG00000001626"]) == 0
    assert cli.main(["ot", "MONDO_0009061"]) == 0
    assert cli.main(["ot", "CHEMBL2010601"]) == 0
    assert cli.main(["ot", "cystic fibrosis"]) == 0

    assert cli.main(["chembl", "   "]) == 2
    assert cli.main(["chembl-activity", "   "]) == 2
    assert cli.main(["opentargets", "   "]) == 2
    assert cli.main(["scite", "   "]) == 2
    assert cli.main(["scite-search", "   "]) == 2
    capsys.readouterr()


# ---------------------------------------------------------------------------
# Scite Smart Citations provider tests
# ---------------------------------------------------------------------------


def test_scite_parse_tally_and_search_from_fixture():
    data = load_fixture("scite_mcp_tally.json")
    url = "https://api.scite.ai/mcp"

    r = scite.parse_tally(
        data,
        "10.1056/NEJMoa1908639",
        "What are the Scite supporting, contrasting, and mentioning citation tallies for DOI '10.1056/NEJMoa1908639'?",
        url,
    )
    assert r.status is Status.FOUND
    assert r.source_id == "scite-mcp"
    assert r.publisher_date == "2019-11-07"
    assert r.fields["doi"] == "10.1056/nejmoa1908639"
    assert r.fields["supporting"] == 109
    assert r.fields["contrasting"] == 5
    assert r.fields["mentioning"] == 1812
    assert r.fields["total_smart_citations"] == 1980
    assert r.fields["citing_publications"] == 2305
    assert r.fields["classification_provenance"] == "Scite ML citation classification"
    assert "[observed: Scite ML citation classification]" in r.limitations
    assert "machine-learning" in r.limitations

    recs = scite.parse_search(data, "elexacaftor", "Which publications in Scite match 'elexacaftor'?", url, limit=3)
    assert len(recs) == 1
    assert recs[0].status is Status.FOUND
    assert recs[0].fields["search_total"] == 1


def test_scite_blocked_when_unauthenticated_and_quota_capped(monkeypatch, tmp_path):
    monkeypatch.delenv("SCITE_API_KEY", raising=False)
    monkeypatch.setenv("SCITE_MCP_OAUTH_FILE", str(tmp_path / "missing_oauth.json"))
    client = Client()

    r_blocked = scite.tally(client, "10.1056/NEJMoa1908639")
    assert r_blocked.status is Status.BLOCKED
    assert "credentials not found" in r_blocked.fields.get("error", "")

    recs_blocked = scite.search(client, "vanzacaftor")
    assert len(recs_blocked) == 1 and recs_blocked[0].status is Status.BLOCKED

    # Quota cap enforcement
    monkeypatch.setenv("SCITE_API_KEY", "test-scite-token")
    usage_log = tmp_path / "scite_usage.jsonl"
    monkeypatch.setenv("SCITE_MCP_USAGE_LOG", str(usage_log))
    monkeypatch.setenv("SCITE_MCP_DAILY_CAP", "1")

    from test_conduct import FakeResponse, Script, make_client

    fx = load_fixture("scite_mcp_tally.json")
    s = Script([FakeResponse(200, body=fx)])
    c = make_client(monkeypatch, s)
    r_ok = scite.tally(c, "https://doi.org/10.1056/NEJMoa1908639")
    assert r_ok.status is Status.FOUND
    assert r_ok.fields["supporting"] == 109

    # Second call exceeds SCITE_MCP_DAILY_CAP=1 and is blocked before network
    r_capped = scite.tally(c, "10.1056/NEJMoa1908639")
    assert r_capped.status is Status.BLOCKED
    assert "daily quota cap reached" in r_capped.fields.get("error", "")


def test_scite_dry_run_and_shape_errors(monkeypatch, capsys):
    monkeypatch.setenv("EVIDENCE_DRY_RUN", "1")
    assert cli.main(["scite", "10.1056/NEJMoa1908639"]) == 0
    assert cli.main(["scite", "10.1056/NEJMoa1908639", "--rest"]) == 0
    assert cli.main(["scite-search", "vanzacaftor CFTR", "--limit", "2"]) == 0
    capsys.readouterr()

    r_rest = scite.parse_rest_tally(
        {
            "total": 1980,
            "supporting": 109,
            "contradicting": 5,
            "mentioning": 1812,
            "unclassified": 54,
            "doi": "10.1056/nejmoa1908639",
            "citingPublications": 2305,
        },
        "10.1056/NEJMoa1908639",
        "q",
        "https://api.scite.ai/tallies/10.1056/NEJMoa1908639",
    )
    assert r_rest.status is Status.FOUND
    assert r_rest.source_id == "scite-api"
    assert r_rest.fields["supporting"] == 109
    assert r_rest.fields["contrasting"] == 5
    assert r_rest.fields["mentioning"] == 1812
    assert r_rest.fields["unclassified"] == 54
    assert r_rest.fields["quota_bucket"] == "scite-public-tallies-free"

    r_err = scite.parse_tally({"error": {"message": "bad token"}}, "10.1000/x", "q", "https://api.scite.ai/mcp")
    assert r_err.status is Status.ERROR
    assert "bad token" in r_err.fields.get("shape_error", "")

    r_nf = scite.parse_tally({"hits": [], "total": 0}, "10.1000/x", "q", "https://api.scite.ai/mcp")
    assert r_nf.status is Status.NOT_FOUND


def test_scite_superpowers_batch_sections_excerpts_and_recommend(monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("EVIDENCE_DRY_RUN", "1")
    assert cli.main(["scite-batch", "10.1056/NEJMoa1908639", "10.1126/science.ade2216", "--papers", "--sections"]) == 0
    assert cli.main(["scite-sections", "10.1056/NEJMoa1908639"]) == 0
    assert cli.main(["scite-excerpts", "10.1056/NEJMoa1908639", "sweat chloride", "--limit", "3"]) == 0
    assert cli.main(["scite-recommend", "10.1056/NEJMoa1908639", "--limit", "3"]) == 0
    assert cli.main(["scite-batch", "   "]) == 2
    assert cli.main(["scite-sections", "   "]) == 2
    assert cli.main(["scite-excerpts", "10.1056/NEJMoa1908639", "   "]) == 2
    assert cli.main(["scite-recommend", "   "]) == 2
    capsys.readouterr()

    # 1. Section-weighted triage parser (0 quota cost)
    r_sec = scite.parse_rest_sections(
        {
            "total": 1980,
            "introduction": 701,
            "results": 87,
            "methods": 21,
            "discussion": 453,
            "other": 533,
            "doi": "10.1056/nejmoa1908639",
        },
        {
            "total": 1980,
            "supporting": 109,
            "contradicting": 5,
            "mentioning": 1812,
            "unclassified": 54,
            "doi": "10.1056/nejmoa1908639",
            "citingPublications": 2305,
        },
        "10.1056/NEJMoa1908639",
        "q",
        "https://api.scite.ai/tallies/cited-by-sections/10.1056/NEJMoa1908639",
    )
    assert r_sec.status is Status.FOUND
    assert r_sec.fields["section_tallies"]["results"] == 87
    assert r_sec.fields["section_tallies"]["methods"] == 21
    assert r_sec.fields["section_triage_computed"] == "EMPIRICAL_OR_METHODOLOGICAL_ATTENTION"
    assert r_sec.fields["quota_bucket"] == "scite-public-tallies-free"

    # 2. Bulk tallies + papers + sections parser (0 quota cost)
    batch_recs = scite.parse_batch_tallies(
        {
            "tallies": {
                "10.1056/nejmoa1908639": {
                    "total": 1980,
                    "supporting": 109,
                    "contradicting": 5,
                    "mentioning": 1812,
                    "unclassified": 54,
                    "doi": "10.1056/nejmoa1908639",
                    "citingPublications": 2305,
                }
            }
        },
        {
            "papers": {
                "10.1056/nejmoa1908639": {
                    "doi": "10.1056/nejmoa1908639",
                    "title": "Elexacaftor-Tezacaftor-Ivacaftor for Cystic Fibrosis",
                    "journal": "NEJM",
                    "year": 2019,
                    "retracted": False,
                    "editorialNotices": [],
                }
            }
        },
        {
            "tallies": {
                "10.1056/nejmoa1908639": {
                    "total": 1980,
                    "introduction": 701,
                    "results": 87,
                    "methods": 21,
                    "discussion": 453,
                    "other": 533,
                    "doi": "10.1056/nejmoa1908639",
                }
            }
        },
        ["10.1056/NEJMoa1908639", "10.1000/nonexistent"],
        "q",
        "https://api.scite.ai/tallies",
    )
    assert len(batch_recs) == 2
    assert batch_recs[0].status is Status.FOUND
    assert batch_recs[0].fields["retracted"] is False
    assert batch_recs[0].fields["section_triage_computed"] == "EMPIRICAL_OR_METHODOLOGICAL_ATTENTION"
    assert batch_recs[1].status is Status.NOT_FOUND

    # 3. Mode C full-text excerpts with <untrusted_data> quarantine & ANSI stripping
    ex_payload = {
        "result": {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "hits": [
                                {
                                    "doi": "10.1056/nejmoa1908639",
                                    "title": "ETI study",
                                    "year": 2019,
                                    "tally": {"supporting": 109, "contrasting": 5, "mentioning": 1812, "total": 1980},
                                    "fulltextExcerpts": ["\x1b[31mMean sweat chloride decreased by 41.8 mmol/L.\x1b[0m"],
                                    "citations": [
                                        {
                                            "snippet": "Replicated in real-world cohort.",
                                            "type": "supporting",
                                            "section": "Results",
                                            "sourceDoi": "10.1016/j.jcf.2021.01.001",
                                        }
                                    ],
                                }
                            ]
                        }
                    ),
                }
            ]
        }
    }
    r_ex = scite.parse_excerpts(ex_payload, "10.1056/NEJMoa1908639", "sweat chloride", "q", "https://api.scite.ai/mcp")
    assert r_ex.status is Status.FOUND
    assert r_ex.fields["untrusted_data_quarantined"] is True
    assert "\x1b" not in r_ex.fields["fulltext_excerpts"][0]
    assert r_ex.fields["fulltext_excerpts"][0].startswith('<untrusted_data source="scite" doi="10.1056/nejmoa1908639">')
    assert "41.8 mmol/L" in r_ex.fields["fulltext_excerpts"][0]

    # 4. Partner REST recommendations & monthly hard cap (650/month)
    rec_data = {
        "papers": [
            {
                "score": 0.942,
                "paper": {
                    "doi": "10.1056/nejmoa1908638",
                    "title": "Homozygous Phe508del ETI Trial",
                    "journal": "NEJM",
                    "year": 2019,
                    "tally": {"supporting": 88, "contradicting": 2, "mentioning": 940, "total": 1030},
                },
            }
        ]
    }
    recs_rec = scite.parse_recommendations(
        rec_data,
        "10.1056/NEJMoa1908639",
        "q",
        "https://api.scite.ai/api_partner/recommend-papers/10.1056/NEJMoa1908639",
    )
    assert len(recs_rec) == 1
    assert recs_rec[0].status is Status.FOUND
    assert recs_rec[0].fields["recommendation_score"] == 0.942
    assert recs_rec[0].fields["quota_bucket"] == "scite-rest-partner-650"

