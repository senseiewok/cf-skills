# Structured data that tells the truth

Structured data (JSON-LD in a `<script type="application/ld+json">` block) lets a page describe itself in a vocabulary engines read. It is optional. A small site loses little by leaving it out and loses trust by getting it wrong. The one rule: **every statement in the block must be supported by text a reader can see on that page.**

## 1. What honest structured data looks like

```html
<script type="application/ld+json">
{"@context": "https://schema.org",
 "@type": "Article",
 "headline": "Reading a registry report before quoting a number",
 "datePublished": "2026-10-01",
 "author": {"@type": "Person", "name": "Example Lab maintainer"}}
</script>
```

This is honest when the page's `<h1>` is that headline, the page shows "Published 2026-10-01" and names the author. Each field has a sentence on the page that backs it.

```html
<!-- Not honest for a small independent research site -->
<script type="application/ld+json">
{"@context": "https://schema.org",
 "@type": "MedicalWebPage",
 "about": {"@type": "MedicalCondition", "name": "Cystic fibrosis"},
 "reviewedBy": {"@type": "Physician", "name": "Not stated"},
 "lastReviewed": "2026-10-05"}
</script>
```

`MedicalWebPage` and `MedicalCondition` tell engines this is clinical content from an authority. `reviewedBy` claims a clinical review that did not happen. `lastReviewed` moves a date without a review. Each line is a claim the page cannot back.

## 2. Types a small content site can honestly use

The checker's allowlist (SEO042): `WebSite`, `WebPage`, `AboutPage`, `CollectionPage`, `ContactPage`, `Article`, `BlogPosting`, `NewsArticle`, `ScholarlyArticle`, `TechArticle`, `CreativeWork`, `Dataset`, `SoftwareSourceCode`, `SoftwareApplication`, `Organization`, `Person`, `BreadcrumbList`, `ListItem`, `ImageObject`, `FAQPage`, `Question`, `Answer`.

Medical types (SEO043): anything beginning with `Medical`, and `Drug`, `Physician`, `Hospital`, `Patient`, `DietarySupplement`. Use them only when the site is a clinical authority and a named, qualified person reviewed the page. "We write about a condition" does not make a page a `MedicalWebPage`; `Article` with a visible "research, not medical advice" line is the honest choice.

Even allowed types can lie. `ScholarlyArticle` for a blog post, `Dataset` for a table copied from someone else's report, `Organization` with a `founder` the About page never names: the type is fine and the content is not. Read the block against the page.

## 3. Fields that need visible support

| Field | Needs on the page |
| --- | --- |
| `headline`, `name` | the same words, visible (the checker's SEO044 checks this as a substring) |
| `datePublished`, `dateModified` | a visible date that changes only when the content does |
| `author`, `publisher` | a visible byline or an About page that names who is responsible |
| `description` | a sentence the page actually contains, not the meta description rephrased upward |
| `image` | the file exists, is the page's image, and has alt text in the page |
| `reviewedBy`, `lastReviewed`, `medicalAudience` | do not use unless literally true and shown |

## 4. Content-Security-Policy and inline JSON-LD: how to check

A strict policy such as `script-src 'self'` forbids inline **executable** scripts. A `<script type="application/ld+json">` block is a data block: the browser does not execute it, so the policy does not block it, and crawlers read it from the HTML source anyway. Three things can still go wrong, and each has its own check:

1. **Your policy does forbid inline scripts.** Confirm what it says: read the `Content-Security-Policy` response header (the browser's network panel, or one request with your own fetch tool to your own host). Then load the page with the console open: an executable inline script under that policy produces a "Refused to execute inline script" message; a JSON-LD block produces none. If you see a refusal, it is not the data block.
2. **Your own tests forbid inline `<script>` of any kind.** Many careful sites have a test that says "no inline script, period" (the real review that produced this skill had one). Search the test suite for the rule before adding the block. Either exempt `type="application/ld+json"` in that test, with a comment saying why it is safe, or leave structured data out. Do not weaken the policy to make a data block pass; the policy was not what blocked it.
3. **A validator or crawler cannot read it.** Validate with the engine's own structured-data tester against the **live** page, not the local file: the host may transform the HTML. The checker's SEO040 only proves the JSON parses.

The checker's SEO051 flags inline executable scripts as info and leaves JSON-LD alone, which matches the browser's behaviour.

## 5. Decision in one line

If you cannot point at the sentence on the page that supports a field, delete the field. If that leaves nothing, leave the block out; titles, descriptions and Open Graph tags carry most of the value for a small site.
