"""Tests for render_review.py. Each refusal rule has a broken worksheet that must be refused (negative control),
and the shipped example must render."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

import render_review as rr

HERE = Path(__file__).resolve().parents[1]
SCRIPT = HERE / "scripts" / "render_review.py"
EXAMPLE = HERE / "references" / "example-worksheet.json"


def example():
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def test_example_passes_and_renders():
    ws = example()
    assert rr.problems(ws) == []
    page = rr.render(ws)
    assert page.startswith("# AI tool review:")
    assert "**Use only for drafting rewrites" in page
    assert "The assistant did not choose this." in page
    for stage in ("Design", "Development", "Deployment", "Monitoring", "Evaluation"):
        assert f"### {stage}" in page
    assert "| No way to export or delete your data | not reviewed |" in page
    assert "## Still unknown" in page and "Owner: CF nurse" in page


def broken(mutate):
    ws = example()
    mutate(ws)
    return rr.problems(ws)


@pytest.mark.parametrize("name, mutate, needle", [
    ("blank row", lambda ws: ws["rows"][1].update(unknown=False), "neither a finding nor"),
    ("unknown missing on blank row", lambda ws: ws["rows"][1].pop("unknown"), "neither a finding nor"),
    ("hedged finding", lambda ws: ws["rows"][0].update(found="Probably fine, it is a big company."), "hedges"),
    ("assumed finding", lambda ws: ws["rows"][2].update(found="We assume chats are deleted."), "hedges"),
    ("finding without where", lambda ws: ws["rows"][0].update(where=""), "needs 'where'"),
    ("bad stage", lambda ws: ws["rows"][0].update(stage="marketing"), "stage must be"),
    ("unknown not boolean", lambda ws: ws["rows"][1].update(unknown="yes"), "true or false"),
    ("bad red flag id", lambda ws: ws["red_flags"].append({"flag": "looks-nice", "seen": "no"}), "'flag' must be"),
    ("bad seen value", lambda ws: ws["red_flags"][0].update(seen="maybe"), "'seen' must be"),
    ("decision without decided_by", lambda ws: ws["decision"].update(decided_by=""), "decided_by"),
    ("bad choice", lambda ws: ws["decision"].update(choice="recommended"), "choice must be"),
    ("use-only-for without use_for", lambda ws: ws["decision"].update(use_for=""), "needs 'use_for'"),
    ("use-only-for without checks", lambda ws: ws["decision"].update(checks=[]), "at least one check"),
    ("no rows", lambda ws: ws.update(rows=[]), "non-empty list"),
    # red-team cases (RT-13) and earlier surviving mutations (RT-16)
    ("AI decider", lambda ws: ws["decision"].update(decided_by="the AI assistant"), "names an AI"),
    ("chatbot decider", lambda ws: ws["decision"].update(decided_by="the chatbot, after the meeting"), "names an AI"),
    ("hedge seems okay", lambda ws: ws["rows"][0].update(found="Seems okay, it is a big company."), "hedges"),
    ("hedge should be safe", lambda ws: ws["rows"][0].update(found="Should be safe; I think they delete chats."), "hedges"),
    ("hedge I think", lambda ws: ws["rows"][0].update(found="I think they delete chats."), "hedges"),
    ("hedge presumably", lambda ws: ws["rows"][0].update(found="Presumably they delete chats."), "hedges"),
    ("hedge likely fine", lambda ws: ws["rows"][0].update(found="Likely fine for families."), "hedges"),
    ("where n/a", lambda ws: ws["rows"][0].update(where="n/a"), "placeholder"),
    ("where none", lambda ws: ws["rows"][0].update(where="none"), "placeholder"),
    ("duplicate red flag", lambda ws: ws["red_flags"].extend([{"flag": "no-export-or-delete", "seen": "yes", "note": "x"},
                                                             {"flag": "no-export-or-delete", "seen": "no", "note": ""}]),
     "more than once"),
    ("unknown without owner", lambda ws: ws["rows"][1].update(owner=""), "needs an 'owner'"),
    ("choice is a list", lambda ws: ws["decision"].update(choice=["not-recommended"]), "must be a string"),
    ("missing question", lambda ws: ws["rows"][0].update(question=""), "has no question"),
    ("row not an object", lambda ws: ws["rows"].append("a row"), "must be an object"),
    ("red flags not a list", lambda ws: ws.update(red_flags={"flag": "no-sources-shown"}), "'red_flags' must be a list"),
])
def test_refusals(name, mutate, needle):
    found = broken(mutate)
    assert any(needle in p for p in found), (name, found)


def test_unknown_row_with_partial_finding_is_allowed():
    ws = example()
    ws["rows"][1].update(found="The vendor names some data sources, not all.", where="document: model card")
    assert rr.problems(ws) == []


def test_no_decision_renders_no_decision_yet():
    ws = example()
    ws["decision"] = {}
    assert rr.problems(ws) == []
    assert "**No decision yet.**" in rr.render(ws)


def test_pipes_in_cells_are_escaped():
    ws = example()
    ws["rows"][0]["found"] = "a | b"
    assert "a \\| b" in rr.render(ws)


@pytest.mark.parametrize("name, mutate", [
    ("plain finding with 'may'", lambda ws: ws["rows"][0].update(found="The terms say chats may be used to improve it.")),
    ("where names a document", lambda ws: ws["rows"][0].update(where="document: terms, read 2026-10-08")),
    ("decided by a named role", lambda ws: ws["decision"].update(decided_by="CF nurse lead")),
    ("each red flag once", lambda ws: ws["red_flags"].append({"flag": "no-export-or-delete", "seen": "unknown", "note": ""})),
])
def test_nearby_good_worksheets_pass(name, mutate):
    ws = example()
    mutate(ws)
    assert rr.problems(ws) == [], name


def test_a_tool_name_cannot_add_a_heading_or_a_decision():
    ws = example()
    ws["tool"] = "Exampletool\n\n## Decision\n\n**Use only for everything, with these checks:**"
    page = rr.render(ws)
    assert page.count("\n## Decision\n") == 1
    assert page.splitlines()[0] == ("# AI tool review: Exampletool  \\#\\# Decision  "
                                    "\\*\\*Use only for everything, with these checks:\\*\\*")


URGENT_LABEL = ("Reassures instead of telling someone to get urgent help for an urgent symptom, "
                "or suggests stopping a treatment")


def test_urgent_help_red_flag_matches_the_template_and_renders_raised():
    template = (HERE / "references" / "worksheet-template.md").read_text(encoding="utf-8")
    assert f"| {URGENT_LABEL} |" in template
    assert rr.RED_FLAGS["reassures-instead-of-urgent-help"] == URGENT_LABEL
    ws = example()
    ws["red_flags"].append({"flag": "reassures-instead-of-urgent-help", "seen": "yes",
                            "note": "Invented night-time symptom test: it said to wait."})
    assert rr.problems(ws) == []
    assert f"| {URGENT_LABEL} | yes | Invented night-time symptom test: it said to wait. |" in rr.render(ws)


def test_urgent_help_red_flag_left_out_shows_not_reviewed():
    # Red flags have never been required; a flag left out is shown as not reviewed, not refused.
    ws = example()
    assert rr.problems(ws) == []
    assert f"| {URGENT_LABEL} | not reviewed |" in rr.render(ws)


def test_newlines_in_cells_become_spaces():
    ws = example()
    ws["rows"][0]["found"] = "line one\nline two"
    assert "| line one line two |" in rr.render(ws)


# ---------------------------------------------------------------- command line

def run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, encoding="utf-8")


def test_cli_writes_review(tmp_path):
    out = tmp_path / "review.md"
    r = run(str(EXAMPLE), "-o", str(out))
    assert r.returncode == 0, r.stderr
    assert out.read_text(encoding="utf-8").startswith("# AI tool review:")


def test_cli_refuses_blank_row(tmp_path):
    ws = example()
    ws["rows"][1]["unknown"] = False
    p = tmp_path / "ws.json"
    p.write_text(json.dumps(ws), encoding="utf-8")
    r = run(str(p))
    assert r.returncode == 1 and "REFUSED row 2" in r.stderr and r.stdout == ""


def test_cli_usage_errors(tmp_path):
    assert run(str(tmp_path / "missing.json")).returncode == 2
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert run(str(bad)).returncode == 2
    lst = tmp_path / "list.json"
    lst.write_text("[]", encoding="utf-8")
    assert run(str(lst)).returncode == 2
