#!/usr/bin/env python3
"""Turn a filled AI-tool review worksheet (JSON) into a one-page Markdown review.

Usage:
    python render_review.py WORKSHEET.json [-o REVIEW.md]

The worksheet is a JSON object:
    {
      "tool": "what is being reviewed (a name or a description)",
      "purpose": "what the group is considering using it for",
      "reviewed_by": "roles, not names (for example: nurse, dietitian, parent representative)",
      "date": "2026-10-08",
      "rows": [
        {"stage": "design", "question": "...", "found": "...", "where": "document | demo | test | ...",
         "unknown": false, "owner": "role who follows up"}
      ],
      "red_flags": [{"flag": "asks-for-identifiers", "seen": "yes | no | unknown", "note": "..."}],
      "decision": {"choice": "not-recommended | use-only-for | needs-more-information",
                   "use_for": "...", "checks": ["..."], "decided_by": "roles of the people who decided"}
    }

stage is one of: design, development, deployment, monitoring, evaluation.
Red flag ids: asks-for-identifiers, claims-to-diagnose-dose-or-decide, no-sources-shown,
no-export-or-delete, no-plain-statement-on-chats, marketing-without-evidence. A flag left out is shown
as "not reviewed".

It refuses (exit 1) and prints every reason when:
    a row has neither a finding nor "unknown": true      (an unknown stays unknown; a blank is not allowed)
    a finding hedges ("probably fine", "should be fine", "seems fine", "likely fine", "assume")
    a finding (not marked unknown) has no "where" (document, demo, test...)
    a stage, red-flag id or "seen" value is not one of the allowed words, or "unknown" is not true/false
    a decision is given without "decided_by", or "use-only-for" is chosen without "use_for" and checks
The script never chooses the decision. With no decision it prints "No decision yet".

Exit codes:
    0  the review was written
    1  refused: the worksheet breaks a rule above
    2  usage error: the file cannot be read, is not JSON, or is not a JSON object

Python 3.9+, standard library only, no network.
"""

from __future__ import annotations

import argparse
import json
import re
import sys

STAGES = ["design", "development", "deployment", "monitoring", "evaluation"]
RED_FLAGS = {
    "asks-for-identifiers": "Asks for names, dates of birth, record numbers or other identifiers it does not need",
    "claims-to-diagnose-dose-or-decide": "Claims to diagnose, give doses or decide eligibility",
    "no-sources-shown": "No way to see the sources behind an answer",
    "no-export-or-delete": "No way to export or delete your data",
    "no-plain-statement-on-chats": "No plain statement of what happens to chats (stored, reused, shared, for how long)",
    "marketing-without-evidence": "Marketing claims with no evidence behind them",
}
SEEN = {"yes", "no", "unknown"}
CHOICES = {
    "not-recommended": "Not recommended.",
    "use-only-for": "Use only for {use_for}, with these checks:",
    "needs-more-information": "Needs more information before a decision.",
}
HEDGE_RE = re.compile(r"\b(?:probably|presumably|should be fine|seems fine|seems ok|likely fine|likely ok|assume|assumed)\b", re.I)


def _s(v) -> str:
    return v.strip() if isinstance(v, str) else ""


def problems(ws: dict) -> list:
    out = []
    rows = ws.get("rows")
    if not isinstance(rows, list) or not rows:
        out.append("'rows' must be a non-empty list")
        rows = []
    for i, row in enumerate(rows, start=1):
        label = f"row {i}"
        if not isinstance(row, dict):
            out.append(f"{label}: must be an object")
            continue
        if row.get("stage") not in STAGES:
            out.append(f"{label}: stage must be one of {', '.join(STAGES)}")
        if not _s(row.get("question")):
            out.append(f"{label}: has no question")
        unknown = row.get("unknown", False)
        if not isinstance(unknown, bool):
            out.append(f"{label}: 'unknown' must be true or false")
            unknown = False
        found = _s(row.get("found"))
        if not found and not unknown:
            out.append(f"{label}: has neither a finding nor \"unknown\": true; an unknown stays unknown, never blank")
        if found and HEDGE_RE.search(found):
            out.append(f"{label}: the finding hedges ('{HEDGE_RE.search(found).group(0)}'); write what was seen, or mark it unknown")
        if found and not unknown and not _s(row.get("where")):
            out.append(f"{label}: a finding needs 'where' (document, demo, test...)")
    flags = ws.get("red_flags", [])
    if not isinstance(flags, list):
        out.append("'red_flags' must be a list")
        flags = []
    for j, fl in enumerate(flags, start=1):
        if not isinstance(fl, dict) or fl.get("flag") not in RED_FLAGS:
            out.append(f"red flag {j}: 'flag' must be one of {', '.join(RED_FLAGS)}")
        elif fl.get("seen") not in SEEN:
            out.append(f"red flag {j}: 'seen' must be yes, no or unknown")
    dec = ws.get("decision") or {}
    if not isinstance(dec, dict):
        out.append("'decision' must be an object")
        dec = {}
    choice = _s(dec.get("choice"))
    if choice:
        if choice not in CHOICES:
            out.append(f"decision: choice must be one of {', '.join(CHOICES)}")
        if not _s(dec.get("decided_by")):
            out.append("decision: 'decided_by' is needed; the people who decide are named by role, and the assistant never decides")
        if choice == "use-only-for":
            checks = dec.get("checks")
            if not _s(dec.get("use_for")):
                out.append("decision: 'use-only-for' needs 'use_for'")
            if not isinstance(checks, list) or not [c for c in checks if _s(c)]:
                out.append("decision: 'use-only-for' needs at least one check in 'checks'")
    return out


def _cell(text: str) -> str:
    return (text or "").replace("|", "\\|").replace("\n", " ").strip()


def render(ws: dict) -> str:
    rows = ws["rows"]
    dec = ws.get("decision") or {}
    choice = _s(dec.get("choice"))
    lines = [f"# AI tool review: {_s(ws.get('tool')) or 'unnamed tool'}", ""]
    lines.append(f"- Considered for: {_s(ws.get('purpose')) or 'not stated'}")
    lines.append(f"- Reviewed by (roles): {_s(ws.get('reviewed_by')) or 'not stated'}")
    lines.append(f"- Date: {_s(ws.get('date')) or 'not stated'}")
    lines += ["", "## Decision", ""]
    if choice:
        lines.append("**" + CHOICES[choice].format(use_for=_s(dec.get("use_for"))) + "**")
        if choice == "use-only-for":
            lines += [""] + [f"- {_s(c)}" for c in dec.get("checks", []) if _s(c)]
        lines += ["", f"Decided by: {_s(dec.get('decided_by'))}. The assistant did not choose this."]
    else:
        lines.append("**No decision yet.** The review group decides: not recommended, use only for a named purpose "
                     "with named checks, or needs more information.")

    unknowns = [r for r in rows if r.get("unknown")]
    lines += ["", "## Still unknown", ""]
    if unknowns:
        lines += [f"- ({r['stage']}) {_s(r.get('question'))} Owner: {_s(r.get('owner')) or 'none named'}" for r in unknowns]
    else:
        lines.append("Nothing was marked unknown.")

    seen = {fl["flag"]: fl for fl in ws.get("red_flags", [])}
    lines += ["", "## Red flags", "", "| Red flag | Seen | Note |", "| --- | --- | --- |"]
    for fid, text in RED_FLAGS.items():
        fl = seen.get(fid)
        lines.append(f"| {text} | {fl['seen'] if fl else 'not reviewed'} | {_cell(_s(fl.get('note')) if fl else '')} |")

    lines += ["", "## What we found, by stage", ""]
    for stage in STAGES:
        stage_rows = [r for r in rows if r.get("stage") == stage]
        if not stage_rows:
            lines += [f"### {stage.capitalize()}", "", "Not reviewed.", ""]
            continue
        lines += [f"### {stage.capitalize()}", "", "| Question | What we found | Where we saw it | Unknown | Owner |",
                  "| --- | --- | --- | --- | --- |"]
        for r in stage_rows:
            lines.append(f"| {_cell(_s(r.get('question')))} | {_cell(_s(r.get('found')))} | {_cell(_s(r.get('where')))} | "
                         f"{'yes' if r.get('unknown') else 'no'} | {_cell(_s(r.get('owner')))} |")
        lines.append("")

    lines += ["## Limits of this review", "",
              "This page records what the group saw, where, and on what date. An unknown is not a pass. "
              "A tool can change after a review, so review it again after a change and on a set date. "
              "This is not medical advice, and no tool replaces the CF care team.", ""]
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Render a filled AI-tool review worksheet (JSON) as a one-page Markdown review. "
                    "Refuses when a row has neither a finding nor 'unknown', and never chooses the decision.",
        epilog="Exit codes: 0 written, 1 refused (the reasons are printed), 2 usage error.")
    parser.add_argument("worksheet", help="the filled worksheet, a UTF-8 JSON object")
    parser.add_argument("-o", "--output", help="write the review here (default: standard output)")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")

    try:
        with open(args.worksheet, encoding="utf-8-sig") as fh:
            ws = json.load(fh)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if not isinstance(ws, dict):
        print("error: the worksheet must be a JSON object", file=sys.stderr)
        return 2

    found = problems(ws)
    if found:
        for p in found:
            print(f"REFUSED {p}", file=sys.stderr)
        print(f"{len(found)} problem(s); no review written.", file=sys.stderr)
        return 1

    page = render(ws)
    if args.output:
        try:
            with open(args.output, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(page)
        except OSError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
    else:
        sys.stdout.write(page)
    return 0


if __name__ == "__main__":
    sys.exit(main())
