"""Tests for claim_worksheet.py, with negative controls: plain sentences must not become claims.

The answer texts are invented. Their 'facts' are placeholders and are not true or false statements about CF.
Dual compatibility: runs under both standard `python -m unittest` and `pytest`.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = str(SKILL_ROOT / "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import claim_worksheet as cw

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "claim_worksheet.py"
FIELDS = {"id", "claim", "source", "quote", "kind", "scope"}

ANSWER = """Thanks for asking. I hope this helps.
In one example study, 42% of people in the trial group improved.
Exampledrug was the first medicine of its kind.
There is no evidence that this diet changes lung function.
Ivacaftor is a CFTR modulator.
- The report covered 2019 to 2023.
Talk with your care team about what this means for you."""


def run_cli(*args, stdin=None):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        input=stdin,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


class TestClaimWorksheet(unittest.TestCase):
    def test_worksheet_has_exactly_the_claims_checker_fields(self):
        ws, _ = cw.build(ANSWER)
        self.assertTrue(ws, "expected candidate claims")
        for entry in ws:
            self.assertEqual(set(entry), FIELDS)
            self.assertEqual(entry["source"], "")
            self.assertEqual(entry["quote"], "")
            self.assertEqual(entry["kind"], "")
            self.assertEqual(entry["scope"], "")

    def test_ids_are_unique_and_ordered(self):
        ws, _ = cw.build(ANSWER)
        self.assertEqual([e["id"] for e in ws], [f"c{i}" for i in range(1, len(ws) + 1)])

    def test_expected_sentences_are_candidates_and_plain_ones_are_not(self):
        ws, _ = cw.build(ANSWER)
        claims = [e["claim"] for e in ws]
        self.assertTrue(any("42%" in c for c in claims))  # percentage
        self.assertTrue(any(c.startswith("Exampledrug was the first") for c in claims))  # widening word
        self.assertTrue(any(c.startswith("There is no evidence") for c in claims))  # absence phrase
        self.assertTrue(any(c.startswith("Ivacaftor") for c in claims))  # drug name, any case
        self.assertIn("The report covered 2019 to 2023.", claims)  # years, list marker removed
        # negative controls: no number, drug, widening word or absence phrase
        self.assertFalse(any(c.startswith("Thanks for asking") for c in claims))
        self.assertFalse(any(c.startswith("I hope this helps") for c in claims))
        self.assertFalse(any(c.startswith("Talk with your care team") for c in claims))

    def test_flags_record_what_was_found_and_scope_need(self):
        ws, flags = cw.build(ANSWER)
        by_claim = {f["id"]: f for f in flags}
        first = next(e for e in ws if e["claim"].startswith("Exampledrug"))
        absent = next(e for e in ws if e["claim"].startswith("There is no"))
        drug = next(e for e in ws if e["claim"].startswith("Ivacaftor"))
        self.assertIn("first", by_claim[first["id"]]["widening"])
        self.assertTrue(by_claim[first["id"]]["needs_scope"])
        self.assertTrue(by_claim[absent["id"]]["absence"])
        self.assertTrue(by_claim[absent["id"]]["needs_scope"])
        self.assertEqual(by_claim[drug["id"]]["drugs"], ["Ivacaftor"])
        self.assertFalse(by_claim[drug["id"]]["needs_scope"])

    def test_widening_and_absence_words_make_candidates(self):
        sentences = [
            "It now covers more people.",
            "Both groups did well.",
            "This happened because of the change.",
            "It is no longer used.",
            "It is not approved for that group.",
        ]
        for sentence in sentences:
            with self.subTest(sentence=sentence):
                ws, flags = cw.build(sentence)
                self.assertEqual(len(ws), 1)
                self.assertTrue(flags[0]["needs_scope"])

    def test_plain_sentences_are_not_candidates(self):
        sentences = [
            "Ask the team what this means.",
            "Please bring your questions.",
            "Knowledge grows slowly.",
            "The allowance form is long.",  # 'all' inside a word must not count
        ]
        for sentence in sentences:
            with self.subTest(sentence=sentence):
                ws, _ = cw.build(sentence)
                self.assertEqual(ws, [])

    def test_decimals_and_abbreviations_do_not_split(self):
        ws, _ = cw.build("The value was 2.5 in one group, e.g. the older one. Next sentence has 3 items.")
        self.assertEqual(
            [e["claim"] for e in ws],
            ["The value was 2.5 in one group, e.g. the older one.", "Next sentence has 3 items."],
        )

    def test_red_team_claims_are_found_whole(self):
        answers = [
            "Nine out of ten people in the trial got better.",
            "Twice as many people improved in the treatment group.",
            "Half of the people in the study had no change.",
            "This medicine is approved for children.",
            "It works for people with the F508del variant.",
            "There's no link between this diet and lung function.",
            "There’s no link between this diet and lung function.",
            "It isn't approved for that group.",
            "It is safe in pregnancy.",
            "It is recommended for older children.",
            "ETI works for most people with CF.",
            "The modulator was approved in the U.S. in 2019 for older children.",
            "A large percent of people improved.",
        ]
        for answer in answers:
            with self.subTest(answer=answer):
                ws, _ = cw.build(answer)
                self.assertEqual([e["claim"] for e in ws], [answer])

    def test_wrapped_sentence_is_one_claim_on_its_first_line(self):
        ws, flags = cw.build("Thanks.\nIn one study of people with CF, forty-two percent\nimproved after a year.")
        self.assertEqual([e["claim"] for e in ws], ["In one study of people with CF, forty-two percent improved after a year."])
        self.assertEqual(flags[0]["line"], 2)

    def test_list_items_and_headings_are_not_joined_to_the_next_line(self):
        ws, _ = cw.build("## 2019 results\nThe trial had 40 people.\n- Item with 3 parts\n- Item with 4 parts")
        self.assertEqual([e["claim"] for e in ws], ["2019 results", "The trial had 40 people.", "Item with 3 parts", "Item with 4 parts"])

    def test_variant_names_are_found(self):
        _, flags = cw.build("People with G551D or 621+1G>T were in the trial group.")
        self.assertEqual(flags[0]["variants"], ["G551D", "621+1G>T"])
        _, flags = cw.build("The p.Phe508del change was the most common.")
        self.assertEqual(flags[0]["variants"], ["p.Phe508del"])

    def test_ordering_and_routine_words_are_not_claims(self):
        answers = [
            "First, write down your questions.",
            "Now, let's look at your list.",
            "Each visit is a chance to ask.",
            "Every time you go, bring the list.",
            "Double-check your list with the nurse.",
            "One way to start is to write your questions.",
        ]
        for answer in answers:
            with self.subTest(answer=answer):
                self.assertEqual(cw.build(answer)[0], [])

    def test_nearby_sentences_with_markers_stay_claims(self):
        answers = [
            "First, 9 out of 10 people improved.",
            "Each visit, ivacaftor levels were measured.",
            "Now is the first time it was tried in children.",
        ]
        for answer in answers:
            with self.subTest(answer=answer):
                self.assertEqual(len(cw.build(answer)[0]), 1)

    def test_all_flag_includes_every_sentence(self):
        ws, _ = cw.build("Hello there. Ask the team.", include_all=True)
        self.assertEqual(len(ws), 2)

    def test_custom_drug_list_replaces_built_in(self):
        ws, _ = cw.build("Exampledrug helps some people.", drugs=["Exampledrug"])
        self.assertEqual(len(ws), 1)
        ws, _ = cw.build("Ivacaftor is a word here.", drugs=["Exampledrug"])
        self.assertEqual(ws, [])

    def test_cli_writes_worksheet_and_flags(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            a = tmp_path / "answer.txt"
            a.write_text(ANSWER, encoding="utf-8")
            out, flags = tmp_path / "ws.json", tmp_path / "flags.json"
            r = run_cli(str(a), "-o", str(out), "--flags", str(flags))
            self.assertEqual(r.returncode, 0, r.stderr)
            ws = json.loads(out.read_text(encoding="utf-8"))
            self.assertTrue(isinstance(ws, list) and all(set(e) == FIELDS for e in ws))
            self.assertEqual(len(json.loads(flags.read_text(encoding="utf-8"))), len(ws))
            self.assertIn("fill 'scope'", r.stdout)

    def test_cli_stdout_is_pure_json(self):
        r = run_cli(stdin=ANSWER)
        self.assertEqual(r.returncode, 0)
        self.assertTrue(isinstance(json.loads(r.stdout), list))

    def test_cli_exit_1_when_nothing_found(self):
        r = run_cli(stdin="Hello. Ask the team.")
        self.assertEqual(r.returncode, 1)
        self.assertIn("does not mean", r.stderr)

    def test_cli_exit_2_on_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            missing = Path(tmp_dir) / "missing.txt"
            self.assertEqual(run_cli(str(missing)).returncode, 2)

    def test_cli_exit_2_on_empty_drug_list(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            d = Path(tmp_dir) / "drugs.txt"
            d.write_text("# nothing\n", encoding="utf-8")
            self.assertEqual(run_cli("--drugs", str(d), stdin=ANSWER).returncode, 2)


if __name__ == "__main__":
    unittest.main()
