"""Tests for scripts/make_tested_grid.py, which builds docs/tested-with.md (where each CF care skill's box has been tried) from docs/tested-with.json.

The grid is only worth having if a missing or invented result cannot hide, so each rule has a negative control: counts that do not add up, a pending
cell with numbers, a missing cell, a skill with a box but no row, and a page that has drifted from the data.
Run:  python -m unittest tests.test_make_tested_grid -v      (standard library only)"""
import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("make_tested_grid", ROOT / "scripts" / "make_tested_grid.py")
gen = importlib.util.module_from_spec(spec)
sys.modules["make_tested_grid"] = gen
spec.loader.exec_module(gen)

DATA = json.loads((ROOT / "docs" / "tested-with.json").read_text(encoding="utf-8"))
BOXES = sorted(p.parent.parent.name for p in (ROOT / ".claude" / "skills").glob("*/references/paste-ready.md"))


class RealRepoTests(unittest.TestCase):
    def test_data_is_consistent(self):
        self.assertEqual(gen.problems(DATA, BOXES), [])

    def test_page_matches_data(self):
        page = (ROOT / "docs" / "tested-with.md").read_text(encoding="utf-8").replace("\r\n", "\n")
        self.assertEqual(page, gen.render(DATA))

    def test_main_check_passes(self):
        self.assertEqual(gen.main([str(ROOT), "--check"]), 0)

    def test_untested_products_are_shown_as_pending(self):
        for skill, row in DATA["cells"].items():
            for cid in ("gemini", "gpt", "copilot"):
                self.assertEqual(row[cid], {"status": "pending"}, f"{skill} / {cid}: not run, so it must stay pending until a run is recorded")

    def test_every_tested_cell_is_a_count_with_a_date(self):
        tested = [(s, c) for s, row in DATA["cells"].items() for c, cell in row.items() if cell["status"] == "tested"]
        self.assertGreaterEqual(len(tested), 15)
        for s, c in tested:
            cell = DATA["cells"][s][c]
            self.assertEqual(cell["pass"] + cell["partial"] + cell["fail"], cell["cases"], (s, c))
            self.assertTrue(cell["date"])


class NegativeControls(unittest.TestCase):
    def broken(self, edit):
        d = copy.deepcopy(DATA)
        edit(d)
        return gen.problems(d, BOXES)

    def test_counts_that_do_not_add_up(self):
        got = self.broken(lambda d: d["cells"]["cf-visit-prep"]["claude-opus"].update(fail=3))
        self.assertEqual(got, ["cf-visit-prep / claude-opus: pass + partial + fail is not cases"])

    def test_a_pending_cell_with_numbers(self):
        got = self.broken(lambda d: d["cells"]["cf-answer-check"]["gemini"].update(**{"pass": 5}))
        self.assertEqual(got, ["cf-answer-check / gemini: a pending cell carries ['pass']"])

    def test_a_missing_cell(self):
        got = self.broken(lambda d: d["cells"]["cf-ai-safe-use"].pop("gpt"))
        self.assertEqual(got, ["cf-ai-safe-use: no cell for gpt"])

    def test_a_skill_with_a_box_but_no_row(self):
        got = self.broken(lambda d: d["cells"].pop("cf-ai-tool-review"))
        self.assertEqual(got, ["cf-ai-tool-review: ships a paste-ready box but has no row in the grid"])

    def test_a_tested_cell_without_a_date(self):
        got = self.broken(lambda d: d["cells"]["cf-visit-prep"]["claude-haiku"].pop("date"))
        self.assertEqual(got, ["cf-visit-prep / claude-haiku: a tested cell needs a date"])

    def test_a_small_run_with_pass_counts(self):
        got = self.broken(lambda d: d["cells"]["cf-visit-prep"]["qwen"].update(**{"pass": 2}))
        self.assertEqual(got, ["cf-visit-prep / qwen: a small cell needs 'cases' and no pass counts"])

    def test_effect_counts_that_do_not_add_up(self):
        got = self.broken(lambda d: d["effect"][0]["models"]["claude-haiku"].update(fail=0))
        self.assertEqual(got, ["effect / No box (a plain helpful assistant) / claude-haiku: pass + partial + fail is not cases"])

    def test_a_stale_page_fails_the_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs").mkdir()
            (root / ".claude" / "skills").mkdir(parents=True)
            for s in BOXES:
                (root / ".claude" / "skills" / s / "references").mkdir(parents=True)
                (root / ".claude" / "skills" / s / "references" / "paste-ready.md").write_text("x", encoding="utf-8")
            (root / "docs" / "tested-with.json").write_text(json.dumps(DATA), encoding="utf-8")
            self.assertEqual(gen.main([str(root)]), 0)
            self.assertEqual(gen.main([str(root), "--check"]), 0)
            page = root / "docs" / "tested-with.md"
            page.write_text(page.read_text(encoding="utf-8").replace("Pending", "5 of 5 pass", 1), encoding="utf-8")
            self.assertEqual(gen.main([str(root), "--check"]), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
