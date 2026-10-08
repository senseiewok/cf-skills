"""Tests for readability.py and fact_diff.py, with a negative control for each kind of difference.

All texts are invented examples. They are not instructions for anyone's care.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import fact_diff as fd
import readability as rd

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"

SOURCE = """Airway clearance

Do your airway clearance 2 times a day, for about 30 minutes each time.
Use the nebuliser from the CF clinic before the session.
Clean the parts after every use. Replace the filters every 3 months.
Call the CF team on Monday if you have questions."""

FAITHFUL = """Airway clearance

Do airway clearance twice a day.
Each time takes about 30 minutes.
First, use the nebuliser from the CF clinic.
Clean the parts after you use them.
Put in new filters every 3 months.
Have questions? Call the CF team on Monday."""


# ---------------------------------------------------------------- fact_diff

def test_faithful_rewrite_passes():
    result = fd.diff(SOURCE, FAITHFUL)
    assert not fd.has_differences(result), result


def test_changed_frequency_is_flagged():
    bad = FAITHFUL.replace("twice a day", "3 times a day")
    result = fd.diff(SOURCE, bad)
    assert {"from": "2 times", "to": "3 times"} in result["changed"]


def test_changed_frequency_in_words_is_flagged():
    bad = FAITHFUL.replace("twice a day", "three times a day")
    assert {"from": "2 times", "to": "3 times"} in fd.diff(SOURCE, bad)["changed"]


def test_added_number_is_flagged():
    bad = FAITHFUL + "\nDrink 8 glasses of water."
    result = fd.diff(SOURCE, bad)
    assert "8 glasses" in result["added"]["numbers"]


def test_dropped_number_is_flagged():
    bad = FAITHFUL.replace("Each time takes about 30 minutes.\n", "")
    assert "30 minutes" in fd.diff(SOURCE, bad)["dropped"]["numbers"]


def test_dropped_name_is_flagged():
    bad = FAITHFUL.replace("Call the CF team on Monday.", "Call the team.")
    dropped = fd.diff(SOURCE, bad)["dropped"]["names"]
    assert "Monday" in dropped


def test_added_name_is_flagged():
    bad = FAITHFUL + "\nAsk Dr Example about it."
    assert "Example" in fd.diff(SOURCE, bad)["added"]["names"]


def test_changed_date_is_flagged():
    src = "Your next visit is on 12 March 2026."
    assert fd.diff(src, "Your next visit is on March 12, 2026.")["added"]["dates"] == []
    result = fd.diff(src, "Your next visit is on 13 March 2026.")
    assert result["added"]["dates"] == ["2026-03-13"] and result["dropped"]["dates"] == ["2026-03-12"]


def test_percent_forms_match():
    assert not fd.has_differences(fd.diff("About 50 percent of the dose.", "About 50% of the dose."))
    assert fd.has_differences(fd.diff("About 50 percent of the dose.", "About 60% of the dose."))


def test_changed_unit_is_flagged():
    result = fd.diff("Take 250 mg.", "Take 250 mcg.")
    assert result["dropped"]["numbers"] == ["250 mg"] and result["added"]["numbers"] == ["250 mcg"]


def test_ranges_and_commas():
    assert not fd.has_differences(fd.diff("Walk 2-3 times and 1,000 steps.", "Walk 2 to 3 times and 1000 steps."))


def test_sentence_start_word_is_not_a_name():
    assert fd.diff("Rest well tonight.", "Sleep well tonight.")["added"]["names"] == []


# ---------------------------------------------------------------- readability

@pytest.mark.parametrize("word, n", [
    ("cat", 1), ("make", 1), ("the", 1), ("table", 2), ("people", 2), ("breathing", 2),
    ("readability", 5), ("makes", 1), ("uses", 2), ("liked", 1), ("added", 2), ("whole", 1),
    ("free", 1), ("medicine", 3), ("30%", 1),
])
def test_syllable_heuristic(word, n):
    assert rd.syllables(word) == n


def test_grade_formula_by_hand():
    # 2 sentences, 8 words, 8 syllables: 0.39 * 4 + 11.8 * 1 - 15.59 = -2.23
    r = rd.measure("The cat sat down. The dog ran off.")
    assert (r["words"], r["sentences"], r["syllables"]) == (8, 2, 8)
    assert r["flesch_kincaid_grade"] == round(0.39 * 4 + 11.8 * 1 - 15.59, 1)
    assert r["average_sentence_length"] == 4.0


def test_list_lines_end_sentences_and_decimals_do_not():
    r = rd.measure("Bring these\n- your list\n- your questions\nIt took 2.5 hours, e.g. a long time.")
    assert r["sentences"] == 4


def test_harder_text_scores_higher():
    easy = rd.measure(FAITHFUL)["flesch_kincaid_grade"]
    hard = rd.measure("Comprehensive pharmacological management necessitates individualised consideration of "
                      "concomitant medications, physiological characteristics and longitudinal monitoring.")["flesch_kincaid_grade"]
    assert hard > easy + 5


def test_empty_text_is_an_error():
    with pytest.raises(ValueError):
        rd.measure("  \n ")


# ---------------------------------------------------------------- command lines

def run(script, *args, stdin=None):
    return subprocess.run([sys.executable, str(SCRIPTS / script), *args], input=stdin,
                          capture_output=True, text=True, encoding="utf-8")


def test_cli_fact_diff_exit_codes(tmp_path):
    s = tmp_path / "s.txt"
    s.write_text(SOURCE, encoding="utf-8")
    good = tmp_path / "g.txt"
    good.write_text(FAITHFUL, encoding="utf-8")
    bad = tmp_path / "b.txt"
    bad.write_text(FAITHFUL.replace("twice", "3 times"), encoding="utf-8")
    assert run("fact_diff.py", str(s), str(good)).returncode == 0
    r = run("fact_diff.py", str(s), str(bad), "--json")
    assert r.returncode == 1 and json.loads(r.stdout)["changed"]
    assert run("fact_diff.py", str(s), str(tmp_path / "missing.txt")).returncode == 2


def test_cli_readability_max_grade():
    assert run("readability.py", "--max-grade", "6", stdin=FAITHFUL).returncode == 0
    hard = "Comprehensive pharmacological management necessitates individualised consideration of concomitant medications."
    r = run("readability.py", "--max-grade", "6", "--json", stdin=hard)
    assert r.returncode == 1 and json.loads(r.stdout)["above_max_grade"] is True
    assert run("readability.py", stdin="   ").returncode == 2
