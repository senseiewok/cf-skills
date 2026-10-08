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
Use the nebuliser from the CF clinic before the session.
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


def test_dropped_timing_word_in_a_faithful_looking_rewrite_is_reported():
    # A known cost of the warning-word count: "First, use..." for "...before the session" is reported.
    bad = FAITHFUL.replace("Use the nebuliser from the CF clinic before the session.", "First, use the nebuliser from the CF clinic.")
    assert {"word": "before", "source": 1, "rewrite": 0} in fd.diff(SOURCE, bad)["words"]


# ---------------------------------------------------------------- red-team cases (RT-08 to RT-10): bad pair flagged,
# nearby good pair clean

def differs(src, new, **kw):
    return fd.has_differences(fd.diff(src, new, **kw))


def test_dropped_negation_is_flagged():
    result = fd.diff("Do not take the enzymes with milk.", "Take the enzymes with milk.")
    assert {"word": "not", "source": 1, "rewrite": 0} in result["words"]
    assert not differs("Do not take the enzymes with milk.", "Don't take the enzymes with milk.")


@pytest.mark.parametrize("src, new, word", [
    ("Take the enzymes before meals.", "Take the enzymes after meals.", "before"),
    ("Never mix the two.", "Mix the two.", "never"),
    ("Avoid salty snacks.", "Have salty snacks.", "avoid"),
    ("Use it only at night.", "Use it at night.", "only"),
    ("Do airway clearance every day.", "Do airway clearance every other day.", "every other"),
    ("You can't skip it.", "You can skip it.", "not"),
])
def test_warning_word_changes_are_flagged(src, new, word):
    assert word in [w["word"] for w in fd.diff(src, new)["words"]]


def test_dropped_repeated_dose_is_a_count_change():
    result = fd.diff("Use 2 puffs in the morning and 2 puffs at night.", "Use 2 puffs in the morning.")
    assert result["counts"] == [{"item": "2 puffs", "source": 2, "rewrite": 1}]
    assert not differs("Use 2 puffs in the morning and 2 puffs at night.", "Use 2 puffs in the morning and two puffs at night.")


def test_added_repeated_dose_is_a_count_change():
    assert fd.diff("Take 1 capsule with snacks.", "Take 1 capsule with snacks and 1 capsule with meals.")["counts"]


def test_swapped_numbers_change_the_order():
    src = "Give 2 puffs of the blue inhaler and 4 puffs of the brown inhaler."
    assert fd.diff(src, "Give 4 puffs of the blue inhaler and 2 puffs of the brown inhaler.")["order_changed"] is True
    assert not differs(src, "Give 2 puffs of the blue inhaler. Give 4 puffs of the brown inhaler.")


def test_added_link_is_flagged():
    result = fd.diff("Call the team if you have questions.", "Questions? See cff.example.org for answers. Call the team.")
    assert result["added"]["links"] == ["cff.example.org"]
    assert not differs("See https://example.org/guide.", "Look at https://example.org/guide.")


def test_medicine_name_at_sentence_start_and_in_lower_case_is_a_name():
    result = fd.diff("Creon helps the body digest food.", "Pulmozyme helps the body digest food.")
    assert result["dropped"]["names"] == ["creon"] and result["added"]["names"] == ["pulmozyme"]
    assert fd.diff("Clean the parts.", "Clean the parts, then take ibuprofen.")["added"]["names"] == ["ibuprofen"]
    assert not differs("Creon helps digestion.", "creon helps digestion.")


def test_names_list_adds_names():
    assert fd.diff("Exampledrug helps.", "Otherdrug helps.", names=["exampledrug"])["dropped"]["names"] == ["exampledrug"]
    assert fd.diff("Exampledrug helps.", "Otherdrug helps.")["dropped"]["names"] == []


def test_weekday_and_month_are_names_even_at_sentence_start():
    result = fd.diff("Monday: clinic visit.\nFriday: blood test.", "Tuesday: clinic visit.\nFriday: blood test.")
    assert result["dropped"]["names"] == ["Monday"] and result["added"]["names"] == ["Tuesday"]
    assert not differs("May I ask a question?", "Can I ask a question?")    # 'May' opening a sentence is a verb


@pytest.mark.parametrize("src, new, change", [
    ("Rest for thirty minutes.", "Rest for forty minutes.", {"from": "30 minutes", "to": "40 minutes"}),
    ("Rest for forty-two minutes.", "Rest for forty-three minutes.", {"from": "42 minutes", "to": "43 minutes"}),
    ("Take .5 ml before bed.", "Take .25 ml before bed.", {"from": "0.5 ml", "to": "0.25 ml"}),
    ("Take half a tablet.", "Take 1 tablet.", {"from": "0.5 tablets", "to": "1 tablets"}),
    ("Give a hundred units.", "Give 200 units.", {"from": "100 units", "to": "200 units"}),
])
def test_number_words_and_leading_decimals(src, new, change):
    assert change in fd.diff(src, new)["changed"]


@pytest.mark.parametrize("src, new", [
    ("Once you are home, rest.", "When you are home, rest."),
    ("One of the team will call you.", "A team member will call you."),
    ("Walk 2-3 times a week.", "Walk 2—3 times a week."),
    ("Give up to 10 000 units.", "Give up to 10,000 units."),
    ("Rest for thirty minutes.", "Rest for 30 minutes."),
    ("Take 0.5 ml.", "Take .5 ml."),
    ("Use 2 puffs.", "Use ２ puffs."),
])
def test_same_facts_written_differently_stay_clean(src, new):
    assert not differs(src, new), fd.diff(src, new)


def test_once_before_a_frequency_is_still_a_number():
    assert {"from": "1 times", "to": "2 times"} in fd.diff("Do it once a day.", "Do it twice a day.")["changed"]


# ---------------------------------------------------------------- RT-16: one case per earlier surviving mutation

def test_date_digits_are_not_also_counted_as_numbers():
    assert not differs("Come back on 2026-03-12.", "Come back on 12 March 2026.")


def test_month_year_is_a_date():
    result = fd.diff("Review in March 2026.", "Review in March 2027.")
    assert result["dropped"]["dates"] == ["2026-03"] and result["added"]["dates"] == ["2027-03"]


def test_slash_date_is_kept_as_written():
    result = fd.diff("Bring it on 04/05/2026.", "Bring it on 05/04/2026.")
    assert result["dropped"]["dates"] == ["04/05/2026"] and result["added"]["dates"] == ["05/04/2026"]


def test_trailing_zero_does_not_change_a_number():
    assert not differs("Take 2.50 ml.", "Take 2.5 ml.")


def test_acronym_at_sentence_start_is_a_name():
    assert fd.diff("CF teams help.", "The teams help.")["dropped"]["names"] == ["CF"]


def test_pronoun_i_is_not_a_name():
    assert fd.diff("Then I rest.", "Then we rest.")["dropped"]["names"] == []


def test_iu_and_units_are_the_same_unit():
    assert not differs("Give 400 IU.", "Give 400 units.")


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


def test_cli_fact_diff_names_file(tmp_path):
    s, n, names = tmp_path / "s.txt", tmp_path / "n.txt", tmp_path / "names.txt"
    s.write_text("Exampledrug helps.", encoding="utf-8")
    n.write_text("Otherdrug helps.", encoding="utf-8")
    names.write_text("# extra names\nexampledrug\n", encoding="utf-8")
    assert run("fact_diff.py", str(s), str(n)).returncode == 0
    r = run("fact_diff.py", str(s), str(n), "--names", str(names))
    assert r.returncode == 1 and "DROPPED name: exampledrug" in r.stdout
    assert run("fact_diff.py", str(s), str(n), "--names", str(tmp_path / "missing.txt")).returncode == 2


def test_cli_readability_max_grade():
    assert run("readability.py", "--max-grade", "6", stdin=FAITHFUL).returncode == 0
    hard = "Comprehensive pharmacological management necessitates individualised consideration of concomitant medications."
    r = run("readability.py", "--max-grade", "6", "--json", stdin=hard)
    assert r.returncode == 1 and json.loads(r.stdout)["above_max_grade"] is True
    assert run("readability.py", stdin="   ").returncode == 2
