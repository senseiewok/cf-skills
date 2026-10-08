---
name: cf-plain-language-rewrite
description: "Rewrite a CF handout, letter, leaflet or message in plain language at a chosen reading level (sixth grade by default) without adding, dropping or changing any fact. Use when a care team or family says make this easier to read, simplify this handout, rewrite this for a parent or a teenager, or check the reading level. Keeps every number, unit, name and rule; returns a draft plus a verify-before-use list of every fact to check against the original. Includes scripts that measure the reading level and compare numbers, dates and names between the original and the rewrite."
license: CC0-1.0
compatibility: "The steps work in any assistant. The optional scripts (scripts/readability.py and scripts/fact_diff.py) need Python 3.9+ with the standard library only and make no network request."
metadata:
    version: "0.1.0"
    last-updated: "2026-10-08"
    capabilities: "python, runs-code"
    optional-capabilities: ""
    audience: "care-teams, patients-families"
    level: "base"
    category: "communication"
---

# CF: plain-language rewrite

A handout only helps if the person can read it. This skill rewrites CF material in plain words **without changing what it says**. The rewrite is a draft. A person checks it against the original before anyone uses it.

This is not medical advice. A rewrite of a handout is not a new instruction for anyone's care.

## Before you start

- Ask for the original text, the reader (for example a parent, a teenager, a new family) and the reading level. The default is sixth grade.
- Ask the person not to paste anything with names, dates of birth, record numbers or other details about one person. If they do, stop and ask them to remove the details first. Do not repeat them.
- If the original contains advice for one person (a dose, a plan), say that the rewrite must be checked by the care team who wrote it.

## Rules for the rewrite

| Keep exactly | Change freely |
| --- | --- |
| Every number and unit ("2 times a day", "30 minutes") | Long sentences into short ones |
| Every name: medicines, clinics, days, teams | Hard words into everyday words |
| Every rule, warning and "do not" | The order, so the most important step comes first |
| Every contact route and resource, as written | Headings and lists, so it is easy to scan |

- Add no new facts, tips, numbers, links or phone numbers. If something seems missing, list it as a question for the author. Do not fill it in.
- Drop nothing. If a part cannot be simplified without losing meaning, keep it and say so.
- Define a medical word once, in plain words, using only what the original says.
- Use person-first words ("a person with CF") and a warm, respectful tone. No pity, no promises.
- Number words: writing "twice" for "2 times" is fine. Changing the number is not.

## What to return

1. **The rewrite**, headed "DRAFT: check against the original before use".
2. **Verify before use**: a list of every number, unit, date, name, rule, warning and resource in the rewrite, each next to the line of the original it came from. A person ticks each one.
3. **Questions for the author**: anything unclear, missing or possibly out of date. Do not guess.
4. **Reading level**: the measured grade if you can run the script below. If you cannot, say "reading level not measured". Do not claim a grade.

## Check with the scripts (optional)

`scripts/readability.py` measures the Flesch-Kincaid grade level and the average sentence length, using a documented syllable rule. The same text always gives the same number. It is an estimate within about one grade, and it measures word and sentence length only, not clarity or correctness.

`scripts/fact_diff.py` lists numbers (with their units), dates and capitalised names that were added, dropped or changed between the original and the rewrite.

```bash
python scripts/readability.py rewrite.txt --max-grade 6
python scripts/fact_diff.py original.txt rewrite.txt
```

Exit codes: `readability.py` gives `0` when measured and within `--max-grade`, `1` when above it, `2` on a usage error. `fact_diff.py` gives `0` when nothing differs, `1` on any difference, `2` on a usage error. Both take `--json`.

**What the scripts cannot see.** `fact_diff.py` compares the surface only. It misses a change in words ("before meals" became "after meals"), a number moved to the wrong step, and a new instruction with no number or name. A clean result is not a check of meaning. A person still reads the rewrite against the original, line by line.

## Files

- `references/paste-ready.md`: the same steps to paste into any chat assistant, no install needed.
- `references/claims-to-source.md`: statements that need a primary source before anyone publishes them.
- `evals/cases.json`: scenarios to test your own assistant.
- `scripts/` and `tests/`: the two checkers and their tests.
