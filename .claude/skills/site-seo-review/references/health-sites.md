# Health and research sites: what the checker cannot enforce

Search engines' quality guidelines single out pages that can affect a reader's health, safety or money (their phrase is "Your Money or Your Life"). The expectation is accountability: who wrote this, when, from what, and what it is not. Readers expect the same. None of it is a trick for ranking; it is what a careful site does anyway, and the checker can only confirm the mechanical traces of it.

## 1. What every health or research page needs

| Need | On the page | How to confirm |
| --- | --- | --- |
| Someone is responsible | A byline, or a footer link to an About page that names who runs the site and in what capacity (an independent lab, a clinic, a person) | Read the About page; it must say what the site is and what it is not (for example, not affiliated with a named organisation) |
| Dated content | A visible publication date and, if changed, a visible update date that moves only with content changes | Compare the date with version history; a sitemap `lastmod` must agree |
| Status is visible | "Draft, in review" or "Reviewed by [role] on [date]" where it applies, on the page and next to every link to it from elsewhere on the site | Search the site's text for the word "draft" beside each link to a draft page |
| Sources are cited | Primary sources (papers with identifiers, registry reports with year, regulator pages) linked from the claims they support | Pick three numbers and follow their citations to the sentence they come from |
| The boundary is stated | A plain line such as "Research, not medical advice", on every page, not only the home page | Search every page's visible text for it |
| Nothing is promised | No "will", "soon", "cure", "guarantee" about treatment or access | Grep the visible text for promise words and read each hit |
| Descriptions do not overclaim | The meta description claims only what the page shows | For each description, quote the page sentence that supports each claim; "evidence behind each claim" needs evidence behind each claim |
| Privacy matches the statement | If the site says it loads nothing from other hosts and sets no cookies, the served pages must show no third-party script, font or image | The checker's SEO050/SEO052 on the build, and a live fetch of each page after deployment (hosts inject scripts) |
| Structured data is modest | No medical types unless the site is a clinical authority; every field backed by visible text | [`structured-data.md`](structured-data.md) |

## 2. Wording that a reviewer flagged on a real site

These are generalised from one review; they are examples, not a rule book.

- "the evidence behind each claim" in a description, when the page showed one evidence record and a list of mistakes caught. Proposed instead: name what the page shows ("one real evidence record and the checks we run on our own writing").
- "3D model" when the page shows a draft drawing from published structures, labelled as a draft on the page. The description must carry the same label ("Draft, in review") or not use the phrase.
- A link named "Open the model" from a page that discusses several things. The link should name what it opens, and say "draft" if the target does.

## 3. What to leave out

- Any statement about an individual's eligibility, dosage, prognosis or treatment. A label's indication text is not any person's eligibility.
- Patient-level data of any kind, including in examples and screenshots.
- Personal stories of the people who run the site, unless they chose to publish them; a public site should neither state nor hint at a maintainer's own medical situation.
- Testimonials and "as seen in" lists that cannot be verified from the page.

## 4. Review coverage, named

A scientific review (are the claims true and sourced), an implementation review (does the HTML do what the metadata says) and a visual or accessibility review (does it read well on a phone, with a screen reader, without a mouse) cover different requirements. A pass on one does not clear another. When you report, say which of the three you did and on what: the exact final wording of each changed claim, the source and access date behind it, and the actual page structure you inspected, not an abridged version.
