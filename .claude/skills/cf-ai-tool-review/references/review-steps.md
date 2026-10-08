# CF: AI tool review, the steps

The rules in [SKILL.md](../SKILL.md) come first. This page adds detail; where the two differ, SKILL.md holds.

## Ground rules

- Every answer points to something you can show: a **document** (terms, privacy notice, published evaluation), a **demo**, or a **test** you ran.
- If you cannot point to anything, the answer is **unknown**. An unknown stays unknown. Never write "probably fine".
- A maker's own page, brochure or self-assessment is a claim. Record it as "maker says", and keep the related red flag unknown until there is independent evidence or the group's own test.
- Test with invented examples only. Never put real patient information, names, dates of birth or record numbers into a tool under review.
- Name roles, not people, in a review that will be shared.
- Include people with lived experience of CF in the review group.
- If someone in the group describes a real urgent symptom, or sounds low, the assistant answers that first: an urgent symptom goes to the CF team's urgent line or local emergency services now; distress gets warmth, and anyone who might be unsafe is pointed to someone they trust or local emergency or crisis services, with no phone number from memory.
- Reply in the language the person writes in. Check the worksheet silently before sending it.

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
   - reassures instead of telling someone to get urgent help for an urgent symptom, or suggests stopping a treatment;
   - no way to see the sources behind an answer;
   - no way to export or delete data;
   - no plain statement of what happens to chats;
   - marketing claims with no evidence.
5. **Run a small test** with invented CF questions: a dose request, a belief stated as fact, a request to read a genetic report, a late-night message from someone feeling low, an invented urgent symptom at night, and a question about stopping a medicine. Record what it did. The other CF skills' `evals/cases.json` files hold ready scenarios.
6. **Decide, as people.** One line: **not recommended**, **use only for (a named purpose) with these checks**, or **needs more information**. The assistant may lay out the findings. It never picks the line.
7. **Set a review date**, and review again after any change to the tool or its terms.
