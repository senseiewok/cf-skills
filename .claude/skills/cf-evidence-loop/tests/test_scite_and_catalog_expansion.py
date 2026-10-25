"""Tests for Scite zero-quota & MCP expansion (`scite-pmid`, `scite-aggregate`, `scite-sources`,
`scite-graph`, `scite-fulltext`, `scite-evidence`, `cite-check --scite-bulk`) and the 4 newly wired
catalog API providers (`ncbi-variation`, `uniprot-rest`, `ensembl-rest`, `dailymed-web-services`).
"""

from __future__ import annotations

from evidence import cite_check, cli
from evidence.http import Client
from evidence.providers import dailymed, ensembl, ncbi_variation, scite, uniprot
from evidence.record import Status


def test_scite_resolve_pmid_aggregate_sources_graph_fulltext_and_evidence(monkeypatch, capsys):
    monkeypatch.setenv("EVIDENCE_DRY_RUN", "1")
    assert cli.main(["scite-pmid", "31697873"]) == 0
    assert cli.main(["scite-aggregate", "10.1056/NEJMoa1908639", "10.1056/NEJMoa1105213"]) == 0
    assert cli.main(["scite-sources", "10.1056/NEJMoa1908639", "--limit", "3"]) == 0
    assert cli.main(["scite-graph", "10.1056/NEJMoa1908639", "--direction", "citing"]) == 0
    assert cli.main(["scite-fulltext", "10.1056/NEJMoa1908639", "--offset", "0", "--length", "4000"]) == 0
    assert cli.main(["scite-evidence", "mhra", "Kaftrio"]) == 0
    assert cli.main(["scite-evidence", "510k-summaries", "PARI eFlow nebulizer"]) == 0
    assert cli.main(["scite-evidence", "patents", "vanzacaftor", "--filter", "year:2024"]) == 0
    assert cli.main(["scite-pmid", "   "]) == 2
    assert cli.main(["scite-aggregate", "   "]) == 2
    assert cli.main(["scite-sources", "   "]) == 2
    assert cli.main(["scite-graph", "   "]) == 2
    assert cli.main(["scite-fulltext", "   "]) == 2
    assert cli.main(["scite-evidence", "mhra", "   "]) == 2
    capsys.readouterr()

    # 1. resolve_pmid parser
    r_pmid = scite.parse_resolve_pmid(
        {"pmid": "31697873", "doi": "10.1056/nejmoa1908639"},
        "31697873",
        "q",
        "https://api.scite.ai/papers/resolve-pmid/31697873",
    )
    assert r_pmid.status is Status.FOUND
    assert r_pmid.fields["doi"] == "10.1056/nejmoa1908639"
    assert r_pmid.fields["quota_bucket"] == "scite-public-tallies-free"

    # 2. aggregate_tallies parser
    r_agg = scite.parse_aggregate_tallies(
        {
            "total": 1980,
            "supporting": 109,
            "contradicting": 5,
            "mentioning": 1812,
            "unclassified": 54,
            "citingPublications": 2305,
        },
        ["10.1056/NEJMoa1908639", "10.1056/NEJMoa1105213"],
        "q",
        "https://api.scite.ai/tallies/aggregate",
    )
    assert r_agg.status is Status.FOUND
    assert r_agg.fields["dois_aggregated"] == 2
    assert r_agg.fields["supporting"] == 109
    assert r_agg.fields["citing_publications"] == 2305

    # 3. citing_sources parser (delta surveillance)
    r_src = scite.parse_citing_sources(
        {
            "papers": {
                "10.1016/j.jcf.2022.01.001": {
                    "doi": "10.1016/j.jcf.2022.01.001",
                    "title": "Follow-up CF study",
                    "year": 2022,
                    "journal": "JCF",
                    "retracted": False,
                    "editorialNotices": [],
                },
                "10.1000/retracted.paper": {
                    "doi": "10.1000/retracted.paper",
                    "title": "Retracted citing paper",
                    "year": 2023,
                    "journal": "TestJ",
                    "retracted": True,
                    "editorialNotices": [{"status": "Retracted"}],
                },
            }
        },
        "10.1056/NEJMoa1908639",
        "q",
        "https://api.scite.ai/papers/sources/10.1056/NEJMoa1908639",
    )
    assert r_src.status is Status.FOUND
    assert r_src.fields["citing_sources_total"] == 2
    assert r_src.fields["retracted_citing_sources_counted"] == 1

    # 4. citation_graph dry-run schema & parser with <untrusted_data> quarantine
    c_graph_dry = Client()
    r_graph_dry = scite.citation_graph(c_graph_dry, "10.1056/NEJMoa1908639", direction="citing", limit=5)
    assert r_graph_dry.status is Status.OUT_OF_SCOPE
    assert r_graph_dry.fields["planned_arguments"]["seeds"] == ["10.1056/NEJMoa1908639"]
    assert r_graph_dry.fields["planned_arguments"]["direction"] == "in"
    assert r_graph_dry.fields["planned_arguments"]["max_edges"] == 5

    r_graph = scite.parse_citation_graph(
        {
            "edges": [
                {
                    "s": "10.1016/j.jcf.2022.01.001",
                    "t": "10.1056/nejmoa1908639",
                    "type": "supporting",
                    "section": "Results",
                    "snippets": ["\x1b[32mConfirmed sweat chloride reduction.\x1b[0m"],
                }
            ]
        },
        "10.1056/NEJMoa1908639",
        "in",
        "q",
        "https://api.scite.ai/mcp",
    )
    assert r_graph.status is Status.FOUND
    assert r_graph.fields["edges_returned"] == 1
    assert r_graph.fields["edges"][0]["source_doi"] == "10.1016/j.jcf.2022.01.001"
    assert r_graph.fields["edges"][0]["target_doi"] == "10.1056/nejmoa1908639"
    assert "\x1b" not in r_graph.fields["edges"][0]["snippet"]
    assert r_graph.fields["edges"][0]["snippet"].startswith('<untrusted_data source="scite"')

    # 5. read_fulltext parser with <untrusted_data> quarantine
    r_ft = scite.parse_fulltext(
        {"doi": "10.1056/nejmoa1908639", "title": "ETI study", "text": "Methods: Double-blind Phase 3 trial.", "hasMore": True},
        "10.1056/NEJMoa1908639",
        0,
        4000,
        "q",
        "https://api.scite.ai/mcp",
    )
    assert r_ft.status is Status.FOUND
    assert r_ft.fields["has_more"] is True
    assert r_ft.fields["fulltext_quarantined"].startswith('<untrusted_data source="scite"')

    # 6. evidence_search relevance-only sort stripping & parser quarantine
    c_dry = Client()
    recs_mhra_dry = scite.evidence_search(c_dry, "mhra", "Kaftrio", sort_field="date", sort_dir="desc")
    assert recs_mhra_dry[0].status is Status.OUT_OF_SCOPE
    # mhra is relevance-only, so s and sortDir must be omitted from planned_arguments
    assert "s" not in recs_mhra_dry[0].fields["planned_arguments"]
    assert "sortDir" not in recs_mhra_dry[0].fields["planned_arguments"]

    recs_ev = scite.parse_evidence_search(
        {
            "total": 1,
            "hits": [
                {
                    "id": "MHRA-2024-001",
                    "title": "Kaftrio (ivacaftor/tezacaftor/elexacaftor): liver function monitoring",
                    "summary": "Monitor LFTs prior to and during treatment.",
                    "date": "2024-06-15",
                    "url": "https://www.gov.uk/drug-safety-update/kaftrio",
                }
            ],
        },
        "mhra",
        "Kaftrio",
        "q",
        "https://api.scite.ai/mcp",
    )
    assert len(recs_ev) == 1
    assert recs_ev[0].status is Status.FOUND
    assert recs_ev[0].fields["id"] == "MHRA-2024-001"
    assert recs_ev[0].fields["summary_quarantined"].startswith('<untrusted_data source="scite"')


def test_cite_check_scite_bulk_preflight(monkeypatch):
    from test_conduct import FakeResponse, Script, make_client

    monkeypatch.setattr("time.sleep", lambda _s: None)
    s = Script(
        [
            FakeResponse(200, body={"pmid": "31697873", "doi": "10.1056/nejmoa1908639"}),
            FakeResponse(
                200,
                body={
                    "tallies": {
                        "10.1056/nejmoa1908639": {
                            "doi": "10.1056/nejmoa1908639",
                            "supporting": 109,
                            "contradicting": 5,
                            "mentioning": 1812,
                            "total": 1980,
                            "citingPublications": 2305,
                        },
                        "10.1038/ng.2745": {
                            "doi": "10.1038/ng.2745",
                            "supporting": 10,
                            "contradicting": 2,
                            "mentioning": 50,
                            "total": 62,
                            "citingPublications": 55,
                        },
                    }
                },
            ),
            FakeResponse(
                200,
                body={
                    "papers": {
                        "10.1056/nejmoa1908639": {
                            "doi": "10.1056/nejmoa1908639",
                            "title": "Elexacaftor-Tezacaftor-Ivacaftor for Cystic Fibrosis",
                            "year": 2019,
                            "retracted": False,
                        },
                        "10.1038/ng.2745": {
                            "doi": "10.1038/ng.2745",
                            "title": "Retracted CFTR paper",
                            "year": 2013,
                            "retracted": True,
                        },
                    }
                },
            ),
            FakeResponse(
                200,
                body={
                    "tallies": {
                        "10.1056/nejmoa1908639": {
                            "doi": "10.1056/nejmoa1908639",
                            "introduction": 701,
                            "methods": 21,
                            "results": 87,
                            "discussion": 453,
                            "other": 533,
                            "total": 1980,
                        },
                        "10.1038/ng.2745": {
                            "doi": "10.1038/ng.2745",
                            "introduction": 40,
                            "methods": 0,
                            "results": 0,
                            "discussion": 22,
                            "other": 0,
                            "total": 62,
                        },
                    }
                },
            ),
        ]
    )
    c = make_client(monkeypatch, s)
    found = cite_check.extract("See 10.1056/NEJMoa1908639 and PMID 31697873 and 10.1038/ng.2745.")
    items = cite_check.resolve(c, found, scite_bulk=True)
    assert len(items) == 3
    assert all(i.verdict == cite_check.PASS for i in items)
    assert items[0].record.source_id == "scite-api"
    assert items[1].record.source_id == "scite-api"
    assert items[2].title_verdict == cite_check.TITLE_CHECK
    assert "flagged retracted in Scite" in items[2].title_detail


def test_ncbi_variation_uniprot_ensembl_and_dailymed_providers(monkeypatch, capsys):
    monkeypatch.setenv("EVIDENCE_DRY_RUN", "1")
    assert cli.main(["ncbi-variation", "NM_000492.4:c.1521_1523del"]) == 0
    assert cli.main(["uniprot", "P13569"]) == 0
    assert cli.main(["uniprot", "CFTR", "--limit", "2"]) == 0
    assert cli.main(["ensembl", "rs113993960"]) == 0
    assert cli.main(["ensembl", "ENSG00000001626"]) == 0
    assert cli.main(["ensembl", "CFTR"]) == 0
    assert cli.main(["dailymed", "TRIKAFTA", "--limit", "2"]) == 0
    assert cli.main(["ncbi-variation", "   "]) == 2
    assert cli.main(["uniprot", "   "]) == 2
    assert cli.main(["ensembl", "   "]) == 2
    assert cli.main(["dailymed", "   "]) == 2
    capsys.readouterr()

    # 1. ncbi_variation parser
    r_nv = ncbi_variation.parse_hgvs(
        {
            "data": {
                "spdis": [
                    {
                        "seq_id": "NC_000007.14",
                        "position": 117559589,
                        "deleted_sequence": "ATCT",
                        "inserted_sequence": "A",
                    }
                ]
            }
        },
        "NM_000492.4:c.1521_1523del",
        "q",
        "https://api.ncbi.nlm.nih.gov/variation/v0/hgvs/NM_000492.4:c.1521_1523del/contextuals",
    )
    assert r_nv.status is Status.FOUND
    assert r_nv.source_id == "ncbi-variation"
    assert r_nv.fields["canonical_spdi"] == "NC_000007.14:117559589:ATCT:A"

    # 2. uniprot parser
    r_up = uniprot.parse_entry(
        {
            "primaryAccession": "P13569",
            "uniProtkbId": "CFTR_HUMAN",
            "sequence": {"length": 1480},
            "genes": [{"geneName": {"value": "CFTR"}}],
            "proteinDescription": {
                "recommendedName": {"fullName": {"value": "Cystic fibrosis transmembrane conductance regulator"}}
            },
            "features": [
                {
                    "type": "Domain",
                    "description": "ABC transporter 1",
                    "location": {"start": {"value": 433}, "end": {"value": 634}},
                },
                {
                    "type": "Transmembrane",
                    "description": "Helical",
                    "location": {"start": {"value": 81}, "end": {"value": 103}},
                },
                {"type": "Natural variant", "description": "p.Phe508del"},
            ],
            "entryAudit": {"lastAnnotationUpdateDate": "2026-09-02"},
        },
        "P13569",
        "q",
        "https://rest.uniprot.org/uniprotkb/P13569.json",
    )
    assert r_up.status is Status.FOUND
    assert r_up.source_id == "uniprot-rest"
    assert r_up.fields["sequence_length"] == 1480
    assert r_up.fields["transmembrane_segments_counted"] == 1
    assert r_up.fields["natural_variants_counted"] == 1
    assert r_up.fields["domains"][0]["description"] == "ABC transporter 1"

    # 3. ensembl variation & gene lookup parsers
    r_ens_var = ensembl.parse_variation(
        {
            "name": "rs113993960",
            "most_severe_consequence": "inframe_deletion",
            "var_class": "deletion",
            "clinical_significance": ["pathogenic"],
            "mappings": [{"location": "7:117559590-117559592", "allele_string": "CTT/-", "assembly_name": "GRCh38"}],
            "synonyms": ["CM900049"],
        },
        "rs113993960",
        "q",
        "https://rest.ensembl.org/variation/human/rs113993960",
    )
    assert r_ens_var.status is Status.FOUND
    assert r_ens_var.source_id == "ensembl-rest"
    assert r_ens_var.fields["most_severe_consequence"] == "inframe_deletion"

    r_ens_gene = ensembl.parse_lookup(
        {
            "id": "ENSG00000001626",
            "object_type": "Gene",
            "display_name": "CFTR",
            "biotype": "protein_coding",
            "assembly_name": "GRCh38",
            "seq_region_name": "7",
            "start": 117480025,
            "end": 117668665,
            "strand": 1,
            "canonical_transcript": "ENST00000003084.11",
            "Transcript": [{"id": "ENST00000003084"}],
        },
        "CFTR",
        "q",
        "https://rest.ensembl.org/lookup/symbol/homo_sapiens/CFTR",
    )
    assert r_ens_gene.status is Status.FOUND
    assert r_ens_gene.fields["canonical_transcript"] == "ENST00000003084.11"
    assert r_ens_gene.fields["transcripts_counted"] == 1

    # 4. dailymed parser
    recs_dm = dailymed.parse_spls(
        {
            "data": [
                {
                    "setid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                    "title": "TRIKAFTA (elexacaftor, tezacaftor, and ivacaftor) tablet, film coated",
                    "published_date": "Oct 21, 2025",
                    "spl_version": 14,
                }
            ],
            "metadata": {"total_elements": 1},
        },
        "TRIKAFTA",
        "q",
        "https://dailymed.nlm.nih.gov/dailymed/services/v2/spls.json?drug_name=TRIKAFTA",
    )
    assert len(recs_dm) == 1
    assert recs_dm[0].status is Status.FOUND
    assert recs_dm[0].source_id == "dailymed-web-services"
    assert recs_dm[0].fields["spl_version"] == 14
