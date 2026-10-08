# Review worksheet

Copy this table into a shared document. One row per question from `questions.md`. Fill **what we found** only with something you saw, and **where we saw it** with the document, demo or test. If you could not find out, write **unknown** and name an owner to follow up.

Rules:

- An unknown stays unknown. Never write "probably fine".
- Name roles, not people, if the review will be shared.
- Do not put any patient information in the worksheet, and do not test the tool with real patient information.

| Stage | Question | What we found | Where we saw it (document, demo, test) | Unknown | Owner |
| --- | --- | --- | --- | --- | --- |
| Design | Who built it, and were people with CF and CF clinicians involved? | | | | |
| Development | What data trained it, and how well does it represent people with CF? | | | | |
| Development | Does it show sources, and what does it do when it does not know? | | | | |
| Deployment | How does output reach the person, and is consent asked? | | | | |
| Deployment | What do the terms say about storing and reusing chats? | | | | |
| Deployment | Can people export and delete their data? | | | | |
| Monitoring | How are errors and made-up content watched for, and who sees them? | | | | |
| Evaluation | Does it help or weaken human decisions and relationships? | | | | |
| Evaluation | What happens when it is wrong, and how do we stop using it? | | | | |

## Red flags

| Red flag | Seen (yes, no, unknown) | Note |
| --- | --- | --- |
| Asks for identifiers it does not need | | |
| Claims to diagnose, give doses or decide eligibility | | |
| Reassures instead of telling someone to get urgent help for an urgent symptom, or suggests stopping a treatment | | |
| No way to see sources | | |
| No way to export or delete data | | |
| No plain statement of what happens to chats | | |
| Marketing claims with no evidence | | |

## Decision (the review group chooses; an assistant never does)

One of:

- **Not recommended.**
- **Use only for** (a named purpose), **with these checks:** (named checks, and who does them).
- **Needs more information** before a decision.

Decided by (roles): ______  Date: ______  Review again on: ______

To turn a filled JSON version of this worksheet into a one-page review, see `example-worksheet.json` and `scripts/render_review.py`.
