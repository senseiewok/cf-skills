# The checks, with IDs and the reason each exists

Severity: `error` fix before publishing; `warn` decide, then fix or document why not; `info` worth knowing. IDs are stable; new checks get new numbers, retired checks are never reused.

Terms: an **indexed page** is any `.html` file except the root `404.html` whose robots meta does not contain `noindex`. A page's **address** is its URL with `index.html` dropped (`about/index.html` is `/about/`); any other file keeps its name (`guides/setup.html`). Metadata checks (SEO001 to SEO016) run on indexed pages; content checks (SEO030 to SEO052) on every page, the 404 page included; the rest once per site. A check that depends on another's subject is skipped when that subject is missing, so one defect produces one finding.

## How the checker reads a site

These are the rules the tests hold it to, written out so a reader does not have to infer them from the code.

| Topic | Rule |
| --- | --- |
| Pages | Every `*.html` file under the folder, recursively; a folder named `x.html` is not a page. Paths are printed with forward slashes. |
| `noindex` | The robots meta `content` is split on commas; each part is stripped and lower-cased; the page is not indexed when one part is exactly `noindex`. |
| HTML | Parsed with the standard library's `html.parser`, never with regular expressions. A self-closed `<div/>` is treated as a start tag, as browsers do; of two equal attribute names the first wins; unclosed and deeply nested elements are fine. Files that are not valid UTF-8 are read with replacement characters and reported (SEO091). |
| Site file | For an href or URL: query and fragment dropped; `/x` is `SITE_DIR/x`; `x` is resolved against the page's own folder; an absolute URL is a site file only when it starts with `--base-url` (the rest is the path), or, without a base, by its URL path. A path that climbs out of the folder is not a site file and is never read. |
| Sitemap | Elements are matched by local name, so the usual namespace is fine; `<loc>` text is stripped. A well-formed sitemap with no `<loc>` leaves every indexed page unlisted (SEO022). `<lastmod>` is compared with today's local date. |
| robots.txt | Comments after `#` are dropped; consecutive `User-agent` lines form one group; `Disallow` lines in any group that includes `*` are matched against each indexed page's URL path (`*` is any run of characters, a trailing `$` anchors the end, otherwise a prefix match). `Allow` lines are ignored. One finding per pattern. |
| JSON-LD | Each block is parsed as written. The typed objects are each top-level object (or each element of a top-level list) plus the members of its `@graph`; SEO041 asks for `@context` on top-level objects only. |
| Counting | One finding per image, link, script, heading jump, sitemap entry or robots pattern; nothing is merged. Findings are sorted by page, ID and message. |

## Page metadata

| ID | Severity | Fires when | Why it matters |
| --- | --- | --- | --- |
| SEO001 | error | no `<title>` | The title is the search-result headline and the browser tab. Without it the engine invents one. |
| SEO002 | warn | title not 20 to 70 characters | Shorter says too little; longer is cut in results. Limits are approximate and tuned per site. |
| SEO003 | error | two indexed pages share a title | Duplicate titles make pages indistinguishable in results and in the browser's history. |
| SEO004 | error | no `<meta name="description">` | The description is the snippet readers see; without it, a random paragraph is shown. |
| SEO005 | warn | description not 60 to 160 characters | Same reason as SEO002; around 160 is where snippets are cut. |
| SEO006 | error | two indexed pages share a description | Same reason as SEO003. |
| SEO007 | error | no canonical link | Without a canonical, `/about`, `/about/` and `/about/index.html` compete as three pages. |
| SEO008 | error | canonical is not the page's own address | A canonical pointing elsewhere tells the engine this page is a copy. Trailing slashes count. |
| SEO009 | error | canonical is not absolute | Relative canonicals are resolved differently by different consumers. |
| SEO010 | error | `og:title` missing or differs from the title | Link previews and search should tell the same story. |
| SEO011 | error | `og:description` missing or differs from the description | Same. |
| SEO012 | error | `og:url` missing or differs from the canonical | A preview that points at a different address splits share counts and confuses readers. |
| SEO013 | info | no `og:image` | Previews without an image are plain; add one only when a reviewed image exists. |
| SEO014 | error | `og:image` names a file on the site that does not exist | A broken preview image is worse than none. |
| SEO015 | warn | `og:image` PNG is not 1200 by 630 | The size most previews crop least. |
| SEO016 | info | `og:image` could not be checked (other host, not a PNG, not absolute) | Says what was not verified. |
| SEO017 | error | `404.html` is not `noindex` | Otherwise every mistyped address becomes an indexed copy of the 404 page. |
| SEO018 | info | no `404.html` | Many static hosts serve this file for missing pages; without it, the host's default appears. |
| SEO019 | error | `404.html` has a canonical | A canonical on the 404 page claims a real address for a non-page. |

## Site level

| ID | Severity | Fires when | Why it matters |
| --- | --- | --- | --- |
| SEO020 | error | `sitemap.xml` missing or not well-formed XML | The sitemap is the list of pages you ask to have indexed. |
| SEO021 | error | a sitemap `<loc>` is not an indexed page | Listing a `noindex` page or a page that does not exist contradicts yourself. |
| SEO022 | error | an indexed page is not in the sitemap | The sitemap and the set of indexed pages must be the same set. |
| SEO023 | warn | `<lastmod>` is not a valid date or is in the future | `lastmod` is a promise about when content changed; crawlers that catch a false one stop trusting the file. The checker catches only impossible dates; honesty is a reading task. |
| SEO024 | error | no `robots.txt` | Without it, some crawlers log an error on every visit; with it, you can name the sitemap. |
| SEO025 | warn | `robots.txt` does not name the sitemap | `Sitemap: https://your-site.example/sitemap.xml` is how crawlers find it without being told. |
| SEO026 | error | a `Disallow` in the `*` group matches an indexed page | You asked for the page to be indexed and blocked the crawler from reading it. |

## Page content

| ID | Severity | Fires when | Why it matters |
| --- | --- | --- | --- |
| SEO030 | error | no `<h1>` | The main heading tells readers and engines what the page is; it should match the title's promise. |
| SEO031 | warn | more than one `<h1>` | Two main headings dilute both. |
| SEO032 | warn | a heading level is skipped (h2 to h4) | Screen-reader users navigate by heading level; a skip reads as a missing section. |
| SEO033 | error | `<img>` without `alt` | Images without alternative text are invisible to screen readers and to image search. `alt=""` is right for decoration. |
| SEO034 | warn | `<img>` without `width` and `height` | Without dimensions the browser cannot reserve space, and the page shifts when the image loads. |
| SEO035 | warn | link text is generic ("click here", "read more", "here", "more", "link", "learn more", "open", "continue", "details", "go") | Link text is read out of context by assistive technology and used by engines to describe the target. "Open the model" says less than "CFTR protein model (draft)". |
| SEO036 | error | a link has no accessible name | A link with nothing to read is unusable without a mouse. |
| SEO037 | info | a module script with no `modulepreload` | The module the page needs first can be fetched in parallel with the HTML parse. |
| SEO038 | info | a stylesheet declares `@font-face` and the page preloads no font | Late fonts cause a visible swap and layout shift; preload the one the first paint needs. |
| SEO040 | error | a JSON-LD block is not valid JSON | Broken structured data is ignored at best. |
| SEO041 | warn | JSON-LD without `@context` | Without `https://schema.org` the types mean nothing. |
| SEO042 | warn | a `@type` outside the allowlist | The allowlist is the set of types a small content site can honestly use; others deserve a second look. |
| SEO043 | warn | a medical `@type` (`Medical*`, `Drug`, `Physician`, `Hospital`, `Patient`, `DietarySupplement`) | These types tell engines the page is a medical authority. Use them only if that is true. |
| SEO044 | warn | a JSON-LD `name` or `headline` does not appear in the page's visible text | Structured data must describe the page a reader sees, not a page you wish you had. |
| SEO050 | warn | a `<script src>` from another host | Third-party scripts contradict a no-third-party privacy statement, add a dependency, and are what hosts inject. |
| SEO051 | info | an inline executable `<script>` | Fine on many sites; a strict Content-Security-Policy or a site's own rule may forbid it. |
| SEO052 | info | a stylesheet, preload, preconnect, dns-prefetch or icon link to another host | Hosted fonts and icons leak visitor addresses to that host; decide knowingly. |
| SEO091 | warn | a file is not valid UTF-8 | Mis-encoded text shows as garbage in results and previews. |

## What the checker cannot see

Overclaiming descriptions; dishonest but valid dates; link text that is specific but wrong; whether an image is the right image; anything the host adds to the served page; Core Web Vitals; and whether the site is a clinical authority. Those belong to steps 3 to 6 of the workflow.
