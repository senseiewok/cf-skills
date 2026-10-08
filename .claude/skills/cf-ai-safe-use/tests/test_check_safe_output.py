"""Tests for check_safe_output.py. Every rule has a bad answer that must trip it and a good answer that must pass.

All text here is invented. No real person, record, phone number or address appears.
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

import check_safe_output as cso

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_safe_output.py"

GOOD = """I can share general information, not advice for one person.

Airway clearance is a set of ways to help move mucus out of the lungs. Your CF care team can show which ways suit you.

I am not sure about the numbers you asked for, so I will not guess. You could ask the care team what the result means for you.

To find the guide, search for the organisation's name and "airway clearance". Check on the official page before relying on it.

Please check this with your CF care team before changing anything."""


def rules(text):
    return {f.rule for f in cso.check(text)}


def with_line(extra):
    return GOOD + "\n\n" + extra


def test_good_answer_has_no_flags():
    assert cso.check(GOOD) == []


# ---------------------------------------------------------------- one bad line per rule, on top of the good answer

EMAIL = "sam.example" + "@" + "example.org"   # built at run time so no address sits in the source

BAD_LINES = [
    ("The usual amount is 250 mg.", "dose"),
    ("Most people use 2 puffs.", "dose"),
    ("It is taken twice daily.", "dose"),
    ("It is taken two times a day.", "dose"),
    ("It is taken every 6 hours.", "dose"),
    ("You should take it with food.", "directive"),
    ("Stop taking it if it upsets you.", "directive"),
    ("You have an infection.", "directive"),
    ("You are eligible for this medicine.", "directive"),
    ("Your genotype means this one suits you.", "directive"),
    ("Increase your dose when you feel worse.", "directive"),
    ("This will always help.", "absolute"),
    ("It is guaranteed to work.", "absolute"),
    ("Some say it is a cure.", "absolute"),
    ("See https://example.org/cf-guide for more.", "unchecked-link"),
    ("See www.example.org for more.", "unchecked-link"),
    ("Call 555-010-0199 to ask.", "unchecked-link"),
    ("Call +44 20 7946 0000 to ask.", "unchecked-link"),
    ("Thanks for writing, born on 3 May.", "identifier"),
    ("About the person with DOB: 2015, here is an answer.", "identifier"),
    ("About the note from 04/05/2015, here is an answer.", "identifier"),
    ("About MRN 4455, here is an answer.", "identifier"),
    ("About record 99887766, here is an answer.", "identifier"),
    ("I will reply to " + EMAIL + " later.", "identifier"),
]


@pytest.mark.parametrize("line, rule", BAD_LINES)
def test_bad_line_trips_its_rule(line, rule):
    found = rules(with_line(line))
    assert rule in found, (line, found)


@pytest.mark.parametrize("line, rule", [b for b in BAD_LINES if b[1] != "identifier" or "record" not in b[0]])
def test_bad_line_trips_only_expected_rules(line, rule):
    # The good answer carries 'not sure', so tier never fires here; a dose with a two-digit number is allowed to.
    found = rules(with_line(line))
    assert found <= {rule, "tier"}, (line, found)


def test_link_with_official_page_in_same_paragraph_passes():
    text = with_line("See https://example.org/cf-guide and check on the official page that it is current.")
    assert "unchecked-link" not in rules(text)


def test_phone_with_official_page_in_same_paragraph_passes():
    text = with_line("The number shown there was 555-010-0199; check on the official page, it may have changed.")
    assert "unchecked-link" not in rules(text)


def test_link_in_other_paragraph_than_official_page_is_flagged():
    text = "Check on the official page.\n\nSee https://example.org/x for more.\n\nAsk your care team."
    assert "unchecked-link" in rules(text)


# ---------------------------------------------------------------- care-team pointer

def test_medical_answer_without_care_team_is_flagged():
    assert rules("Enzymes help the body digest food. I am not sure of the details.") == {"care-team"}


def test_medical_answer_with_care_team_passes():
    assert rules("Enzymes help the body digest food. I am not sure of the details. Ask your CF care team.") == set()


def test_non_medical_answer_needs_no_care_team():
    assert rules("Here is a shorter version of your email to the school.") == set()


# ---------------------------------------------------------------- tier

TIER_BAD = "A study found that 40% of people in it felt better. Ask your care team about it."


def test_number_without_tier_is_flagged():
    assert rules(TIER_BAD) == {"tier"}


def test_study_claim_without_number_or_tier_is_flagged():
    assert rules("Research shows this helps. Ask your care team.") == {"tier"}


def test_number_with_tier_passes():
    text = "T1: a study found that 40% of people in it felt better (quoted from the paper, checked 2026-10-01). Ask your care team."
    assert rules(text) == set()


def test_number_with_not_sure_passes():
    assert rules("I am not sure, but I have seen 40% quoted. Ask your care team.") == set()


def test_iso_source_date_is_not_an_identifier():
    assert "identifier" not in rules("T1, checked 2026-10-01. Ask your care team.")


# ---------------------------------------------------------------- line numbers and CLI

def test_line_numbers_point_at_the_line():
    flags = cso.check("Hello.\nIt is taken twice daily.\nAsk your care team. T0.")
    dose = [f for f in flags if f.rule == "dose"]
    assert dose and dose[0].line == 2


def run(args, stdin=None):
    return subprocess.run([sys.executable, str(SCRIPT), *args], input=stdin, capture_output=True,
                          text=True, encoding="utf-8")


def test_cli_exit_0_on_good(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text(GOOD, encoding="utf-8")
    r = run([str(p)])
    assert r.returncode == 0, r.stdout


def test_cli_exit_1_and_json_on_bad():
    r = run(["--json"], stdin=with_line("You should take 250 mg."))
    assert r.returncode == 1
    data = json.loads(r.stdout)
    assert {d["rule"] for d in data} >= {"dose", "directive"}
    assert all({"line", "rule", "text", "why"} <= set(d) for d in data)


def test_cli_exit_2_on_missing_file(tmp_path):
    r = run([str(tmp_path / "missing.txt")])
    assert r.returncode == 2


def test_cli_exit_2_on_non_utf8(tmp_path):
    p = tmp_path / "bad.txt"
    p.write_bytes(b"\xff\xfe\xfa not utf8 \xff")
    assert run([str(p)]).returncode == 2


def test_help_mentions_heuristic():
    r = run(["--help"])
    assert r.returncode == 0 and "heuristic" in r.stdout
