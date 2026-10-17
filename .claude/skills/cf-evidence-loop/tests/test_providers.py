"""Each provider's parse() on a saved response. No network."""

import json
from pathlib import Path

import pytest

from evidence.providers import (clinvar, crossref, datacommons, ema, europepmc, gnomad, myvariant, openalex, openfda,
                                preprints, pubmed, reporter, semantic_scholar, trials, ukri_gtr, unpaywall)
from evidence.record import Evidence, Status

FX = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FX / name).read_text(encoding="utf-8"))


def test_every_record_has_limitations():
    with pytest.raises(ValueError):
        Evidence(status=Status.FOUND, question="q", source_id="s", url="u", provider="p", limitations="")


def test_retracted_doi_yields_notices():
    recs = crossref.parse_updates(load("crossref_updates_retracted.json"), "10.1016/S0140-6736(97)11096-0", "q", "u")
    assert len(recs) == 2
    assert all(r.fields["clean"] is False for r in recs)
    assert {r.fields["notice_type"][0] for r in recs} == {"correction", "retraction"}
    assert {r.publisher_date for r in recs} == {"2004", "2010"}


def test_clean_doi_is_found_and_clean():
    recs = crossref.parse_updates(load("crossref_updates_clean.json"), "10.1038/ng.2745", "q", "u")
    assert len(recs) == 1 and recs[0].status is Status.FOUND
    assert recs[0].fields == {"doi": "10.1038/ng.2745", "update_notices": 0, "clean": True}
    assert "not conclusive" in recs[0].limitations


def test_work_metadata():
    r = crossref.parse_work(load("crossref_work.json"), "q", "u")
    assert r.fields["doi"] == "10.1038/ng.2745" and r.publisher_date == "2013"
    assert r.fields["authors"][0] == "Sosnay"


def test_approval_original_date():
    r = openfda.parse_approval(load("openfda_drugsfda.json"), "TRIKAFTA", "q", "u")
    assert r.status is Status.FOUND
    assert r.fields["application_number"] == "NDA212273"
    assert r.fields["original_approval"] == "2019-10-21" == r.publisher_date
    assert "US FDA only" in r.limitations


def test_approval_not_found():
    r = openfda.parse_approval({"results": []}, "NOSUCHDRUG", "q", "u")
    assert r.status is Status.NOT_FOUND


def test_label_excerpt_is_bounded():
    r = openfda.parse_label(load("openfda_label.json"), "ALYFTREK", ("indications_and_usage",), "q", "u")
    assert r.fields["set_id"] == "7e635909-c6fd-4f0d-ae77-cdff03653a20"
    assert r.publisher_date == "2026-08-26"
    assert r.excerpt and len(r.excerpt) <= openfda.EXCERPT_CHARS + 1
    assert "not any individual's eligibility" in r.limitations


def test_preprint_details_and_filter():
    recs = preprints.parse_details(load("preprints_details.json"), "medrxiv", "q", "u")
    assert len(recs) == 1 and recs[0].fields["doi"] == "10.1101/2025.02.14.25322057"
    assert "not peer reviewed" in recs[0].limitations
    assert preprints.parse_details(load("preprints_details.json"), "medrxiv", "q", "u", pattern=r"zebrafish") == []


def test_clinvar_classification():
    recs = clinvar.parse_summaries(load("clinvar_esummary.json"), "q", "u")
    by_acc = {r.fields["accession"]: r for r in recs}
    assert by_acc["VCV004072070"].fields["classification"] == "Pathogenic"
    assert "Phe508del" in by_acc["VCV004072070"].fields["title"]
    assert all("CFTR2" in r.limitations for r in recs)


def test_trial_record():
    recs = trials.parse_studies(load("trials_study.json"), "q", "u")
    assert len(recs) == 1
    f = recs[0].fields
    assert f["nct_id"] == "NCT05033080" and f["status"] == "COMPLETED" and f["phases"] == ["PHASE3"]
    assert f["start"] == "2021-09-14"
    assert "not evidence that an intervention works" in recs[0].limitations


def test_pubmed_summaries_and_ids():
    recs = pubmed.parse_summaries(load("pubmed_esummary.json"), "q", "u")
    by = {r.fields["pmid"]: r for r in recs}
    assert by["23974870"].fields["doi"] == "10.1038/ng.2745"
    assert "Systematic Review" in by["42781846"].fields["pub_types"]
    assert by["42781846"].fields["pmcid"] == "PMC13602365"


def test_review_term_scoping():
    assert pubmed.review_term("sickle cell disease").startswith("(sickle cell disease[tiab]) AND (systematic[sb]")
    assert pubmed.review_term("cystic fibrosis[MeSH]").startswith("cystic fibrosis[MeSH] AND")


def test_europepmc_lookup_fields():
    recs = europepmc.parse_search(load("europepmc_search.json"), "q", "u")
    assert len(recs) == 1
    f = recs[0].fields
    assert f["doi"] == "10.1001/jamanetworkopen.2020.1737" and f["year"] == "2020" and f["open_access"] is True
    assert isinstance(f["cited_by"], int) and f["cited_by"] > 0
    assert "differs from Crossref" in recs[0].limitations


def test_reporter_handles_null_dates():
    recs = reporter.parse_projects(load("reporter_projects.json"), "q", "u")
    assert len(recs) == 2
    assert all(r.publisher_date == "2025" for r in recs)
    assert all("NIH-funded projects only" in r.limitations for r in recs)


def test_datacommons_parse_observation_latest():
    r = datacommons.parse_observation(load("datacommons_observation.json"), "country/USA", "Count_Person", "q", "u")
    assert r.status is Status.FOUND
    assert r.publisher_date == "2025"
    assert r.fields["value"] == 341784857
    assert r.fields["measurement_method"] == "CensusPEPSurvey"
    assert r.fields["provenance_url"] == "https://www.census.gov/programs-surveys/popest.html"
    assert "Google Data Commons aggregate statistical observation" in r.limitations
    assert "CensusPEPSurvey" in r.limitations
    assert "2025" in r.limitations


def test_datacommons_parse_observation_by_year():
    r = datacommons.parse_observation(load("datacommons_observation.json"), "country/USA", "Count_Person", "q", "u", year="2024")
    assert r.status is Status.FOUND
    assert r.publisher_date == "2024"
    assert r.fields["value"] == 340000000
    assert "CensusPEPSurvey" in r.limitations
    assert "2024" in r.limitations


def test_datacommons_parse_observation_not_found():
    r = datacommons.parse_observation({}, "country/USA", "Count_Person", "q", "u")
    assert r.status is Status.NOT_FOUND
    assert r.fields["entity"] == "country/USA"


def test_datacommons_parse_observation_positive_control_empty_observations():
    fixture = {
        "byVariable": {
            "Count_Person": {
                "byEntity": {
                    "geoId/99": {
                        "orderedFacets": [
                            {"facetId": "f1", "observations": []}
                        ]
                    }
                }
            }
        },
        "facets": {"f1": {"measurementMethod": "CensusPEPSurvey"}}
    }
    r = datacommons.parse_observation(fixture, "geoId/99", "Count_Person", "q", "u")
    assert r.status is Status.NOT_FOUND
    assert r.fields["entity"] == "geoId/99"
    assert "No observation points returned" in r.limitations


def test_datacommons_parse_observation_positive_control_empty_facets():
    fixture = {
        "byVariable": {
            "Count_Person": {
                "byEntity": {
                    "geoId/99": {
                        "orderedFacets": []
                    }
                }
            }
        }
    }
    r = datacommons.parse_observation(fixture, "geoId/99", "Count_Person", "q", "u")
    assert r.status is Status.NOT_FOUND
    assert r.fields["entity"] == "geoId/99"
    assert "No observations found" in r.limitations


def test_datacommons_parse_observation_year_not_found():
    r = datacommons.parse_observation(load("datacommons_observation.json"), "country/USA", "Count_Person", "q", "u", year="1990")
    assert r.status is Status.NOT_FOUND
    assert r.fields["year"] == "1990"
    assert "No observation found for year 1990" in r.limitations


def test_datacommons_observation_blocks_without_key(monkeypatch):
    from evidence import http
    monkeypatch.delenv("DC_API_KEY", raising=False)
    c = http.Client()
    r = datacommons.observation(c, "country/USA")
    assert r.status is Status.BLOCKED
    assert "DC_API_KEY" in r.fields["error"]


def test_openalex_parse_work_found():
    data = load("openalex_work.json")
    r = openalex.parse_work(data, "q", "u")
    assert r.status is Status.FOUND
    assert r.publisher_date == "2019-11-07"
    assert r.fields["year"] == 2019
    assert "Elexacaftor" in r.fields["title"]
    assert r.fields["cited_by"] == 2179
    assert r.fields["is_retracted"] is False
    assert r.fields["is_oa"] is True
    assert r.fields["venue"] == "New England Journal of Medicine"
    assert r.fields["first_author"] == "Peter G. Middleton"
    assert r.fields["last_author"] == "Michael W. Konstan"
    assert r.fields["author_count"] == 2
    assert "Westmead Hospital" in r.fields["institutions"]
    assert "Case Western Reserve University" in r.fields["institutions"]
    assert "Cystic Fibrosis" in r.fields["mesh_terms"]
    assert "Vertex Pharmaceuticals" in r.fields["grants"]
    assert "OpenAlex index record" in r.limitations


def test_openalex_parse_work_retracted():
    data = load("openalex_work.json")
    data["is_retracted"] = True
    r = openalex.parse_work(data, "q", "u")
    assert r.status is Status.FOUND
    assert r.fields["is_retracted"] is True


def test_openalex_parse_work_not_found():
    r = openalex.parse_work({}, "q", "u")
    assert r.status is Status.NOT_FOUND


def test_openalex_work_blocks_without_key(monkeypatch):
    from evidence import http
    monkeypatch.delenv("OPENALEX_API_KEY", raising=False)
    c = http.Client()
    r = openalex.work(c, "10.1056/nejmoa1908639")
    assert r.status is Status.BLOCKED
    assert "OPENALEX_API_KEY" in r.fields["error"]


def test_openalex_search_blocks_without_key(monkeypatch):
    from evidence import http
    monkeypatch.delenv("OPENALEX_API_KEY", raising=False)
    c = http.Client()
    recs = openalex.search(c, "cystic fibrosis")
    assert len(recs) == 1
    assert recs[0].status is Status.BLOCKED
    assert "OPENALEX_API_KEY" in recs[0].fields["error"]


def test_myvariant_parse_record():
    data = load("myvariant_hit.json")
    hit = data["hits"][0]
    r = myvariant.parse_myvariant_record(hit, "What is CFTR R31L in MyVariant?", "https://myvariant.info/v1/query?q=CFTR%20R31L")
    assert r.status is Status.FOUND
    assert r.source_id == "myvariant"
    assert r.fields["variant_id_genomic"] == "chr7:g.117144345G>T"
    assert r.fields["cadd_phred"] == 22.9
    assert r.fields["cadd_consequence"] == "NON_SYNONYMOUS"
    assert r.fields["snpeff_effect"] == "missense_variant"
    assert r.fields["clinvar_clinical_significance"] == "Uncertain significance"
    assert r.fields["gnomad_allele_freq"] == 0.0001
    assert "not a clinical diagnosis" in r.limitations


def test_gnomad_parse_record():
    data = load("gnomad_variant.json")
    r = gnomad.parse_gnomad_record(data, "What is F508del in gnomAD?", "https://gnomad.broadinstitute.org/variant/7-117559590-ATCT-A")
    assert r.status is Status.FOUND
    assert r.source_id == "gnomad"
    assert r.fields["variant_id"] == "7-117559590-ATCT-A"
    assert r.fields["chrom"] == "7"
    assert r.fields["pos"] == 117559590
    assert r.fields["exome_allele_freq"] == 0.007094
    assert r.fields["genome_allele_freq"] == 0.008036
    assert r.fields["joint_allele_freq"] == 0.007313
    assert "not constitute clinical diagnoses" in r.limitations


def test_gnomad_variant_blocks_under_catalog_rules():
    from evidence import http
    c = http.Client()
    r = gnomad.variant(c, "7-117559590-ATCT-A")
    assert r.status is Status.BLOCKED
    assert r.source_id == "gnomad"
    assert "AccessDenied" in r.fields["error"]


def test_ema_parse():
    data = load("ema_medicines_slice.json")
    r = ema.parse(data, "Kaftrio", "question", file_timestamp="2026-10-04T18:02:25Z")
    assert r.status is Status.FOUND
    assert r.publisher_date == "2020-08-21"
    assert r.fields["name_of_medicine"] == "Kaftrio"
    assert r.fields["medicine_status"] == "Authorised"
    assert "European Medicines Agency" in r.limitations


def test_ukri_gtr_parse():
    data = load("ukri_gtr_projects.json")
    recs = ukri_gtr.parse_projects(data, "question", "https://gtr.ukri.org/gtr/api/projects")
    assert len(recs) == 3
    assert recs[0].status is Status.FOUND
    assert recs[0].fields["lead_funder"] == "MRC"
    assert recs[0].fields["license"] == "Open Government Licence v3.0 (OGL)"
    assert "Open Government Licence v3.0" in recs[0].limitations


def test_unpaywall_parse():
    data = load("unpaywall_ng2745.json")
    r = unpaywall.parse_unpaywall(data, "10.1038/ng.2745", "question", "https://api.unpaywall.org/v2/10.1038/ng.2745")
    assert r.status is Status.FOUND
    assert r.source_id == "unpaywall"
    assert r.publisher_date == "2013"
    assert r.fields["doi"] == "10.1038/ng.2745"
    assert r.fields["is_oa"] is True
    assert r.fields["oa_status"] == "green"
    assert r.fields["best_oa_location"]["url"] == "https://www.ncbi.nlm.nih.gov/pmc/articles/3874936"
    assert "Unpaywall" in r.limitations


def test_semantic_scholar_parse():
    data = load("s2_ng2745.json")
    r = semantic_scholar.parse_paper(data, "10.1038/ng.2745", "question", "https://api.semanticscholar.org/graph/v1/paper/DOI:10.1038/ng.2745")
    assert r.status is Status.FOUND
    assert r.source_id == "semantic-scholar"
    assert r.publisher_date == "2013"
    assert r.fields["paper_id"] == "789d766eb8218cf6e6337c7740aee90f9c932eaf"
    assert r.fields["citation_graph_summary"]["citation_count"] >= 600
    assert r.fields["citation_graph_summary"]["reference_count"] >= 90
    assert "Semantic Scholar" in r.limitations





