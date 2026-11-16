"""Tests for Retraction Watch daily data and OpenAlex cross-check (T-0926)."""

import io
from pathlib import Path
import tempfile
import unittest

from evidence.providers import retraction_watch as rw
from evidence.record import Status


SAMPLE_CSV = """Record ID,OriginalPaperDOI,OriginalPaperTitle,OriginalPaperDate,RetractionDOI,RetractionDate,RetractionNature,Reason
1001,10.1016/S0140-6736(97)11096-0,"Ileal-lymphoid-nodular hyperplasia, non-specific colitis, and pervasive developmental disorder in children",1998-02-28,10.1016/S0140-6736(10)60175-4,2010-02-06,Retraction,"Data fabrication; falsification"
1002,10.1038/ng.2745,"Identification of non-coding CFTR variants modifying cystic fibrosis lung disease",2013-09-08,10.1038/ng.2800,2014-01-15,Correction,"Author name typo and supplementary table mislabeling"
1003,10.1126/science.1234567,"Nanoparticle gene delivery across airway mucus in cystic fibrosis",2021-03-12,10.1126/science.eoc890,2022-06-20,Expression of Concern,"Image integrity inquiry underway"
1004,10.1056/NEJMoa1908639,"Elexacaftor-Tezacaftor-Ivacaftor for Cystic Fibrosis with a Single Phe508del Allele",2019-11-07,,,Clean,""
"""

UPDATED_CSV = """Record ID,OriginalPaperDOI,OriginalPaperTitle,OriginalPaperDate,RetractionDOI,RetractionDate,RetractionNature,Reason
1001,10.1016/S0140-6736(97)11096-0,"Ileal-lymphoid-nodular hyperplasia, non-specific colitis, and pervasive developmental disorder in children",1998-02-28,10.1016/S0140-6736(10)60175-4,2010-02-06,Retraction,"Data fabrication; falsification"
1002,10.1038/ng.2745,"Identification of non-coding CFTR variants modifying cystic fibrosis lung disease",2013-09-08,10.1038/ng.2800,2014-01-15,Correction,"Author name typo and supplementary table mislabeling"
1003,10.1126/science.1234567,"Nanoparticle gene delivery across airway mucus in cystic fibrosis",2021-03-12,10.1126/science.ret999,2023-01-10,Retraction,"Confirmed image duplication; retracted following inquiry"
1005,10.1002/humu.23276,"Novel CFTR splicing variants identified by whole-genome sequencing",2017-06-01,10.1002/humu.23400,2026-11-10,Retraction,"Unreproducible variant caller artifact"
"""


class TestRetractionWatch(unittest.TestCase):
    def test_normalize_doi(self):
        self.assertEqual(rw.normalize_doi("10.1016/S0140-6736(97)11096-0"), "10.1016/s0140-6736(97)11096-0")
        self.assertEqual(rw.normalize_doi("https://doi.org/10.1038/NG.2745."), "10.1038/ng.2745")
        self.assertEqual(rw.normalize_doi("http://dx.doi.org/10.1126/science.1234567"), "10.1126/science.1234567")
        self.assertEqual(rw.normalize_doi(""), "")
        self.assertEqual(rw.normalize_doi(None), "")

    def test_parse_csv(self):
        index = rw.parse_retraction_watch_csv(SAMPLE_CSV)
        self.assertIn("10.1016/s0140-6736(97)11096-0", index)
        self.assertIn("10.1038/ng.2745", index)
        self.assertIn("10.1126/science.1234567", index)

        ret_rec = index["10.1016/s0140-6736(97)11096-0"][0]
        self.assertTrue(ret_rec.is_retracted)
        self.assertFalse(ret_rec.is_correction)
        self.assertFalse(ret_rec.is_expression_of_concern)
        self.assertEqual(ret_rec.retraction_nature, "Retraction")
        self.assertEqual(ret_rec.record_id, "1001")

        corr_rec = index["10.1038/ng.2745"][0]
        self.assertFalse(corr_rec.is_retracted)
        self.assertTrue(corr_rec.is_correction)
        self.assertEqual(corr_rec.retraction_nature, "Correction")

        eoc_rec = index["10.1126/science.1234567"][0]
        self.assertFalse(eoc_rec.is_retracted)
        self.assertTrue(eoc_rec.is_expression_of_concern)

    def test_diff_snapshots(self):
        old_index = rw.parse_retraction_watch_csv(SAMPLE_CSV)
        new_index = rw.parse_retraction_watch_csv(UPDATED_CSV)

        diff = rw.diff_snapshots(old_index, new_index)
        self.assertEqual(diff["new_dois_count"], 1)
        self.assertEqual(diff["new_flags"][0]["doi"], "10.1002/humu.23276")
        self.assertTrue(diff["new_flags"][0]["is_retracted"])

        # Escalation: 10.1126/science.1234567 went from Expression of Concern to Retraction
        self.assertEqual(diff["escalated_count"], 1)
        self.assertEqual(diff["escalated"][0]["doi"], "10.1126/science.1234567")

    def test_cross_check_openalex_concordance(self):
        index = rw.parse_retraction_watch_csv(SAMPLE_CSV)

        # Case 1: Confirmed retracted by both RW and OpenAlex
        doi_1 = "10.1016/s0140-6736(97)11096-0"
        res_1 = rw.cross_check_openalex(doi_1, index[doi_1], openalex_is_retracted=True)
        self.assertEqual(res_1["verdict"], "RETRACTED")
        self.assertEqual(res_1["concordance"], "CONFIRMED_RETRACTED")

        # Case 2: Retraction Watch only (OpenAlex not yet updated)
        res_2 = rw.cross_check_openalex(doi_1, index[doi_1], openalex_is_retracted=False)
        self.assertEqual(res_2["verdict"], "RETRACTED")
        self.assertEqual(res_2["concordance"], "RETRACTION_WATCH_ONLY")

        # Case 3: OpenAlex only (Retraction Watch clean)
        clean_doi = "10.1056/nejmoa1908639"
        res_3 = rw.cross_check_openalex(clean_doi, [], openalex_is_retracted=True)
        self.assertEqual(res_3["verdict"], "RETRACTED")
        self.assertEqual(res_3["concordance"], "OPENALEX_ONLY")

        # Case 4: Correction notice
        doi_corr = "10.1038/ng.2745"
        res_4 = rw.cross_check_openalex(doi_corr, index[doi_corr], openalex_is_retracted=False)
        self.assertEqual(res_4["verdict"], "CORRECTION")
        self.assertEqual(res_4["concordance"], "CORRECTION")

        # Case 5: Expression of concern
        doi_eoc = "10.1126/science.1234567"
        res_5 = rw.cross_check_openalex(doi_eoc, index[doi_eoc], openalex_is_retracted=False)
        self.assertEqual(res_5["verdict"], "EXPRESSION_OF_CONCERN")
        self.assertEqual(res_5["concordance"], "EXPRESSION_OF_CONCERN")

        # Case 6: Clean in both
        res_6 = rw.cross_check_openalex(clean_doi, [], openalex_is_retracted=False)
        self.assertEqual(res_6["verdict"], "CLEAN")
        self.assertEqual(res_6["concordance"], "CLEAN")

    def test_check_doi_evidence_record(self):
        index = rw.parse_retraction_watch_csv(SAMPLE_CSV)
        ev = rw.check_doi("10.1016/S0140-6736(97)11096-0", index, {"is_retracted": True, "title": "Lancet study"})
        self.assertEqual(ev.status, Status.FOUND)
        self.assertEqual(ev.fields["verdict"], "RETRACTED")
        self.assertEqual(ev.fields["concordance"], "CONFIRMED_RETRACTED")
        self.assertIn("Never uses a model's own judgement", ev.limitations)
        self.assertIn("Data fabrication", ev.excerpt)

    def test_audit_catalog_sources(self):
        index = rw.parse_retraction_watch_csv(SAMPLE_CSV)

        mock_catalog = """
sources:
  - id: wakefield-study
    title: Wakefield et al 1998
    doi: 10.1016/S0140-6736(97)11096-0
  - id: cftr-modifier-gwas
    title: CFTR Modifier Study 2013
    url: https://doi.org/10.1038/ng.2745
  - id: trikafta-phase3
    title: Trikafta Phase 3 Study 2019
    doi: 10.1056/NEJMoa1908639
"""
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8") as f:
            f.write(mock_catalog)
            temp_path = f.name

        try:
            report = rw.audit_catalog_sources(temp_path, index, openalex_cache={"10.1016/s0140-6736(97)11096-0": True})
            self.assertEqual(report["total_sources_scanned"], 3)
            self.assertEqual(report["unique_dois_checked"], 3)
            self.assertEqual(report["flagged_dois_count"], 2)
            self.assertEqual(report["clean_dois_count"], 1)

            flagged_ids = [item["source_id"] for item in report["flagged"]]
            self.assertIn("wakefield-study", flagged_ids)
            self.assertIn("cftr-modifier-gwas", flagged_ids)
        finally:
            Path(temp_path).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
