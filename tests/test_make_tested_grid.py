"""Tests for scripts/make_tested_grid.py, which builds docs/tested-with.md (where each CF care skill's box has been tried) from docs/tested-with.json.

The grid is only worth having if a missing or invented result cannot hide, so each rule has a negative control: counts that do not add up, a pending
cell with numbers, a missing cell, a skill with a box but no row, a page that has drifted from the data, a cell or effect count that
differs from the committed run rows, a row whose verdict changed, a cell with no run data, and a duplicate row.
Run:  python -m unittest tests.test_make_tested_grid -v      (standard library only)"""
import copy
import importlib.util
import json
import shutil
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
RUNS = gen.load_runs(ROOT)
SUSPECT = gen.load_suspect(ROOT)


class RealRepoTests(unittest.TestCase):
    def test_data_is_consistent(self):
        self.assertEqual(gen.problems(DATA, BOXES), [])

    def test_page_matches_data(self):
        page = (ROOT / "docs" / "tested-with.md").read_text(encoding="utf-8").replace("\r\n", "\n")
        self.assertEqual(page, gen.render(DATA, RUNS, SUSPECT))

    def test_every_tested_cell_and_effect_count_is_recounted_from_the_rows(self):
        self.assertEqual(gen.run_problems(RUNS), [])
        self.assertEqual(gen.recount_problems(DATA, RUNS), [])

    def test_rows_hold_no_reply_text(self):
        for date, rows in RUNS.items():
            for r in rows:
                self.assertEqual(sorted(r), sorted(gen.ROW_KEYS), date)
                self.assertRegex(r["reply_sha256"], r"^[0-9a-f]{64}$")

    def test_the_drift_note_says_what_the_rows_say(self):
        # the same answer-check replies: 14 pass judged on 2026-10-08, 19 judged again on 2026-10-09; the new wording 21 in that batch
        self.assertIn(("cf-answer-check", "2026-10-08", "2026-10-09", 39, 14, 19, "2026-10-08", (21, 39)), gen.drift(RUNS))
        self.assertIn(("cf-visit-prep", "2026-10-08", "2026-10-09", 39, 18, 19, "2026-10-08", (26, 39)), gen.drift(RUNS))
        page = gen.render(DATA, RUNS, SUSPECT)
        self.assertIn("scored 14 pass when judged on 2026-10-08 and 19 when judged again on 2026-10-09", page)
        self.assertIn("a gain of +2, within that drift", page)

    def test_the_page_counts_the_suspect_cases(self):
        n = sum(len(v) for v in SUSPECT.values())
        self.assertGreater(n, 0)
        self.assertIn(f"{n} eval cases are marked `suspect`", gen.render(DATA, RUNS, SUSPECT))

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

    def broken_rows(self, edit_data=None, edit_runs=None):
        d, runs = copy.deepcopy(DATA), copy.deepcopy(RUNS)
        if edit_data:
            edit_data(d)
        if edit_runs:
            edit_runs(runs)
        return gen.run_problems(runs) + gen.recount_problems(d, runs)

    def test_a_cell_that_differs_from_its_rows(self):
        # still adds up to cases, so only the recount can catch it
        got = self.broken_rows(lambda d: d["cells"]["cf-answer-check"]["claude-opus"].update(**{"pass": 10, "partial": 3}))
        self.assertEqual(got, ["cf-answer-check / claude-opus: the rows in runs/2026-10-09 give 9 pass, 4 partial, 0 fail of 13; the data says 10, 3, 0 of 13"])

    def test_a_row_whose_verdict_changed(self):
        def flip(runs):
            r = next(r for r in runs["2026-10-08"] if r["test"] == "grid" and r["skill"] == "cf-ai-tool-review" and r["model"] == "opus" and r["verdict"] == "fail")
            r["verdict"] = "pass"
        got = self.broken_rows(edit_runs=flip)
        self.assertEqual(got, ["cf-ai-tool-review / claude-opus: the rows in runs/2026-10-08 give 6 pass, 7 partial, 0 fail of 13; the data says 5, 7, 1 of 13"])

    def test_an_effect_count_that_differs_from_its_rows(self):
        got = self.broken_rows(lambda d: d["effect"][1]["models"]["claude-opus"].update(**{"pass": 8, "fail": 3}))
        self.assertEqual(got, ["effect / SHORT box / claude-opus: the rows in runs/2026-10-08 give 7 pass, 1 partial, 4 fail of 12; the data says 8, 1, 3 of 12"])

    def test_a_duplicate_row(self):
        def dup(runs):
            runs["2026-10-09"].append(dict(runs["2026-10-09"][0]))
        got = self.broken_rows(edit_runs=dup)
        self.assertTrue(got and got[0].startswith("runs/2026-10-09: duplicate row"), got)

    def test_a_tested_cell_with_no_run_data(self):
        got = self.broken_rows(lambda d: d["cells"]["cf-visit-prep"]["claude-haiku"].update(date="2026-10-01"))
        self.assertEqual(got, ["cf-visit-prep / claude-haiku: no run data in docs/tested-with-runs/2026-10-01"])

    def test_a_duplicate_row_fails_the_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(ROOT / "docs", root / "docs")
            shutil.copytree(ROOT / ".claude" / "skills", root / ".claude" / "skills", ignore=shutil.ignore_patterns("__pycache__"))
            self.assertEqual(gen.main([str(root), "--check"]), 0)
            f = root / "docs" / "tested-with-runs" / "2026-10-08" / "rows.json"
            doc = json.loads(f.read_text(encoding="utf-8"))
            doc["rows"].append(doc["rows"][0])
            f.write_text(json.dumps(doc), encoding="utf-8")
            self.assertEqual(gen.main([str(root), "--check"]), 1)

    def test_a_stale_page_fails_the_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs").mkdir()
            (root / ".claude" / "skills").mkdir(parents=True)
            for s in BOXES:
                (root / ".claude" / "skills" / s / "references").mkdir(parents=True)
                (root / ".claude" / "skills" / s / "references" / "paste-ready.md").write_text("x", encoding="utf-8")
            (root / "docs" / "tested-with.json").write_text(json.dumps(DATA), encoding="utf-8")
            shutil.copytree(ROOT / "docs" / "tested-with-runs", root / "docs" / "tested-with-runs")
            for f in (ROOT / ".claude" / "skills").glob("*/evals/cases.json"):
                (root / ".claude" / "skills" / f.parent.parent.name / "evals").mkdir(parents=True, exist_ok=True)
                shutil.copy(f, root / ".claude" / "skills" / f.parent.parent.name / "evals" / "cases.json")
            self.assertEqual(gen.main([str(root)]), 0)
            self.assertEqual(gen.main([str(root), "--check"]), 0)
            page = root / "docs" / "tested-with.md"
            page.write_text(page.read_text(encoding="utf-8").replace("Pending", "5 of 5 pass", 1), encoding="utf-8")
            self.assertEqual(gen.main([str(root), "--check"]), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
