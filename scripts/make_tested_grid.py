#!/usr/bin/env python3
"""Build docs/tested-with.md, the grid of the CF care skills against the AI models and products they were tried on, from docs/tested-with.json.

Usage:  python scripts/make_tested_grid.py [ROOT] [--check]

Without --check it writes the page. With --check it writes nothing and exits 1 if the page is out of date or the data is inconsistent.

A cell is one of:
  tested   cases, pass, partial, fail (they must add up), plus a date; shown as "pass/cases pass, partial, fail"
  small    a short earlier run on some cases, no pass counts; shown as "small run, N cases"
  pending  not tried yet; no numbers allowed
Every skill that ships a references/paste-ready.md must be a row, and every row must have every column, so a missing result cannot hide.

The counts are data, not typing. Each judged reply is a row in docs/tested-with-runs/<date>/rows.json (skill, case, model, condition,
box wording, verdict, the judge's short reason and a SHA-256 of the reply; never the reply itself). A tested cell dated D is recounted
from the rows of run D with test "grid", the cell's skill and model, condition "standard" and wording D; the box-effect table is
recounted from the rows of data["effect_run"] with test "box-effect". --check fails on any mismatch and on a duplicate row.
The page also carries two notes worked out from the rows: how far the judges moved when they scored the same replies twice
(matched by SHA-256), and how many eval cases marked "suspect" in evals/cases.json are inside the counts.
"""

import argparse
import json
import sys
from pathlib import Path

STATUSES = ("tested", "small", "pending")
VERDICTS = ("pass", "partial", "fail")
ROW_KEYS = ("test", "skill", "case", "model", "condition", "wording", "verdict", "why", "reply_sha256")
KEY = ("test", "skill", "case", "model", "condition", "wording")
MARK = "<!-- Generated file: do not edit by hand. Run python scripts/make_tested_grid.py. -->"
RUNS = Path("docs") / "tested-with-runs"


def load_runs(root):
    """{run date: list of rows} from docs/tested-with-runs/<date>/rows.json."""
    runs = {}
    d = Path(root) / RUNS
    if d.is_dir():
        for f in sorted(d.glob("*/rows.json")):
            runs[f.parent.name] = json.loads(f.read_text(encoding="utf-8"))["rows"]
    return runs


def load_suspect(root):
    """{skill: [case ids marked suspect]} from each skill's evals/cases.json."""
    out = {}
    for f in sorted((Path(root) / ".claude" / "skills").glob("*/evals/cases.json")):
        cases = json.loads(f.read_text(encoding="utf-8")).get("cases", [])
        ids = [c["id"] for c in cases if c.get("suspect") is True]
        if ids:
            out[f.parent.parent.name] = ids
    return out


def tally(rows):
    t = {v: 0 for v in VERDICTS}
    for r in rows:
        t[r["verdict"]] += 1
    t["cases"] = len(rows)
    return t


def run_problems(runs):
    """Rows that are malformed, or the same reply judged twice in one run."""
    out = []
    for date, rows in sorted(runs.items()):
        seen = set()
        for n, r in enumerate(rows, 1):
            missing = [k for k in ROW_KEYS if k not in r]
            if missing:
                out.append(f"runs/{date} row {n}: missing {missing}")
                continue
            if r["verdict"] not in VERDICTS:
                out.append(f"runs/{date} row {n}: verdict {r['verdict']!r} is not one of {VERDICTS}")
            k = tuple(r[x] for x in KEY)
            if k in seen:
                out.append(f"runs/{date}: duplicate row {dict(zip(KEY, k))}")
            seen.add(k)
    return out


def recount_problems(data, runs):
    """Every tested cell and every box-effect count must equal a count of the committed rows."""
    out = []
    model = {c["id"]: c.get("model") for c in data["columns"]}

    def compare(where, cell, rows, source):
        got = tally(rows)
        if not rows:
            out.append(f"{where}: no rows in {source}")
        elif any(got[k] != cell.get(k) for k in ("cases",) + VERDICTS):
            out.append(f"{where}: the rows in {source} give {got['pass']} pass, {got['partial']} partial, {got['fail']} fail of {got['cases']};"
                       f" the data says {cell.get('pass')}, {cell.get('partial')}, {cell.get('fail')} of {cell.get('cases')}")

    for s, row in data["cells"].items():
        for cid, cell in row.items():
            if cell.get("status") != "tested":
                continue
            date = cell.get("date")
            if date not in runs:
                out.append(f"{s} / {cid}: no run data in {RUNS.as_posix()}/{date}")
                continue
            sel = [r for r in runs[date] if r.get("test") == "grid" and r.get("skill") == s and r.get("model") == model.get(cid)
                   and r.get("condition") == "standard" and r.get("wording") == date]
            compare(f"{s} / {cid}", cell, sel, f"runs/{date}")
    if data.get("effect"):
        date = data.get("effect_run")
        if date not in runs:
            out.append(f"effect: no run data in {RUNS.as_posix()}/{date}")
        else:
            for e in data["effect"]:
                for cid, v in e["models"].items():
                    sel = [r for r in runs[date] if r.get("test") == "box-effect" and r.get("model") == model.get(cid)
                           and r.get("condition") == e.get("condition_id")]
                    compare(f"effect / {e['condition']} / {cid}", v, sel, f"runs/{date}")
    return out


def drift(runs):
    """Replies judged in two runs, matched by SHA-256: [(skill, earlier run, later run, replies, passes then, passes later, their wording, newer)].

    newer is (passes, replies) for the later run's own wording of that skill, or None when the later run has no newer wording."""
    out = []
    dates = sorted(runs)
    for i, a in enumerate(dates):
        for b in dates[i + 1:]:
            first = {(r["skill"], r["model"], r["case"], r["reply_sha256"]): r for r in runs[a] if r["test"] == "grid"}
            by_skill = {}
            for r in runs[b]:
                k = (r["skill"], r["model"], r["case"], r["reply_sha256"])
                if r["test"] == "grid" and k in first:
                    by_skill.setdefault(r["skill"], []).append((first[k], r))
            for s, pairs in sorted(by_skill.items()):
                wording = pairs[0][1]["wording"]
                newer = [r for r in runs[b] if r["test"] == "grid" and r["skill"] == s and r["condition"] == "standard" and r["wording"] == b]
                then = sum(p[0]["verdict"] == "pass" for p in pairs)
                now = sum(p[1]["verdict"] == "pass" for p in pairs)
                gain = None
                if newer and b != wording:
                    gain = (sum(r["verdict"] == "pass" for r in newer), len(newer))
                out.append((s, a, b, len(pairs), then, now, wording, gain))
    return out


def drift_note(runs):
    parts = []
    for s, a, b, n, then, now, wording, gain in drift(runs):
        line = (f"`{s}`: the same {n} replies scored {then} pass when judged on {a} and {now} when judged again on {b},"
                f" a move of {now - then:+d} with nothing in the replies changed")
        if gain:
            g = gain[0] - now
            line += (f"; in the {b} batch the {b} wording scored {gain[0]} of {gain[1]} against {now} for the same cases with the {wording} wording,"
                     f" a gain of {g:+d}, " + ("within that drift" if abs(g) <= abs(now - then) else "larger than that drift, though still one reply per case"))
        parts.append(line)
    if not parts:
        return None
    return ("**The judges drift.** The same reply text (matched by its SHA-256 in `docs/tested-with-runs/`) does not always get the same verdict"
            " twice. " + ". ".join(parts) + ". So a change smaller than the drift is not evidence that a rewording helped.")


def suspect_note(data, runs, suspect):
    if not suspect:
        return None
    flagged = {(s, c) for s, ids in suspect.items() for c in ids}
    model = {c["id"]: c.get("model") for c in data["columns"]}
    total = hit = 0
    for s, row in data["cells"].items():
        for cid, cell in row.items():
            if cell.get("status") != "tested" or cell.get("date") not in runs:
                continue
            for r in runs[cell["date"]]:
                if (r["test"] == "grid" and r["skill"] == s and r["model"] == model.get(cid) and r["condition"] == "standard"
                        and r["wording"] == cell["date"]):
                    total += 1
                    hit += (s, r["case"]) in flagged
    names = "; ".join(f"`{s}`: {', '.join(ids)}" for s, ids in sorted(suspect.items()))
    return (f"**Suspect cases are included.** {len(flagged)} eval cases are marked `suspect` in their `evals/cases.json` ({names}): each points at"
            f" text to rewrite, translate or check (\"this handout\", \"here is my letter\") that the case never gives, so the model had nothing to"
            f" work on. They were run before this was noticed and are still inside the counts above: {hit} of the {total} judged replies behind"
            f" the tested cells. Each case's `suspect_note` says what is missing; a person needs to write the invented text, then the cases can be run again.")


def problems(data, skills_with_boxes):
    out = []
    ids = [c["id"] for c in data["columns"]]
    if len(set(ids)) != len(ids):
        out.append("duplicate column ids")
    rows = set(data["cells"])
    for s in sorted(set(skills_with_boxes) - rows):
        out.append(f"{s}: ships a paste-ready box but has no row in the grid")
    for s in sorted(rows - set(skills_with_boxes)):
        out.append(f"{s}: a row for a skill with no paste-ready box")
    for s, row in data["cells"].items():
        for cid in ids:
            if cid not in row:
                out.append(f"{s}: no cell for {cid}")
        for cid in set(row) - set(ids):
            out.append(f"{s}: a cell for an unknown column {cid}")
        for cid, cell in row.items():
            where = f"{s} / {cid}"
            st = cell.get("status")
            if st not in STATUSES:
                out.append(f"{where}: status {st!r} is not one of {STATUSES}")
            elif st == "pending":
                extra = set(cell) - {"status", "note"}
                if extra:
                    out.append(f"{where}: a pending cell carries {sorted(extra)}")
            elif st == "small":
                if not isinstance(cell.get("cases"), int) or cell["cases"] < 1 or set(cell) - {"status", "cases", "note"}:
                    out.append(f"{where}: a small cell needs 'cases' and no pass counts")
            elif st == "tested":
                keys = ("cases", "pass", "partial", "fail")
                if not all(isinstance(cell.get(k), int) and cell[k] >= 0 for k in keys):
                    out.append(f"{where}: a tested cell needs whole numbers for {keys}")
                elif cell["pass"] + cell["partial"] + cell["fail"] != cell["cases"]:
                    out.append(f"{where}: pass + partial + fail is not cases")
                if not cell.get("date"):
                    out.append(f"{where}: a tested cell needs a date")
    for e in data.get("effect", []):
        for cid, v in e["models"].items():
            if cid not in ids:
                out.append(f"effect / {e['condition']}: unknown column {cid}")
            elif v["pass"] + v["partial"] + v["fail"] != v["cases"]:
                out.append(f"effect / {e['condition']} / {cid}: pass + partial + fail is not cases")
    return out


def cell_text(cell):
    st = cell["status"]
    if st == "pending":
        return "Pending"
    if st == "small":
        return f"Small run, {cell['cases']} cases"
    return f"{cell['pass']} of {cell['cases']} pass; {cell['partial']} partial, {cell['fail']} fail"


def render(data, runs=None, suspect=None):
    runs = runs or {}
    cols = data["columns"]
    lines = [MARK, "", "# Where each skill has been tried", "", data["intro"], ""]
    for kind, title in (("hosted", "Hosted models"), ("local", "Local models"), ("product", "Products people use at work")):
        sel = [c for c in cols if c["kind"] == kind]
        if not sel:
            continue
        lines += [f"## {title}", "", "| Skill | " + " | ".join(c["label"] for c in sel) + " |", "| --- |" + " --- |" * len(sel)]
        for s, row in data["cells"].items():
            lines.append(f"| `{s}` | " + " | ".join(cell_text(row[c["id"]]) for c in sel) + " |")
        lines.append("")
    if data.get("effect"):
        eids = [c["id"] for c in cols if any(c["id"] in e["models"] for e in data["effect"])]
        labels = {c["id"]: c["label"] for c in cols}
        lines += ["## Does the box change the replies?", "",
                  "The same 12 messages to `cf-ai-safe-use`'s instructions: none, the SHORT box, the STANDARD box. Pass, partial, fail.", "",
                  "| Instructions | " + " | ".join(labels[i] for i in eids) + " |", "| --- |" + " --- |" * len(eids)]
        for e in data["effect"]:
            lines.append(f"| {e['condition']} | " + " | ".join(f"{e['models'][i]['pass']} / {e['models'][i]['partial']} / {e['models'][i]['fail']}" for i in eids) + " |")
        lines.append("")
    notes = list(data["notes"]) + [x for x in (drift_note(runs), suspect_note(data, runs, suspect)) if x]
    lines += ["## How to read this", ""] + [f"- {x}" for x in notes] + [""]
    lines += ["## What was run", ""] + [f"- **{c['label']}**: {c['how']}" for c in cols] + [""]
    lines += ["## Add a result", "", data["add"], ""]
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("root", nargs="?", default=str(Path(__file__).resolve().parents[1]))
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    root = Path(a.root)
    data = json.loads((root / "docs" / "tested-with.json").read_text(encoding="utf-8"))
    boxes = [p.parent.parent.name for p in sorted((root / ".claude" / "skills").glob("*/references/paste-ready.md"))]
    runs = load_runs(root)
    bad = problems(data, boxes) + run_problems(runs)
    if not bad:
        bad = recount_problems(data, runs)
    if bad:
        print("\n".join(bad), file=sys.stderr)
        return 1
    page = render(data, runs, load_suspect(root))
    target = root / "docs" / "tested-with.md"
    if a.check:
        if not target.exists() or target.read_text(encoding="utf-8").replace("\r\n", "\n") != page:
            print("docs/tested-with.md is out of date: run python scripts/make_tested_grid.py", file=sys.stderr)
            return 1
        print("docs/tested-with.md is up to date")
        return 0
    target.write_text(page, encoding="utf-8", newline="\n")
    print("wrote docs/tested-with.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
