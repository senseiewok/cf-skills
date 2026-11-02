"""Unit tests for CFTR structural domain, exon, and canonical allele context.

Verifies zero-network deterministic lookup of CFTR RefSeq (NM_000492.4) exon numbers,
UniProt (P13569) protein domain boundaries, and CFTR2/CFFPR canonical mutation classes,
with positive analytical cases and deterministic negative controls.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = SKILL_ROOT / "scripts" / "evidence" / "cftr_context.py"

spec = importlib.util.spec_from_file_location("cftr_context", MODULE_PATH)
assert spec is not None and spec.loader is not None
cftr_context = importlib.util.module_from_spec(spec)
sys.modules["evidence.cftr_context"] = cftr_context
spec.loader.exec_module(cftr_context)


class CftrContextTests(unittest.TestCase):
    def test_canonical_alleles_catalog_integrity(self):
        """Verify that canonical alleles catalog contains at least 23 curated alleles with full metadata."""
        alleles = cftr_context.CANONICAL_ALLELES
        self.assertGreaterEqual(len(alleles), 23)
        for key, info in alleles.items():
            self.assertTrue(key.isupper() or any(c in key for c in "+->"))
            self.assertIn("allele", info)
            self.assertIn("hgvs_c", info)
            self.assertIn("hgvs_p", info)
            self.assertIn("exon", info)
            self.assertIn("domain", info)
            self.assertIn("cftr_class", info)
            if info["exon"] is not None:
                self.assertIsInstance(info["exon"], int)
                self.assertGreaterEqual(info["exon"], 1)
                self.assertLessEqual(info["exon"], 27)

    def test_domain_boundaries_contiguity(self):
        """Verify that all 9 structural domains span 1 to 1480 contiguously without gaps."""
        domains = cftr_context.CFTR_DOMAINS
        self.assertEqual(len(domains), 9)
        curr = 1
        for start, end, name, desc in domains:
            self.assertEqual(start, curr, f"Domain '{name}' start {start} does not match expected {curr}")
            self.assertGreater(end, start)
            curr = end + 1
        self.assertEqual(curr - 1, 1480, f"Terminal residue {curr - 1} does not equal 1480")

    def test_exon_boundaries_contiguity(self):
        """Verify that all 27 CFTR exons span codons 1 to 1480 contiguously."""
        exons = cftr_context.CFTR_EXON_SPANS
        self.assertEqual(len(exons), 27)
        curr = 1
        for exon_num, start, end in exons:
            self.assertEqual(start, curr, f"Exon {exon_num} start {start} does not match expected {curr}")
            self.assertGreater(end, start)
            curr = end + 1
        self.assertEqual(curr - 1, 1480, f"Terminal codon {curr - 1} does not equal 1480")

    def test_major_classes_canonical_lookups(self):
        """Test representative canonical allele lookups across mutation Classes I through V."""
        test_matrix = [
            # Class I: Nonsense / Frameshift / Canonical Splice
            ("G542X", "G542X", 12, "Class I"),
            ("W1282X", "W1282X", 23, "Class I"),
            ("R553X", "R553X", 12, "Class I"),
            ("621+1G>T", "621+1G>T", 4, "Class I"),
            ("1717-1G>A", "1717-1G>A", 12, "Class I"),
            ("3120+1G>A", "3120+1G>A", 18, "Class I"),
            ("R1162X", "R1162X", 21, "Class I"),
            ("2184delA", "2184delA", 14, "Class I"),
            ("3659delC", "3659delC", 22, "Class I"),
            ("Y1092X", "Y1092X", 20, "Class I"),
            # Class II: Misfolding & Trafficking
            ("F508del", "F508del", 11, "Class II"),
            ("N1303K", "N1303K", 24, "Class II"),
            ("I507del", "I507del", 11, "Class II"),
            ("V520F", "V520F", 11, "Class II"),
            ("G85E", "G85E", 3, "Class II"),
            ("M1101K", "M1101K", 20, "Class II"),
            # Class III: Gating
            ("G551D", "G551D", 12, "Class III"),
            ("S549N", "S549N", 12, "Class III"),
            # Class IV: Conductance
            ("R117H", "R117H", 4, "Class IV"),
            ("R334W", "R334W", 8, "Class IV"),
            ("R347P", "R347P", 8, "Class IV"),
            ("D1152H", "D1152H", 21, "Class IV"),
            # Class V: Alternative / Cryptic Splicing & Reduced Synthesis
            ("3849+10kbC>T", "3849+10kbC>T", 22, "Class V"),
            ("2789+5G>A", "2789+5G>A", 15, "Class V"),
            ("A455E", "A455E", 10, "Class V"),
        ]

        for query, expected_allele, expected_exon, expected_class_substr in test_matrix:
            res = cftr_context.lookup_cftr_context(query)
            self.assertIsNotNone(res, f"Lookup failed for query: '{query}'")
            self.assertEqual(res["allele"], expected_allele)
            self.assertEqual(res["exon"], expected_exon)
            self.assertIn(expected_class_substr, res["cftr_class"])
            self.assertEqual(res["transcript"], "NM_000492.4")
            self.assertEqual(res["uniprot"], "P13569")

    def test_query_normalization_arrow_and_delta(self):
        """Verify normalization of arrow notation, delta prefix, and casing."""
        # Arrow notation -> normalized to >
        res1 = cftr_context.lookup_cftr_context("621+1G->T")
        self.assertIsNotNone(res1)
        self.assertEqual(res1["allele"], "621+1G>T")

        res2 = cftr_context.lookup_cftr_context("3849+10kbC->T")
        self.assertIsNotNone(res2)
        self.assertEqual(res2["allele"], "3849+10kbC>T")

        # Delta symbol Δ and delta prefix
        res3 = cftr_context.lookup_cftr_context("ΔF508")
        self.assertIsNotNone(res3)
        self.assertEqual(res3["allele"], "F508del")

        res4 = cftr_context.lookup_cftr_context("delF508")
        self.assertIsNotNone(res4)
        self.assertEqual(res4["allele"], "F508del")

        res5 = cftr_context.lookup_cftr_context("ΔI507")
        self.assertIsNotNone(res5)
        self.assertEqual(res5["allele"], "I507del")

    def test_hgvs_aliases_lookup(self):
        """Verify lookup by HGVS cDNA and protein notations."""
        # cDNA lookups
        self.assertEqual(cftr_context.lookup_cftr_context("c.1521_1523delCTT")["allele"], "F508del")
        self.assertEqual(cftr_context.lookup_cftr_context("c.1652G>A")["allele"], "G551D")
        self.assertEqual(cftr_context.lookup_cftr_context("c.1624G>T")["allele"], "G542X")
        self.assertEqual(cftr_context.lookup_cftr_context("c.3846G>A")["allele"], "W1282X")

        # Protein lookups
        self.assertEqual(cftr_context.lookup_cftr_context("p.Phe508del")["allele"], "F508del")
        self.assertEqual(cftr_context.lookup_cftr_context("p.Gly551Asp")["allele"], "G551D")
        self.assertEqual(cftr_context.lookup_cftr_context("p.Trp1282Ter")["allele"], "W1282X")

    def test_generic_codon_extraction(self):
        """Verify generic codon extraction and mapping to domain and exon."""
        res = cftr_context.lookup_cftr_context("CFTR codon 508")
        self.assertIsNotNone(res)
        self.assertEqual(res["codon"], 508)
        self.assertEqual(res["exon"], 11)
        self.assertEqual(res["domain"], "NBD1 (Nucleotide-Binding Domain 1)")

        res_tmd = cftr_context.lookup_cftr_context("CFTR codon 100")
        self.assertIsNotNone(res_tmd)
        self.assertEqual(res_tmd["codon"], 100)
        self.assertEqual(res_tmd["exon"], 4)
        self.assertEqual(res_tmd["domain"], "TMD1 (Transmembrane Domain 1)")

    def test_negative_controls(self):
        """Verify negative controls return None deterministically."""
        negative_cases = [
            "",
            "   ",
            "CFTR codon 0",
            "CFTR codon 1481",
            "CFTR codon -10",
            "completely_unrelated_disease_gene_xyz",
        ]
        for query in negative_cases:
            res = cftr_context.lookup_cftr_context(query)
            self.assertIsNone(res, f"Negative control query '{query}' did not return None")

    def test_self_check_engine(self):
        """Verify the built-in self_check() function passes completely."""
        res = cftr_context.self_check()
        self.assertTrue(res["passed"], f"self_check() failed: {res}")
        self.assertEqual(res["total_checks"], 5)
        self.assertTrue(all(c["ok"] for c in res["checks"]))

    def test_cli_standalone(self):
        """Verify standalone CLI main() with various options."""
        # --self-check
        code = cftr_context.main(["--self-check"])
        self.assertEqual(code, 0)

        # --self-check --json
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            code = cftr_context.main(["--self-check", "--json"])
            self.assertEqual(code, 0)
            data = json.loads(sys.stdout.getvalue())
            self.assertTrue(data["passed"])
        finally:
            sys.stdout = old_stdout

        # --list
        sys.stdout = io.StringIO()
        try:
            code = cftr_context.main(["--list"])
            self.assertEqual(code, 0)
            self.assertIn("F508del", sys.stdout.getvalue())
        finally:
            sys.stdout = old_stdout

        # Term lookup
        code = cftr_context.main(["F508del"])
        self.assertEqual(code, 0)

        # Unknown term lookup returns 1
        code = cftr_context.main(["unknown_allele_xyz_123"])
        self.assertEqual(code, 1)

        # No arguments returns 2
        code = cftr_context.main([])
        self.assertEqual(code, 2)

    def test_audit_hook_zero_network_zero_subprocess(self):
        """Verify that looking up CFTR context triggers zero network sockets or subprocess calls."""
        events: list[tuple[str, tuple]] = []

        def audit_hook(event, args):
            if event.startswith("socket.") or event.startswith("urllib.") or event == "subprocess.Popen":
                events.append((event, args))

        sys.addaudithook(audit_hook)
        try:
            for k in list(cftr_context.CANONICAL_ALLELES.keys())[:10]:
                cftr_context.lookup_cftr_context(k)
            cftr_context.self_check()
        finally:
            pass

        self.assertEqual(events, [], f"Disallowed network/subprocess events: {events}")


if __name__ == "__main__":
    unittest.main()
