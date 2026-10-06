"""Verifier tests for `seo_audit.py`, the site-seo-review checker. Standard library only.

Run:   python -m unittest discover -s tests -v              (from the skill folder; tests ../scripts/seo_audit.py)
       SEO_AUDIT_PATH=path/to/seo_audit.py python -m unittest discover -s tests   (any other candidate)
       python tests/verify_checker.py path/to/seo_audit.py   (sets the variable and prints a short summary)

The candidate is run as a subprocess against temporary copies of `fixtures/good` (a four-page site that must yield
zero findings). Each check test applies ONE defect to a copy and asserts the exact set of (id, severity, page)
triples and the exit code, so a cascade (one defect, two IDs) fails the test that owns the defect.
"""
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
GOOD = HERE / "fixtures" / "good"
BASE = "https://example.test/"
CANDIDATE = os.environ.get("SEO_AUDIT_PATH") or str(HERE.parent / "scripts" / "seo_audit.py")
TIMEOUT = 60

# fixture strings the defects edit; each must appear exactly once in its file
ABOUT = "about/index.html"
NOTES = "notes/index.html"
INDEX = "index.html"
ABOUT_TITLE = "About the lab | Example Lab"
INDEX_TITLE = "Example Lab: open tools for rare-disease research"
ABOUT_DESC = "What the lab is and is not, who maintains it, how it writes, which licences apply, and what this site collects about visitors."
INDEX_DESC = "An independent lab building small, open tools for rare-disease research, and writing down what each tool does not show. Research, not medical advice."
SHARE = 'og:image" content="https://example.test/images/share.png"'
NOTES_LD = ('  {"@context": "https://schema.org", "@type": "Article", "headline": "Reading a registry report before quoting a number", '
            '"datePublished": "2026-10-01", "author": {"@type": "Person", "name": "Example Lab maintainer"}}')
NOTES_LINK = '<a href="/notes/">reading a registry report before quoting a number</a>'
ABOUT_IMG = '<img src="/images/share.png" alt="A plain grey card with the lab\'s name" width="600" height="315">'
NOINDEX_PAGE = ('<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Draft</title>'
                '<meta name="robots" content="noindex, nofollow"></head><body><h1>Draft page</h1><p>Not ready.</p></body></html>\n')


def _load_gen():
    spec = importlib.util.spec_from_file_location("gen_fixtures", HERE / "fixtures" / "gen_fixtures.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


GEN = _load_gen()


def setUpModule():
    if not CANDIDATE or not Path(CANDIDATE).is_file():
        raise RuntimeError("SEO_AUDIT_PATH must point at the candidate seo_audit.py")
    GEN.write_all(GOOD)


def run(site, *args, base=BASE, json_mode=True):
    """Run the candidate on `site`. Returns (exit code, parsed JSON or None, stdout, stderr)."""
    cmd = [sys.executable, CANDIDATE, str(site)]
    if base is not None:
        cmd += ["--base-url", base]
    if json_mode:
        cmd.append("--json")
    cmd += list(args)
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=TIMEOUT)
    data = None
    if json_mode and p.stdout.strip():
        try:
            data = json.loads(p.stdout)
        except ValueError:
            data = None
    return p.returncode, data, p.stdout, p.stderr


def triples(data):
    return [(f["id"], f["severity"], f["page"]) for f in data["findings"]]


class SiteCase(unittest.TestCase):
    """Shared helpers: a fresh copy of the good site, one-string edits, and an exact-findings assertion."""

    def site(self):
        d = Path(tempfile.mkdtemp(prefix="seo-")) / "site"
        shutil.copytree(GOOD, d)
        self.addCleanup(shutil.rmtree, d.parent, True)
        return d

    def edit(self, site, rel, old, new):
        p = site / rel
        text = p.read_text(encoding="utf-8")
        self.assertEqual(text.count(old), 1, f"fixture drift: {old[:60]!r} is not unique in {rel}")
        p.write_text(text.replace(old, new), encoding="utf-8")

    def remove_line(self, site, rel, fragment):
        p = site / rel
        lines = p.read_text(encoding="utf-8").splitlines(keepends=True)
        hits = [ln for ln in lines if fragment in ln]
        self.assertEqual(len(hits), 1, f"fixture drift: {fragment[:60]!r} is on {len(hits)} lines of {rel}")
        p.write_text("".join(ln for ln in lines if fragment not in ln), encoding="utf-8")

    def insert_in_head(self, site, rel, markup):
        self.edit(site, rel, "</head>", f"  {markup}\n</head>")

    def expect(self, site, expected, code, *args, base=BASE):
        rc, data, out, err = run(site, *args, base=base)
        if data is None:
            self.fail(f"no JSON document on stdout (exit {rc}); stderr: {err.strip()[:200]!r}; stdout: {out.strip()[:120]!r}")
        got = triples(data)
        if sorted(got) != sorted(expected):
            self.fail(f"findings expected {sorted(expected)} got {sorted(got)}")
        self.assertEqual(rc, code, f"exit code expected {code} got {rc} for findings {got}")
        return data


# ================================================================ the good site
class TestGoodSite(SiteCase):
    def test_good_site_has_no_findings_with_base_url(self):
        """The unmodified fixture site yields zero findings of any severity and exit 0."""
        self.expect(self.site(), [], 0)

    def test_good_site_has_no_findings_without_base_url(self):
        """Without --base-url, canonical, sitemap and robots are compared by URL path and still pass."""
        self.expect(self.site(), [], 0, base=None)

    def test_base_url_without_trailing_slash_is_normalised(self):
        """`--base-url https://example.test` is treated as `https://example.test/`."""
        data = self.expect(self.site(), [], 0, base="https://example.test")
        self.assertEqual(data["base_url"], BASE)

    def test_pages_and_indexed_pages_are_listed_sorted(self):
        """`pages` lists every .html by forward-slash path, sorted; `indexed_pages` leaves out 404.html."""
        data = self.expect(self.site(), [], 0)
        self.assertEqual(data["pages"], ["404.html", "about/index.html", "index.html", "notes/index.html"])
        self.assertEqual(data["indexed_pages"], ["about/index.html", "index.html", "notes/index.html"])

    def test_noindex_page_is_exempt_from_metadata_checks(self):
        """A page whose robots meta says `noindex, nofollow` gets no metadata findings and is not expected in the sitemap."""
        site = self.site()
        (site / "drafts").mkdir()
        (site / "drafts" / "index.html").write_text(NOINDEX_PAGE, encoding="utf-8")
        data = self.expect(site, [], 0)
        self.assertNotIn("drafts/index.html", data["indexed_pages"])
        self.assertIn("drafts/index.html", data["pages"])


# ================================================================ interface
class TestInterface(SiteCase):
    def three_defects(self):
        site = self.site()
        self.remove_line(site, ABOUT, "<title>")
        self.edit(site, NOTES, "<h3>Denominators</h3>", "<h4>Denominators</h4>")
        self.edit(site, "robots.txt", "Disallow:\n", "Disallow: /notes/\n")
        return site

    def test_json_shape(self):
        """The JSON document has version, base_url, pages, indexed_pages, findings and counts, and each finding has four keys."""
        site = self.three_defects()
        rc, data, out, err = run(site)
        self.assertIsNotNone(data, f"no JSON: {err[:200]!r}")
        self.assertEqual(sorted(data), ["base_url", "counts", "findings", "indexed_pages", "pages", "version"])
        self.assertEqual(data["version"], 1)
        for f in data["findings"]:
            self.assertEqual(sorted(f), ["id", "message", "page", "severity"], f)
            self.assertRegex(f["id"], r"^SEO\d{3}$")
            self.assertIn(f["severity"], ("error", "warn", "info"))
            self.assertIsInstance(f["message"], str)

    def test_output_is_deterministic_across_runs(self):
        """Two runs on the same folder print byte-identical stdout (no timestamps, no unsorted iteration)."""
        site = self.three_defects()
        _, _, out1, _ = run(site)
        _, _, out2, _ = run(site)
        self.assertTrue(out1.strip(), "empty output")
        self.assertEqual(out1, out2)

    def test_findings_are_sorted_by_page_then_id(self):
        """Findings are ordered by (page, id, message): about/ before notes/ before robots.txt, whatever the ID order."""
        data = self.expect(self.three_defects(), [("SEO001", "error", ABOUT), ("SEO032", "warn", NOTES), ("SEO026", "error", "robots.txt")], 1)
        self.assertEqual(triples(data), [("SEO001", "error", ABOUT), ("SEO032", "warn", NOTES), ("SEO026", "error", "robots.txt")])

    def test_counts_match_findings(self):
        """`counts` has error, warn and info and agrees with the findings list."""
        data = self.expect(self.three_defects(), [("SEO001", "error", ABOUT), ("SEO032", "warn", NOTES), ("SEO026", "error", "robots.txt")], 1)
        self.assertEqual(data["counts"], {"error": 2, "warn": 1, "info": 0})

    def test_text_mode_summary_line(self):
        """Without --json the last line is `E errors, W warnings, I info in N pages (K indexed)`."""
        rc, _, out, err = run(self.site(), json_mode=False)
        self.assertEqual(rc, 0, err[:200])
        lines = [ln for ln in out.splitlines() if ln.strip()]
        self.assertTrue(lines, "no text output")
        self.assertRegex(lines[-1], r"^0 errors, 0 warnings, 0 info in 4 pages \(3 indexed\)$")

    def test_text_mode_finding_line_format(self):
        """Text mode prints one `ID severity page: message` line per finding before the summary."""
        site = self.site()
        self.remove_line(site, ABOUT, "<title>")
        rc, _, out, _ = run(site, json_mode=False)
        self.assertEqual(rc, 1)
        self.assertTrue(any(re.match(r"^SEO001 error about/index\.html: \S", ln) for ln in out.splitlines()), out[:300])

    def test_warning_only_exits_0_without_strict(self):
        """A site with only warnings (SEO002) exits 0 by default."""
        site = self.site()
        self.edit(site, ABOUT, f"<title>{ABOUT_TITLE}</title>", "<title>About</title>")
        self.edit(site, ABOUT, f'og:title" content="{ABOUT_TITLE}"', 'og:title" content="About"')
        self.expect(site, [("SEO002", "warn", ABOUT)], 0)

    def test_strict_turns_warnings_into_exit_1(self):
        """With --strict the same warning-only site exits 1 while the severity stays `warn`."""
        site = self.site()
        self.edit(site, ABOUT, f"<title>{ABOUT_TITLE}</title>", "<title>About</title>")
        self.edit(site, ABOUT, f'og:title" content="{ABOUT_TITLE}"', 'og:title" content="About"')
        self.expect(site, [("SEO002", "warn", ABOUT)], 1, "--strict")

    def test_strict_ignores_info_only(self):
        """Info findings (SEO013) never change the exit code, even with --strict."""
        site = self.site()
        self.remove_line(site, ABOUT, 'property="og:image"')
        self.expect(site, [("SEO013", "info", ABOUT)], 0)
        self.expect(site, [("SEO013", "info", ABOUT)], 0, "--strict")

    def test_no_arguments_is_usage_error_2(self):
        """Running with no SITE_DIR exits 2."""
        p = subprocess.run([sys.executable, CANDIDATE], capture_output=True, text=True, timeout=TIMEOUT)
        self.assertEqual(p.returncode, 2, p.stderr[:200])

    def test_missing_directory_is_usage_error_2(self):
        """A SITE_DIR that does not exist exits 2 with nothing on stdout."""
        site = self.site()
        rc, data, out, err = run(site / "nope")
        self.assertEqual(rc, 2, err[:200])
        self.assertEqual(out.strip(), "")

    def test_empty_directory_is_usage_error_2(self):
        """A folder with no .html file exits 2 with nothing on stdout."""
        site = self.site()
        empty = site.parent / "empty"
        empty.mkdir()
        rc, data, out, err = run(empty)
        self.assertEqual(rc, 2, err[:200])
        self.assertEqual(out.strip(), "")

    def test_unknown_flag_is_usage_error_2(self):
        """An unknown option exits 2."""
        rc, _, _, err = run(self.site(), "--bogus")
        self.assertEqual(rc, 2, err[:200])

    def test_json_out_writes_the_same_document(self):
        """--json-out PATH writes the JSON document to PATH; it equals what --json prints."""
        site = self.site()
        self.remove_line(site, ABOUT, "<title>")
        target = site.parent / "report.json"
        rc, data, out, err = run(site, "--json-out", str(target))
        self.assertEqual(rc, 1, err[:200])
        self.assertTrue(target.is_file(), "report.json was not written")
        self.assertEqual(json.loads(target.read_text(encoding="utf-8"))["findings"], data["findings"])

    def test_nothing_is_written_into_the_site_folder(self):
        """Without --json-out the script writes no file at all: the site folder listing is unchanged."""
        site = self.site()
        before = sorted(p.relative_to(site).as_posix() for p in site.rglob("*"))
        run(site)
        run(site, json_mode=False)
        after = sorted(p.relative_to(site).as_posix() for p in site.rglob("*"))
        self.assertEqual(before, after)

    def test_output_contains_no_absolute_paths(self):
        """Messages and page fields never contain the absolute folder path (portable, deterministic output)."""
        site = self.three_defects()
        _, data, out, _ = run(site)
        _, _, text_out, _ = run(site, json_mode=False)
        # decoded fields too: JSON escapes the backslashes of a Windows path, so raw stdout alone never matches it
        fields = [f["page"] + " " + f["message"] for f in (data or {}).get("findings", [])]
        for blob in [out, text_out] + fields:
            for form in {str(site), site.as_posix(), str(site.resolve()), site.resolve().as_posix()}:
                self.assertNotIn(form, blob)

    def test_source_has_no_network_or_subprocess_imports(self):
        """The script's source imports no socket, urllib.request, http.client, requests, subprocess or asyncio (no network, ever)."""
        src = Path(CANDIDATE).read_text(encoding="utf-8", errors="replace")
        pattern = re.compile(r"^\s*(?:import|from)\s+(socket|urllib\.request|http\.client|http\.server|requests|subprocess|asyncio|ftplib|smtplib|xmlrpc|webbrowser|ssl|telnetlib)\b", re.M)
        self.assertEqual([m.group(1) for m in pattern.finditer(src)], [])
        self.assertNotIn("urllib.request", src)

    def test_source_does_not_exec_or_eval(self):
        """The script never calls exec() or eval(): page content is data, not code."""
        src = Path(CANDIDATE).read_text(encoding="utf-8", errors="replace")
        self.assertIsNone(re.search(r"(?<![\w.])(?:exec|eval)\s*\(", src))


# ================================================================ page metadata checks
class TestPageMetadata(SiteCase):
    def test_seo001_title_missing(self):
        """SEO001: a page with no <title> gets SEO001 only (no SEO002, SEO003 or SEO010 cascade)."""
        site = self.site()
        self.remove_line(site, ABOUT, "<title>")
        self.expect(site, [("SEO001", "error", ABOUT)], 1)

    def test_seo002_title_too_short(self):
        """SEO002: a 5-character title is outside 20..70."""
        site = self.site()
        self.edit(site, ABOUT, f"<title>{ABOUT_TITLE}</title>", "<title>About</title>")
        self.edit(site, ABOUT, f'og:title" content="{ABOUT_TITLE}"', 'og:title" content="About"')
        self.expect(site, [("SEO002", "warn", ABOUT)], 0)

    def test_seo003_duplicate_title(self):
        """SEO003: two indexed pages sharing a title are both reported."""
        site = self.site()
        self.edit(site, ABOUT, f"<title>{ABOUT_TITLE}</title>", f"<title>{INDEX_TITLE}</title>")
        self.edit(site, ABOUT, f'og:title" content="{ABOUT_TITLE}"', f'og:title" content="{INDEX_TITLE}"')
        self.expect(site, [("SEO003", "error", ABOUT), ("SEO003", "error", INDEX)], 1)

    def test_seo004_description_missing(self):
        """SEO004: a page with no meta description gets SEO004 only."""
        site = self.site()
        self.remove_line(site, ABOUT, 'name="description"')
        self.expect(site, [("SEO004", "error", ABOUT)], 1)

    def test_seo005_description_too_short(self):
        """SEO005: a 6-character description is outside 60..160."""
        site = self.site()
        self.edit(site, ABOUT, f'name="description" content="{ABOUT_DESC}"', 'name="description" content="Short."')
        self.edit(site, ABOUT, f'og:description" content="{ABOUT_DESC}"', 'og:description" content="Short."')
        self.expect(site, [("SEO005", "warn", ABOUT)], 0)

    def test_seo006_duplicate_description(self):
        """SEO006: two indexed pages sharing a description are both reported."""
        site = self.site()
        self.edit(site, ABOUT, f'name="description" content="{ABOUT_DESC}"', f'name="description" content="{INDEX_DESC}"')
        self.edit(site, ABOUT, f'og:description" content="{ABOUT_DESC}"', f'og:description" content="{INDEX_DESC}"')
        self.expect(site, [("SEO006", "error", ABOUT), ("SEO006", "error", INDEX)], 1)

    def test_seo007_canonical_missing(self):
        """SEO007: a page with no canonical link gets SEO007 only (SEO012 is skipped)."""
        site = self.site()
        self.remove_line(site, ABOUT, 'rel="canonical"')
        self.expect(site, [("SEO007", "error", ABOUT)], 1)

    def test_seo008_canonical_differs_from_own_address(self):
        """SEO008: a canonical without the trailing slash is not the page's address (og:url matches it, so no SEO012)."""
        site = self.site()
        self.edit(site, ABOUT, 'rel="canonical" href="https://example.test/about/"', 'rel="canonical" href="https://example.test/about"')
        self.edit(site, ABOUT, 'og:url" content="https://example.test/about/"', 'og:url" content="https://example.test/about"')
        self.expect(site, [("SEO008", "error", ABOUT)], 1)

    def test_seo009_canonical_not_absolute(self):
        """SEO009: a root-relative canonical `/about/` is not absolute (its path matches, so no SEO008)."""
        site = self.site()
        self.edit(site, ABOUT, 'rel="canonical" href="https://example.test/about/"', 'rel="canonical" href="/about/"')
        self.edit(site, ABOUT, 'og:url" content="https://example.test/about/"', 'og:url" content="/about/"')
        self.expect(site, [("SEO009", "error", ABOUT)], 1)

    def test_seo010_og_title_differs(self):
        """SEO010: og:title that differs from the title."""
        site = self.site()
        self.edit(site, ABOUT, f'og:title" content="{ABOUT_TITLE}"', 'og:title" content="Something else entirely"')
        self.expect(site, [("SEO010", "error", ABOUT)], 1)

    def test_seo011_og_description_missing(self):
        """SEO011: og:description absent while the description exists."""
        site = self.site()
        self.remove_line(site, ABOUT, 'property="og:description"')
        self.expect(site, [("SEO011", "error", ABOUT)], 1)

    def test_seo012_og_url_differs_from_canonical(self):
        """SEO012: og:url that is not the canonical."""
        site = self.site()
        self.edit(site, ABOUT, 'og:url" content="https://example.test/about/"', 'og:url" content="https://example.test/"')
        self.expect(site, [("SEO012", "error", ABOUT)], 1)

    def test_seo013_og_image_absent(self):
        """SEO013: no og:image is an info finding."""
        site = self.site()
        self.remove_line(site, ABOUT, 'property="og:image"')
        self.expect(site, [("SEO013", "info", ABOUT)], 0)

    def test_seo014_og_image_file_missing(self):
        """SEO014: og:image on the site's own host naming a file that does not exist."""
        site = self.site()
        self.edit(site, ABOUT, SHARE, 'og:image" content="https://example.test/images/missing.png"')
        self.expect(site, [("SEO014", "error", ABOUT)], 1)

    def test_seo015_og_image_wrong_size(self):
        """SEO015: an existing PNG og:image that is 600x315, not 1200x630."""
        site = self.site()
        (site / "images" / "small.png").write_bytes(GEN.png(600, 315))
        self.edit(site, ABOUT, SHARE, 'og:image" content="https://example.test/images/small.png"')
        self.expect(site, [("SEO015", "warn", ABOUT)], 0)

    def test_seo016_og_image_on_another_host_not_checked(self):
        """SEO016: an og:image on another host is reported as not checked (info), not as missing."""
        site = self.site()
        self.edit(site, ABOUT, SHARE, 'og:image" content="https://cdn.example.net/share.png"')
        self.expect(site, [("SEO016", "info", ABOUT)], 0)

    def test_seo017_404_page_is_indexable(self):
        """SEO017: 404.html without a robots noindex meta; it is still never treated as an indexed page."""
        site = self.site()
        self.remove_line(site, "404.html", 'name="robots"')
        self.expect(site, [("SEO017", "error", "404.html")], 1)

    def test_seo018_404_page_missing(self):
        """SEO018: no 404.html at the root is an info finding attributed to 404.html."""
        site = self.site()
        (site / "404.html").unlink()
        self.expect(site, [("SEO018", "info", "404.html")], 0)

    def test_seo019_404_page_has_canonical(self):
        """SEO019: a canonical link on the 404 page."""
        site = self.site()
        self.insert_in_head(site, "404.html", '<link rel="canonical" href="https://example.test/404.html">')
        self.expect(site, [("SEO019", "error", "404.html")], 1)


# ================================================================ page content checks
class TestPageContent(SiteCase):
    def test_seo030_no_h1(self):
        """SEO030: a page whose only top heading is an h2 has no h1 (no SEO032: the first heading never 'skips')."""
        site = self.site()
        self.edit(site, ABOUT, "<h1>About the lab</h1>", "<h2>About the lab</h2>")
        self.expect(site, [("SEO030", "error", ABOUT)], 1)

    def test_seo031_two_h1(self):
        """SEO031: two h1 elements on one page."""
        site = self.site()
        self.edit(site, ABOUT, "<h1>About the lab</h1>", "<h1>About the lab</h1>\n    <h1>A second main heading</h1>")
        self.expect(site, [("SEO031", "warn", ABOUT)], 0)

    def test_seo032_skipped_heading_level(self):
        """SEO032: h2 followed by h4 skips a level."""
        site = self.site()
        self.edit(site, NOTES, "<h3>Denominators</h3>", "<h4>Denominators</h4>")
        self.expect(site, [("SEO032", "warn", NOTES)], 0)

    def test_seo033_image_without_alt(self):
        """SEO033: an img with no alt attribute at all."""
        site = self.site()
        self.edit(site, ABOUT, ABOUT_IMG, '<img src="/images/share.png" width="600" height="315">')
        self.expect(site, [("SEO033", "error", ABOUT)], 1)

    def test_seo034_image_without_dimensions(self):
        """SEO034: an img with alt but no width/height (layout shift)."""
        site = self.site()
        self.edit(site, ABOUT, ABOUT_IMG, '<img src="/images/share.png" alt="A plain grey card with the lab\'s name">')
        self.expect(site, [("SEO034", "warn", ABOUT)], 0)

    def test_seo035_generic_link_text(self):
        """SEO035: a link whose text is `click here`."""
        site = self.site()
        self.edit(site, ABOUT, NOTES_LINK, '<a href="/notes/">click here</a>')
        self.expect(site, [("SEO035", "warn", ABOUT)], 0)

    def test_seo036_link_without_accessible_name(self):
        """SEO036: a link with no text, no image alt and no aria-label."""
        site = self.site()
        self.edit(site, ABOUT, NOTES_LINK, '<a href="/notes/"></a>')
        self.expect(site, [("SEO036", "error", ABOUT)], 1)

    def test_seo037_module_without_modulepreload(self):
        """SEO037: a module script with no modulepreload link on that page."""
        site = self.site()
        self.remove_line(site, ABOUT, 'rel="modulepreload"')
        self.expect(site, [("SEO037", "info", ABOUT)], 0)

    def test_seo038_font_face_without_preload(self):
        """SEO038: the page's stylesheet declares @font-face but the page preloads no font."""
        site = self.site()
        self.remove_line(site, ABOUT, 'as="font"')
        self.expect(site, [("SEO038", "info", ABOUT)], 0)

    def test_seo040_json_ld_does_not_parse(self):
        """SEO040: a truncated JSON-LD block is an error, and nothing else is reported for it."""
        site = self.site()
        self.edit(site, NOTES, NOTES_LD, '  {"@context": "https://schema.org", "@type": "Article",')
        self.expect(site, [("SEO040", "error", NOTES)], 1)

    def test_seo041_json_ld_without_context(self):
        """SEO041: a top-level JSON-LD object with no @context."""
        site = self.site()
        self.edit(site, NOTES, '"@context": "https://schema.org", "@type": "Article"', '"@type": "Article"')
        self.expect(site, [("SEO041", "warn", NOTES)], 0)

    def test_seo042_json_ld_type_outside_allowlist(self):
        """SEO042: @type Recipe is not in the allowlist and is not medical."""
        site = self.site()
        self.edit(site, NOTES, '"@type": "Article"', '"@type": "Recipe"')
        self.expect(site, [("SEO042", "warn", NOTES)], 0)

    def test_seo043_json_ld_medical_type(self):
        """SEO043: @type MedicalWebPage is flagged as a medical type (and not also as SEO042)."""
        site = self.site()
        self.edit(site, NOTES, '"@type": "Article"', '"@type": "MedicalWebPage"')
        self.expect(site, [("SEO043", "warn", NOTES)], 0)

    def test_seo044_json_ld_headline_not_on_page(self):
        """SEO044: a JSON-LD headline that the page's visible text does not contain."""
        site = self.site()
        self.edit(site, NOTES, '"headline": "Reading a registry report before quoting a number"', '"headline": "A headline the page never shows"')
        self.expect(site, [("SEO044", "warn", NOTES)], 0)

    def test_seo050_third_party_script(self):
        """SEO050: a script loaded from another host."""
        site = self.site()
        self.insert_in_head(site, ABOUT, '<script src="https://analytics.example.net/a.js"></script>')
        self.expect(site, [("SEO050", "warn", ABOUT)], 0)

    def test_seo051_inline_script(self):
        """SEO051: an inline executable script (not JSON-LD) is an info finding."""
        site = self.site()
        self.insert_in_head(site, ABOUT, '<script>console.log("hello")</script>')
        self.expect(site, [("SEO051", "info", ABOUT)], 0)

    def test_seo052_third_party_stylesheet(self):
        """SEO052: a stylesheet link to another host (a typical hosted-font include)."""
        site = self.site()
        self.insert_in_head(site, ABOUT, '<link rel="stylesheet" href="https://fonts.example.net/css?family=Body">')
        self.expect(site, [("SEO052", "info", ABOUT)], 0)


# ================================================================ site-level checks
class TestSiteLevel(SiteCase):
    def test_seo020_sitemap_missing(self):
        """SEO020: no sitemap.xml; SEO021/SEO022 are skipped and robots still passes."""
        site = self.site()
        (site / "sitemap.xml").unlink()
        self.expect(site, [("SEO020", "error", "sitemap.xml")], 1)

    def test_seo021_sitemap_lists_a_page_that_does_not_exist(self):
        """SEO021: a <loc> for a page that is not an indexed page, with the loc in the message."""
        site = self.site()
        self.edit(site, "sitemap.xml", "</urlset>", "  <url><loc>https://example.test/drafts/</loc><lastmod>2026-10-01</lastmod></url>\n</urlset>")
        data = self.expect(site, [("SEO021", "error", "sitemap.xml")], 1)
        self.assertIn("https://example.test/drafts/", data["findings"][0]["message"])

    def test_seo021_sitemap_lists_a_noindex_page(self):
        """SEO021: a noindex page is not an indexed page, so its <loc> is an error."""
        site = self.site()
        (site / "drafts").mkdir()
        (site / "drafts" / "index.html").write_text(NOINDEX_PAGE, encoding="utf-8")
        self.edit(site, "sitemap.xml", "</urlset>", "  <url><loc>https://example.test/drafts/</loc></url>\n</urlset>")
        self.expect(site, [("SEO021", "error", "sitemap.xml")], 1)

    def test_seo022_indexed_page_missing_from_sitemap(self):
        """SEO022: an indexed page with no <loc>, with its URL path in the message."""
        site = self.site()
        self.remove_line(site, "sitemap.xml", "<loc>https://example.test/notes/</loc>")
        data = self.expect(site, [("SEO022", "error", "sitemap.xml")], 1)
        self.assertIn("/notes/", data["findings"][0]["message"])

    def test_seo023_lastmod_in_the_future(self):
        """SEO023: a lastmod of 2999-01-01 is not an honest date."""
        site = self.site()
        self.edit(site, "sitemap.xml", "<loc>https://example.test/notes/</loc><lastmod>2026-10-01</lastmod>",
                  "<loc>https://example.test/notes/</loc><lastmod>2999-01-01</lastmod>")
        self.expect(site, [("SEO023", "warn", "sitemap.xml")], 0)

    def test_seo024_robots_missing(self):
        """SEO024: no robots.txt; SEO025/SEO026 are skipped."""
        site = self.site()
        (site / "robots.txt").unlink()
        self.expect(site, [("SEO024", "error", "robots.txt")], 1)

    def test_seo025_robots_does_not_name_the_sitemap(self):
        """SEO025: robots.txt without a Sitemap line."""
        site = self.site()
        self.remove_line(site, "robots.txt", "Sitemap:")
        self.expect(site, [("SEO025", "warn", "robots.txt")], 0)

    def test_seo026_robots_disallows_an_indexed_page(self):
        """SEO026: `Disallow: /notes/` in the `*` group blocks an indexed page, with the pattern in the message."""
        site = self.site()
        self.edit(site, "robots.txt", "Disallow:\n", "Disallow: /notes/\n")
        data = self.expect(site, [("SEO026", "error", "robots.txt")], 1)
        self.assertIn("/notes/", data["findings"][0]["message"])


# ================================================================ robustness
class TestRobustness(SiteCase):
    def test_page_without_head_does_not_crash(self):
        """Robustness: a page with no <head> yields SEO001, SEO004 and SEO007 for that page and a normal exit 1."""
        site = self.site()
        (site / "bare.html").write_text("<!doctype html><html><body><h1>Bare</h1><p>Text</p></body></html>\n", encoding="utf-8")
        rc, data, out, err = run(site)
        self.assertIsNotNone(data, f"no JSON (exit {rc}): {err[-300:]!r}")
        self.assertEqual(rc, 1)
        ids = {f["id"] for f in data["findings"] if f["page"] == "bare.html"}
        self.assertTrue({"SEO001", "SEO004", "SEO007"} <= ids, ids)

    def test_huge_attribute_value_does_not_crash_or_hang(self):
        """Robustness: a 1 MB attribute value is parsed within the timeout and changes nothing."""
        site = self.site()
        self.edit(site, ABOUT, "<h1>About the lab</h1>", '<p data-x="' + "a" * 1_000_000 + '"></p>\n    <h1>About the lab</h1>')
        self.expect(site, [], 0)

    def test_non_utf8_page_is_reported_and_still_audited(self):
        """SEO091: a Latin-1 page is a warning, not a crash, and its other checks still pass."""
        site = self.site()
        p = site / ABOUT
        text = p.read_text(encoding="utf-8").replace("Questions and corrections", "Questions and corrections (résumé)")
        p.write_bytes(text.encode("latin-1"))
        self.expect(site, [("SEO091", "warn", ABOUT)], 0)

    def test_malformed_sitemap_is_seo020_not_a_crash(self):
        """SEO020 (robustness): an unclosed sitemap.xml is reported as not well-formed; nothing else about the sitemap is reported."""
        site = self.site()
        (site / "sitemap.xml").write_text("<urlset><url><loc>https://example.test/</loc>", encoding="utf-8")
        self.expect(site, [("SEO020", "error", "sitemap.xml")], 1)

    def test_empty_json_ld_block_is_seo040(self):
        """SEO040 (robustness): an empty JSON-LD block is invalid JSON, not a crash."""
        site = self.site()
        self.edit(site, NOTES, NOTES_LD, "  ")
        self.expect(site, [("SEO040", "error", NOTES)], 1)


if __name__ == "__main__":
    unittest.main()
