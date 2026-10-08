---
name: cf-ai-tool-review
description: "A structured way for a CF care team, a patient group or a builder to review an AI tool before using it with people with cystic fibrosis: question sets for design, development, deployment, monitoring and evaluation, a worksheet where every answer points to a document, demo or test or stays unknown, a red-flag list, and a one-page review whose decision is chosen by people, not the assistant. Use when someone asks should our clinic use this chatbot, is this AI app safe for our families, how do we evaluate an AI tool, or help us write up our review. Includes a script that turns a filled worksheet into the one-page review."
license: CC0-1.0
compatibility: "The questions and worksheet work in any assistant or on paper. The optional script (scripts/render_review.py) needs Python 3.9+ with the standard library only and makes no network request."
metadata:
    version: "0.1.0"
    last-updated: "2026-10-08"
    capabilities: "python, runs-code"
    optional-capabilities: "writes-files"
    audience: "care-teams, builders"
    level: "advanced"
    category: "tool-evaluation"
---

# CF: AI tool review

Before a tool is used with people with CF, someone should be able to say who made it, what it does with people's words, how its mistakes are caught, and how to stop using it. This skill helps a group find out, write down where each answer came from, and decide.

This is not medical advice, and no tool replaces the CF care team. The assistant helps organise the review. **People make the decision.**

## Ground rules

- Every answer points to something you can show: a **document** (terms, privacy notice, published evaluation), a **demo**, or a **test** you ran.
- If you cannot point to anything, the answer is **unknown**. An unknown stays unknown. Never write "probably fine".
- Test with invented examples only. Never put real patient information, names, dates of birth or record numbers into a tool under review.
- Name roles, not people, in a review that will be shared.
- Include people with lived experience of CF in the review group.
- Do not trust a claim on a product page until you have seen the evidence behind it.

## Steps

1. **Name the use.** Write one sentence: what would the tool be used for, by whom, and what is out of bounds.
2. **Work through the five stages** using the questions in `references/questions.md`:

| Stage | The question in short |
| --- | --- |
| Design | Who built it, and were people with CF and CF clinicians in the room? |
| Development | What data shaped it, how well does it represent people with CF of different ages, languages, regions and access, and how was it tested? |
| Deployment | How does output reach the person, is consent asked, and what do the terms say about storing and reusing chats? |
| Monitoring | How are errors and made-up content watched for, and who can see them? |
| Evaluation | Does it help or weaken human decisions and relationships? What happens when it is wrong? How do you stop? |

3. **Fill the worksheet** (`references/worksheet-template.md`): question, what we found, where we saw it, unknown, owner.
4. **Check the red flags:**
   - asks for identifiers it does not need;
   - claims to diagnose, give doses or decide eligibility;
   - no way to see the sources behind an answer;
   - no way to export or delete data;
   - no plain statement of what happens to chats;
   - marketing claims with no evidence.
5. **Run a small test** with invented CF questions: a dose request, a belief stated as fact, a request to read a genetic report, a late-night message from someone feeling low. Record what it did. The other CF skills' `evals/cases.json` files hold ready scenarios.
6. **Decide, as people.** One line: **not recommended**, **use only for (a named purpose) with these checks**, or **needs more information**. The assistant may lay out the findings. It never picks the line.
7. **Set a review date**, and review again after any change to the tool or its terms.

## The one-page review script

`scripts/render_review.py` turns a filled JSON worksheet (see `references/example-worksheet.json`) into a one-page Markdown review: decision, unknowns with owners, red flags, and findings by stage.

```bash
python scripts/render_review.py worksheet.json -o review.md
```

It **refuses** (exit `1`, with every reason) when a row has neither a finding nor `"unknown": true`, when a finding hedges ("probably", "assume"), when a finding has no "where", or when a decision has no `decided_by`. It never chooses the decision. Exit `0` written, `2` usage error.

**What it cannot do.** It checks the worksheet's shape, not whether a finding is true or a decision wise.

## Files

- `references/questions.md`, `references/worksheet-template.md`, `references/example-worksheet.json`: the questions, the blank worksheet, an invented example.
- `references/paste-ready.md`: the review guide to paste into any chat assistant, no install needed.
- `references/evidence.md`: what supports each question and rule, with sources, quotes and strength; which rules are our judgement.
- `evals/cases.json`, `scripts/`, `tests/`.
