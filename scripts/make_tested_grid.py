#!/usr/bin/env python3
"""Build docs/tested-with.md, the grid of the CF care skills against the AI models and products they were tried on, from docs/tested-with.json.

Usage:  python scripts/make_tested_grid.py [ROOT] [--check]

Without --check it writes the page. With --check it writes nothing and exits 1 if the page is out of date or the data is inconsistent.

A cell is one of:
  tested   cases, pass, partial, fail (they must add up), plus a date; shown as "pass/cases pass, partial, fail"
  small    a short earlier run on some cases, no pass counts; shown as "small run, N cases"
  pending  not tried yet; no numbers allowed
Every skill that ships a references/paste-ready.md must be a row, and every row must have every column, so a missing result cannot hide.
"""

import argparse
import json
import sys
from pathlib import Path

STATUSES = ("tested", "small", "pending")
MARK = "<!-- Generated file: do not edit by hand. Run python scripts/make_tested_grid.py. -->"


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


def render(data):
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
    lines += ["## How to read this", ""] + [f"- {x}" for x in data["notes"]] + [""]
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
    bad = problems(data, boxes)
    if bad:
        print("\n".join(bad), file=sys.stderr)
        return 1
    page = render(data)
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
