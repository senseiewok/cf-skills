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
Red flag ids: asks-for-identifiers, claims-to-diagnose-dose-or-decide, reassures-instead-of-urgent-help,
no-sources-shown, no-export-or-delete, no-plain-statement-on-chats, marketing-without-evidence. A flag left out is shown
as "not reviewed".

It refuses (exit 1) and prints every reason when:
    a row has neither a finding nor "unknown": true      (an unknown stays unknown; a blank is not allowed)
    a row has no question, or is not an object
    a finding hedges ("probably", "presumably", "should be fine", "should be safe", "seems fine",
        "seems okay", "looks fine", "likely fine", "assume", "I think", "I believe", "I guess", "maybe",
        "perhaps", "hopefully")
    a finding (not marked unknown) has no "where" (document, demo, test...), or "where" is a
        placeholder such as "n/a", "none", "-" or "tbd"
    a row marked unknown has no "owner" (an unknown needs someone to follow it up)
    a stage, red-flag id or "seen" value is not one of the allowed words, or "unknown" is not true/false
    the same red-flag id is given twice
    a decision choice is not a string, a decision is given without "decided_by", "decided_by" names an
        AI (the assistant, a chatbot, a model), or "use-only-for" is chosen without "use_for" and checks
The script never chooses the decision. With no decision it prints "No decision yet".
Every text from the worksheet is written as plain text: line breaks become spaces and Markdown
characters (# * _ | < > [ ] ` and backslash) are escaped, so a name cannot add a heading or a decision.

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
    "reassures-instead-of-urgent-help": ("Reassures instead of telling someone to get urgent help for an urgent symptom, "
                                         "or suggests stopping a treatment"),
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
HEDGE_RE = re.compile(r"\b(?:probably|presumably|should be fine|seems fine|seems ok|likely fine|likely ok|assume|assumed"
                      r"|should be (?:safe|ok|okay|fine)|seems (?:okay|safe|alright|good)|looks (?:fine|ok|okay|safe|good)"
                      r"|likely (?:safe|okay)|i think|i believe|i guess|i suppose|i assume|maybe|perhaps|hopefully"
                      r"|assuming|we think|we believe|not sure)\b", re.I)
PLACEHOLDER_RE = re.compile(r"^\W*(?:n\W?a|none|nil|tbd|tbc|unknown|not applicable|nothing|-+|\?+)\W*$", re.I)
AI_DECIDER_RE = re.compile(r"\b(?:ai|a\.i\.|assistant|chatbot|chat bot|bot|model|llm|gpt|chatgpt|claude|copilot|gemini|"
                           r"the tool|the script|automated|automatically)\b", re.I)
_MD_SPECIAL = re.compile(r"([\\`*_#|<>\[\]])")


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
        where = _s(row.get("where"))
        if found and not unknown and not where:
            out.append(f"{label}: a finding needs 'where' (document, demo, test...)")
        elif found and where and PLACEHOLDER_RE.match(where):
            out.append(f"{label}: 'where' is a placeholder ('{where}'); name the document, demo or test, or mark the row unknown")
        if unknown and not _s(row.get("owner")):
            out.append(f"{label}: an unknown needs an 'owner' (the role who follows it up)")
    flags = ws.get("red_flags", [])
    if not isinstance(flags, list):
        out.append("'red_flags' must be a list")
        flags = []
    seen_ids = set()
    for j, fl in enumerate(flags, start=1):
        if not isinstance(fl, dict) or fl.get("flag") not in RED_FLAGS:
            out.append(f"red flag {j}: 'flag' must be one of {', '.join(RED_FLAGS)}")
            continue
        if fl.get("seen") not in SEEN:
            out.append(f"red flag {j}: 'seen' must be yes, no or unknown")
        if fl["flag"] in seen_ids:
            out.append(f"red flag {j}: '{fl['flag']}' is given more than once; keep one entry per flag")
        seen_ids.add(fl["flag"])
    dec = ws.get("decision") or {}
    if not isinstance(dec, dict):
        out.append("'decision' must be an object")
        dec = {}
    if "choice" in dec and dec["choice"] not in (None, "") and not isinstance(dec["choice"], str):
        out.append("decision: choice must be a string, one of " + ", ".join(CHOICES))
    choice = _s(dec.get("choice"))
    if choice:
        if choice not in CHOICES:
            out.append(f"decision: choice must be one of {', '.join(CHOICES)}")
        decided_by = _s(dec.get("decided_by"))
        if not decided_by:
            out.append("decision: 'decided_by' is needed; the people who decide are named by role, and the assistant never decides")
        elif AI_DECIDER_RE.search(decided_by):
            out.append(f"decision: 'decided_by' names an AI ('{AI_DECIDER_RE.search(decided_by).group(0)}'); "
                       "people decide, by role, and the assistant never decides")
        if choice == "use-only-for":
            checks = dec.get("checks")
            if not _s(dec.get("use_for")):
                out.append("decision: 'use-only-for' needs 'use_for'")
            if not isinstance(checks, list) or not [c for c in checks if _s(c)]:
                out.append("decision: 'use-only-for' needs at least one check in 'checks'")
    return out


def _cell(text: str) -> str:
    """Worksheet text as plain inline Markdown: one line, with Markdown characters escaped."""
    text = (text or "").replace("\r", " ").replace("\n", " ")
    return _MD_SPECIAL.sub(r"\\\1", text).strip()


def render(ws: dict) -> str:
    rows = ws["rows"]
    dec = ws.get("decision") or {}
    choice = _s(dec.get("choice"))
    lines = [f"# AI tool review: {_cell(_s(ws.get('tool'))) or 'unnamed tool'}", ""]
    lines.append(f"- Considered for: {_cell(_s(ws.get('purpose'))) or 'not stated'}")
    lines.append(f"- Reviewed by (roles): {_cell(_s(ws.get('reviewed_by'))) or 'not stated'}")
    lines.append(f"- Date: {_cell(_s(ws.get('date'))) or 'not stated'}")
    lines += ["", "## Decision", ""]
    if choice:
        lines.append("**" + CHOICES[choice].format(use_for=_cell(_s(dec.get("use_for")))) + "**")
        if choice == "use-only-for":
            lines += [""] + [f"- {_cell(_s(c))}" for c in dec.get("checks", []) if _s(c)]
        lines += ["", f"Decided by: {_cell(_s(dec.get('decided_by')))}. The assistant did not choose this."]
    else:
        lines.append("**No decision yet.** The review group decides: not recommended, use only for a named purpose "
                     "with named checks, or needs more information.")

    unknowns = [r for r in rows if r.get("unknown")]
    lines += ["", "## Still unknown", ""]
    if unknowns:
        lines += [f"- ({r['stage']}) {_cell(_s(r.get('question')))} Owner: {_cell(_s(r.get('owner'))) or 'none named'}"
                  for r in unknowns]
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
