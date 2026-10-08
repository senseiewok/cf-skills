---
name: cf-answer-check
description: "Check an AI answer about cystic fibrosis (CF) before relying on it or sharing it: split it into claims, label each with what it rests on, find the primary source and the exact passage for each factual claim, and mark what could not be checked as unverified. Use when someone asks is this answer right, can I trust what the chatbot said, check these facts, find the source for this, or before putting AI-written text into a handout, a post or a note. Includes a script that turns an answer into a claims worksheet. For anyone: patients, families, care teams, researchers and builders."
license: CC0-1.0
compatibility: "The steps work in any assistant. The optional script (scripts/claim_worksheet.py) needs Python 3.9+ with the standard library only and makes no network request. Finding sources needs a person or a tool that can read the source pages."
metadata:
    version: "0.1.0"
    last-updated: "2026-10-08"
    capabilities: "python, runs-code"
    optional-capabilities: "writes-files"
    audience: "patients-families, care-teams, researchers, builders"
    level: "advanced"
    category: "evidence"
---

# CF: answer check

An answer can read well and still be wrong. This skill checks an AI answer one claim at a time, against the source the claim should come from. What cannot be checked is marked unverified, not guessed.

This is not medical advice. Checking an answer does not make it advice for one person. Medical questions go to the CF care team.

Do not paste anything with names, dates of birth, record numbers or other details about one person.

## The tiers

| Tier | The claim rests on |
| --- | --- |
| T0 | Memory, a summary or a search snippet. Unverified |
| T1 | An exact quote from a primary source, with the source's date |
| T2 | T1, also checked by a script and by a different model or tool |
| T3 | T2, also read by a person |

A primary source is the original: a regulator page, a registry report, a paper, a trial record. A news story, a blog or another AI answer is a lead, not a source.

## Steps

1. **Split the answer into claims.** One checkable statement per line. The script below can draft this list.
2. **Mark each claim T0** to start. Nothing is checked yet.
3. **For each factual claim, find the primary source.** Ask the assistant which source it used, then find that source yourself. Do not trust a citation until you have opened it.
4. **Read the exact passage.** Copy the words that support the claim and write them next to it, with the source's name and date.
5. **Cross-check, in plain words:**

| Question | If the answer is no |
| --- | --- |
| Does the source exist? | Delete the claim. Do not repair it from memory |
| Does the passage really say it? | Narrow the claim to what the passage says, or mark it unverified |
| Does it say it about this group, place and year? | Narrow the claim to the group, place and year in the source |
| Does a different tool or source agree? | Keep it at T1 and say only one source was read |

6. **Watch the widening words.** "Only", "all", "never", "always", "same", "first", "no longer", "new" and "there is no" need a record of what was searched and where. Without one, narrow the sentence.
7. **List what could not be checked** and label it unverified. A search that found nothing is not proof that something does not exist.
8. **Bring medical questions to the care team**, with the claims and quotes you found.

## The worksheet script

`scripts/claim_worksheet.py` reads an answer and writes a JSON worksheet: one entry per sentence that has a number, percentage, year, drug name (a small built-in list, or your own with `--drugs`), widening word or absence phrase. Each entry is `{id, claim, source, quote, kind, scope}` with the last four empty for a person to fill. `kind` is `observed`, `computed` or `inferred`.

```bash
python scripts/claim_worksheet.py answer.txt -o worksheet.json --flags flags.json
```

Exit codes: `0` worksheet written, `1` no candidate claims found (this does not mean the answer has no claims; read it, or use `--all`), `2` usage error.

**What it cannot do.** It finds sentences worth checking. It checks nothing. It misses claims made without numbers, names or the listed words, and its drug list is for spotting names only: being on it says nothing about approval or use.

People who have the cf-research repository can run its claims checker (`tools/claims/check_claims.py`) on the filled worksheet. It fails when a quote is not exact, a number is not in the quote, or a widening word has no scope. It still cannot prove that a quote supports the sentence beside it; a person reads each pair.

## Files

- `references/paste-ready.md`: the same steps to paste into any chat assistant, no install needed.
- `references/claims-to-source.md`: statements that need a primary source before anyone publishes them.
- `evals/cases.json`: scenarios to test your own assistant.
- `scripts/` and `tests/`: the worksheet script and its tests.
