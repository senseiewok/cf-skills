"""Benchmark validation tests for SourceCheckup 20-statement benchmark (T-0924).

Methodology: SourceCheckup statement-level support evaluation (Nat Commun 2025, doi:10.1038/s41467-025-58551-6).
Dual compatibility: runs under both standard `python -m unittest` and `pytest`.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = str(SKILL_ROOT / "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import answer_checker as ac

BENCHMARK_FILE = SKILL_ROOT / "evals" / "source_checkup_20.json"


class TestSourceCheckupBenchmark(unittest.TestCase):
    def test_benchmark_file_exists_and_has_20_items(self):
        self.assertTrue(BENCHMARK_FILE.is_file(), f"Benchmark file missing at {BENCHMARK_FILE}")
        data = json.loads(BENCHMARK_FILE.read_text(encoding="utf-8"))
        items = data.get("items", [])
        self.assertEqual(len(items), 20, "SourceCheckup benchmark must contain exactly 20 statements")

        # Verify balanced distribution (5 items per class)
        counts = {}
        for it in items:
            exp = it["expected_status"]
            counts[exp] = counts.get(exp, 0) + 1

        self.assertEqual(counts.get(ac.STATUS_SUPPORTED), 5)
        self.assertEqual(counts.get(ac.STATUS_NOT_SUPPORTED), 5)
        self.assertEqual(counts.get(ac.STATUS_RETRACTED), 5)
        self.assertEqual(counts.get(ac.STATUS_NO_SOURCE), 5)

    def test_benchmark_metrics_satisfy_target_thresholds(self):
        metrics = ac.run_benchmark(BENCHMARK_FILE)

        # Accuracy target: >= 0.85 (target from T-0924 spec & discovery protocol)
        self.assertGreaterEqual(
            metrics["accuracy"],
            0.85,
            f"Expected accuracy >= 0.85, got {metrics['accuracy']}",
        )
        self.assertGreaterEqual(
            metrics["macro_f1"],
            0.85,
            f"Expected macro F1 >= 0.85, got {metrics['macro_f1']}",
        )

        # Verify each class achieves >= 0.80 precision and >= 0.85 recall
        for cls in ac.CLOSED_STATUS_CLASSES:
            m = metrics["per_class"][cls]
            self.assertGreaterEqual(
                m["precision"],
                0.80,
                f"Class {cls} precision {m['precision']} < 0.80",
            )
            self.assertGreaterEqual(
                m["recall"],
                0.85,
                f"Class {cls} recall {m['recall']} < 0.85",
            )
            self.assertGreaterEqual(
                m["f1"],
                0.85,
                f"Class {cls} F1 {m['f1']} < 0.85",
            )

    def test_falsification_negative_control_fails_on_inverted_ground_truth(self):
        """Planted defect: inverting ground truth labels must degrade accuracy below threshold."""
        raw_data = json.loads(BENCHMARK_FILE.read_text(encoding="utf-8"))
        poisoned_items = []
        for it in raw_data["items"]:
            p_it = dict(it)
            # Invert supported to not_supported
            if p_it["expected_status"] == ac.STATUS_SUPPORTED:
                p_it["expected_status"] = ac.STATUS_NOT_SUPPORTED
            elif p_it["expected_status"] == ac.STATUS_NOT_SUPPORTED:
                p_it["expected_status"] = ac.STATUS_SUPPORTED
            poisoned_items.append(p_it)

        # Evaluate against poisoned set
        total = len(poisoned_items)
        matches = 0
        for it in poisoned_items:
            rep = ac.check_answer(it["statement"])
            pred = rep.claims[0]["status"] if rep.claims else ac.STATUS_NO_SOURCE
            if pred == it["expected_status"]:
                matches += 1

        poisoned_acc = matches / total
        self.assertLess(
            poisoned_acc,
            0.85,
            "Negative control failed: poisoned ground truth should fail accuracy threshold",
        )


if __name__ == "__main__":
    unittest.main()
