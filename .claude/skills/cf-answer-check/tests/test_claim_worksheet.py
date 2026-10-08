"""Tests for claim_worksheet.py, with negative controls: plain sentences must not become claims.

The answer texts are invented. Their 'facts' are placeholders and are not true or false statements about CF.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

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


def test_worksheet_has_exactly_the_claims_checker_fields():
    ws, _ = cw.build(ANSWER)
    assert ws, "expected candidate claims"
    for entry in ws:
        assert set(entry) == FIELDS
        assert entry["source"] == entry["quote"] == entry["kind"] == entry["scope"] == ""


def test_ids_are_unique_and_ordered():
    ws, _ = cw.build(ANSWER)
    assert [e["id"] for e in ws] == [f"c{i}" for i in range(1, len(ws) + 1)]


def test_expected_sentences_are_candidates_and_plain_ones_are_not():
    ws, _ = cw.build(ANSWER)
    claims = [e["claim"] for e in ws]
    assert any("42%" in c for c in claims)                        # percentage
    assert any(c.startswith("Exampledrug was the first") for c in claims)   # widening word
    assert any(c.startswith("There is no evidence") for c in claims)        # absence phrase
    assert any(c.startswith("Ivacaftor") for c in claims)                   # drug name, any case
    assert "The report covered 2019 to 2023." in claims                     # years, list marker removed
    # negative controls: no number, drug, widening word or absence phrase
    assert not any(c.startswith("Thanks for asking") for c in claims)
    assert not any(c.startswith("I hope this helps") for c in claims)
    assert not any(c.startswith("Talk with your care team") for c in claims)


def test_flags_record_what_was_found_and_scope_need():
    _, flags = cw.build(ANSWER)
    by_claim = {f["id"]: f for f in flags}
    ws, _ = cw.build(ANSWER)
    first = next(e for e in ws if e["claim"].startswith("Exampledrug"))
    absent = next(e for e in ws if e["claim"].startswith("There is no"))
    drug = next(e for e in ws if e["claim"].startswith("Ivacaftor"))
    assert "first" in by_claim[first["id"]]["widening"] and by_claim[first["id"]]["needs_scope"]
    assert by_claim[absent["id"]]["absence"] and by_claim[absent["id"]]["needs_scope"]
    assert by_claim[drug["id"]]["drugs"] == ["Ivacaftor"] and not by_claim[drug["id"]]["needs_scope"]


@pytest.mark.parametrize("sentence", [
    "It now covers more people.", "Both groups did well.", "This happened because of the change.",
    "It is no longer used.", "It is not approved for that group.",
])
def test_widening_and_absence_words_make_candidates(sentence):
    ws, flags = cw.build(sentence)
    assert len(ws) == 1 and flags[0]["needs_scope"]


@pytest.mark.parametrize("sentence", [
    "Ask the team what this means.", "Please bring your questions.", "Knowledge grows slowly.",
    "The allowance form is long.",   # 'all' inside a word must not count
])
def test_plain_sentences_are_not_candidates(sentence):
    ws, _ = cw.build(sentence)
    assert ws == []


def test_decimals_and_abbreviations_do_not_split():
    ws, _ = cw.build("The value was 2.5 in one group, e.g. the older one. Next sentence has 3 items.")
    assert [e["claim"] for e in ws] == ["The value was 2.5 in one group, e.g. the older one.", "Next sentence has 3 items."]


# ---------------------------------------------------------------- red-team cases (RT-11, RT-12): each a single claim

@pytest.mark.parametrize("answer", [
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
])
def test_red_team_claims_are_found_whole(answer):
    ws, _ = cw.build(answer)
    assert [e["claim"] for e in ws] == [answer]


def test_wrapped_sentence_is_one_claim_on_its_first_line():
    ws, flags = cw.build("Thanks.\nIn one study of people with CF, forty-two percent\nimproved after a year.")
    assert [e["claim"] for e in ws] == ["In one study of people with CF, forty-two percent improved after a year."]
    assert flags[0]["line"] == 2


def test_list_items_and_headings_are_not_joined_to_the_next_line():
    ws, _ = cw.build("## 2019 results\nThe trial had 40 people.\n- Item with 3 parts\n- Item with 4 parts")
    assert [e["claim"] for e in ws] == ["2019 results", "The trial had 40 people.", "Item with 3 parts", "Item with 4 parts"]


def test_variant_names_are_found():
    _, flags = cw.build("People with G551D or 621+1G>T were in the trial group.")
    assert flags[0]["variants"] == ["G551D", "621+1G>T"]
    _, flags = cw.build("The p.Phe508del change was the most common.")
    assert flags[0]["variants"] == ["p.Phe508del"]


@pytest.mark.parametrize("answer", [
    "First, write down your questions.",
    "Now, let's look at your list.",
    "Each visit is a chance to ask.",
    "Every time you go, bring the list.",
    "Double-check your list with the nurse.",
    "One way to start is to write your questions.",
])
def test_ordering_and_routine_words_are_not_claims(answer):
    assert cw.build(answer)[0] == []


@pytest.mark.parametrize("answer", [
    "First, 9 out of 10 people improved.",
    "Each visit, ivacaftor levels were measured.",
    "Now is the first time it was tried in children.",
])
def test_nearby_sentences_with_markers_stay_claims(answer):
    assert len(cw.build(answer)[0]) == 1


def test_all_flag_includes_every_sentence():
    ws, _ = cw.build("Hello there. Ask the team.", include_all=True)
    assert len(ws) == 2


def test_custom_drug_list_replaces_built_in():
    ws, _ = cw.build("Exampledrug helps some people.", drugs=["Exampledrug"])
    assert len(ws) == 1
    ws, _ = cw.build("Ivacaftor is a word here.", drugs=["Exampledrug"])
    assert ws == []


# ---------------------------------------------------------------- command line

def run(*args, stdin=None):
    return subprocess.run([sys.executable, str(SCRIPT), *args], input=stdin, capture_output=True,
                          text=True, encoding="utf-8")


def test_cli_writes_worksheet_and_flags(tmp_path):
    a = tmp_path / "answer.txt"
    a.write_text(ANSWER, encoding="utf-8")
    out, flags = tmp_path / "ws.json", tmp_path / "flags.json"
    r = run(str(a), "-o", str(out), "--flags", str(flags))
    assert r.returncode == 0, r.stderr
    ws = json.loads(out.read_text(encoding="utf-8"))
    assert isinstance(ws, list) and all(set(e) == FIELDS for e in ws)
    assert len(json.loads(flags.read_text(encoding="utf-8"))) == len(ws)
    assert "fill 'scope'" in r.stdout


def test_cli_stdout_is_pure_json():
    r = run(stdin=ANSWER)
    assert r.returncode == 0
    assert isinstance(json.loads(r.stdout), list)


def test_cli_exit_1_when_nothing_found():
    r = run(stdin="Hello. Ask the team.")
    assert r.returncode == 1 and "does not mean" in r.stderr


def test_cli_exit_2_on_missing_file(tmp_path):
    assert run(str(tmp_path / "missing.txt")).returncode == 2


def test_cli_exit_2_on_empty_drug_list(tmp_path):
    d = tmp_path / "drugs.txt"
    d.write_text("# nothing\n", encoding="utf-8")
    assert run("--drugs", str(d), stdin=ANSWER).returncode == 2
