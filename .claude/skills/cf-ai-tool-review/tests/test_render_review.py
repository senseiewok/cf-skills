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
