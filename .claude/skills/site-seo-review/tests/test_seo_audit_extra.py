"""Extra tests for `seo_audit.py`: behaviour the main suite cannot see. Standard library only.

Run:   python -m unittest discover -s tests -v       (from the skill folder; runs both test files)

These were written while reviewing a checker that already passed every test in `test_seo_audit.py`: each one
probes a rule that file could not see (sub-folder addresses, the 404 page's content checks, robots groups,
`@graph`, odd files, side effects). They reuse that file's helpers and fixtures, so the two files live side by side.
"""
import ast
import datetime
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import test_seo_audit as base
from test_seo_audit import ABOUT, BASE, CANDIDATE, INDEX, NOINDEX_PAGE, NOTES, NOTES_LD, NOTES_LINK, TIMEOUT, SiteCase, run

ABOUT_IMG = base.ABOUT_IMG


def setUpModule():
    base.setUpModule()


def page(path_url, title, desc, h1):
    """A complete, finding-free indexed page whose canonical and og:url are `path_url` under the test base."""
    url = BASE + path_url
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<title>{title}</title><meta name="description" content="{desc}">'
            f'<link rel="canonical" href="{url}">'
            f'<meta property="og:title" content="{title}"><meta property="og:description" content="{desc}">'
            f'<meta property="og:url" content="{url}"><meta property="og:image" content="{BASE}images/share.png">'
            f'</head><body><h1>{h1}</h1><p>Body text.</p></body></html>\n')


DEEP_DESC = "A page three folders deep that exists only to check how the checker turns a file path into an address."
FLAT_DESC = "A page whose file name is not index.html, so its address keeps the .html name and has no trailing slash."


class ExtraCase(SiteCase):
    def add_loc(self, site, url):
        self.edit(site, "sitemap.xml", "</urlset>", f"  <url><loc>{url}</loc></url>\n</urlset>")

    def replace_all(self, site, rel, old, new):
        p = site / rel
        text = p.read_text(encoding="utf-8")
        self.assertIn(old, text, f"fixture drift: {old[:60]!r} not in {rel}")
        p.write_text(text.replace(old, new), encoding="utf-8")


# ================================================================ addresses and page discovery
class TestAddresses(ExtraCase):
    def test_deep_sub_folder_index_page(self):
        """Reading rules: `a/b/c/index.html` has address `a/b/c/`; a correct canonical and sitemap entry give no finding."""
        site = self.site()
        (site / "a" / "b" / "c").mkdir(parents=True)
        (site / "a" / "b" / "c" / "index.html").write_text(
            page("a/b/c/", "A deep page for the address check", DEEP_DESC, "A deep page"), encoding="utf-8")
        self.add_loc(site, BASE + "a/b/c/")
        data = self.expect(site, [], 0)
        self.assertIn("a/b/c/index.html", data["indexed_pages"])

    def test_non_index_page_keeps_its_file_name(self):
        """Reading rules: `guides/setup.html` has address `guides/setup.html` (no trailing slash), with and without a base."""
        site = self.site()
        (site / "guides").mkdir()
        (site / "guides" / "setup.html").write_text(
            page("guides/setup.html", "Setting up the example tools", FLAT_DESC, "Setting up"), encoding="utf-8")
        self.add_loc(site, BASE + "guides/setup.html")
        self.expect(site, [], 0)
        self.expect(site, [], 0, base=None)

    def test_non_index_page_wrong_canonical_names_the_address(self):
        """SEO008: a non-index page whose canonical has a trailing slash; the message names the right address."""
        site = self.site()
        (site / "setup.html").write_text(
            page("setup.html/", "Setting up the example tools", FLAT_DESC, "Setting up"), encoding="utf-8")
        self.add_loc(site, BASE + "setup.html")
        data = self.expect(site, [("SEO008", "error", "setup.html")], 1)
        self.assertTrue(data["findings"][0]["message"].endswith("https://example.test/setup.html"),
                        data["findings"][0]["message"])

    def test_folder_named_like_a_page_is_not_a_page(self):
        """Interface: every `*.html` file is a page; a folder called `old.html` is not, and must not crash the run."""
        site = self.site()
        (site / "old.html").mkdir()
        data = self.expect(site, [], 0)
        self.assertNotIn("old.html", data["pages"])

    def test_symlink_loop_does_not_hang(self):
        """Robustness: a symlink pointing back at the site folder neither hangs nor duplicates pages."""
        site = self.site()
        try:
            os.symlink(site, site / "loop", target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"cannot create a symlink here: {exc}")
        data = self.expect(site, [], 0)
        self.assertEqual(len(data["pages"]), 4)

    def test_site_served_under_a_sub_path(self):
        """Reading rules: with `--base-url https://example.test/lab/`, `https://example.test/lab/images/share.png` is the
        site file `images/share.png` (the remainder after the base), so a site published under a path is clean."""
        site = self.site()
        for rel in ("index.html", ABOUT, NOTES, "robots.txt", "sitemap.xml"):
            self.replace_all(site, rel, "https://example.test/", "https://example.test/lab/")
        self.expect(site, [], 0, base="https://example.test/lab/")


# ================================================================ SEO008 without a base
class TestCanonicalWithoutBase(ExtraCase):
    """SEO008 reading rule: with no base, an absolute canonical is judged by `urlsplit(canon).path` against the page's
    URL path and the host is not compared; with a base, an absolute canonical must equal the expected URL, host included."""

    def set_about_canonical(self, site, url):
        self.edit(site, ABOUT, 'rel="canonical" href="https://example.test/about/"', f'rel="canonical" href="{url}"')
        self.edit(site, ABOUT, 'og:url" content="https://example.test/about/"', f'og:url" content="{url}"')

    def test_absolute_canonical_wrong_path_without_base(self):
        """SEO008: no --base-url, absolute canonical whose path `/foo/` is not the page's URL path `/about/`."""
        site = self.site()
        self.set_about_canonical(site, "https://example.test/foo/")
        self.expect(site, [("SEO008", "error", ABOUT)], 1, base=None)

    def test_absolute_canonical_wrong_path_on_root_page_without_base(self):
        """SEO008: no --base-url, `index.html` (URL path `/`) with canonical `http://example.com/foo`."""
        site = self.site()
        self.edit(site, INDEX, 'rel="canonical" href="https://example.test/"', 'rel="canonical" href="http://example.com/foo"')
        self.edit(site, INDEX, 'og:url" content="https://example.test/"', 'og:url" content="http://example.com/foo"')
        self.expect(site, [("SEO008", "error", INDEX)], 1, base=None)

    def test_absolute_canonical_other_host_same_path_without_base(self):
        """No SEO008: no --base-url, so only the path is compared; another host with path `/about/` is clean."""
        site = self.site()
        self.set_about_canonical(site, "https://other.example/about/")
        self.expect(site, [], 0, base=None)

    def test_absolute_canonical_other_host_same_path_with_base(self):
        """SEO008: with --base-url the whole URL is compared, so another host with the right path still fires."""
        site = self.site()
        self.set_about_canonical(site, "https://other.example/about/")
        self.expect(site, [("SEO008", "error", ABOUT)], 1)


# ================================================================ odd files
class TestOddFiles(ExtraCase):
    def test_empty_html_file(self):
        """Robustness: an empty .html file is audited like any page with nothing in it."""
        site = self.site()
        (site / "empty.html").write_bytes(b"")
        self.expect(site, [("SEO001", "error", "empty.html"), ("SEO004", "error", "empty.html"),
                           ("SEO007", "error", "empty.html"), ("SEO013", "info", "empty.html"),
                           ("SEO030", "error", "empty.html"), ("SEO022", "error", "sitemap.xml")], 1)

    def test_binary_file_named_html(self):
        """Robustness: random bytes in a .html file produce SEO091 and ordinary findings, not a traceback."""
        site = self.site()
        (site / "blob.html").write_bytes(bytes((i * 151 + 7) % 256 for i in range(20000)))
        rc, data, out, err = run(site)
        self.assertIsNotNone(data, f"no JSON (exit {rc}): {err[-300:]!r}")
        self.assertIn(("SEO091", "warn", "blob.html"), base.triples(data))
        self.assertEqual(rc, 1)

    def test_large_file_is_audited_in_time(self):
        """Robustness: a 4 MB page finishes within the timeout and changes nothing else."""
        site = self.site()
        self.edit(site, ABOUT, "<h1>About the lab</h1>", "<h1>About the lab</h1>\n" + "<p>Plain words.</p>\n" * 220_000)
        self.expect(site, [], 0)

    def test_deeply_nested_unclosed_elements(self):
        """Reading rules (unbalanced tags must not crash): 3,000 `<li>` without `</li>` nest 3,000 deep in a simple tree."""
        site = self.site()
        self.edit(site, ABOUT, "<h1>About the lab</h1>",
                  "<h1>About the lab</h1>\n<ul>" + "<li>item" * 3000 + "</ul>")
        self.expect(site, [], 0)

    def test_deeply_nested_json_ld_does_not_crash(self):
        """Robustness: JSON-LD nested too deep for the JSON parser still gives a JSON report, not a traceback."""
        site = self.site()
        self.edit(site, NOTES, NOTES_LD, "[" * 100_000 + "]" * 100_000)
        rc, data, out, err = run(site)
        self.assertIsNotNone(data, f"no JSON (exit {rc}): {err[-300:]!r}")

    def test_non_ascii_path_with_spaces_in_text_mode(self):
        """Reading rules (page path) and output: a page under `日本 notes/` is listed with forward slashes and printed in text mode without
        an encoding crash, whatever the console code page."""
        site = self.site()
        folder = site / "日本 notes"
        folder.mkdir()
        (folder / "index.html").write_text(NOINDEX_PAGE.replace("<h1>Draft page</h1>", "<h2>Draft page</h2>"),
                                           encoding="utf-8")
        env = {k: v for k, v in os.environ.items() if k not in ("PYTHONIOENCODING", "PYTHONUTF8")}
        p = subprocess.run([sys.executable, CANDIDATE, str(site), "--base-url", BASE], capture_output=True,
                           timeout=TIMEOUT, env=env)
        out = p.stdout.decode("utf-8", errors="replace")
        self.assertEqual(p.returncode, 1, p.stderr.decode("utf-8", "replace")[-300:])
        self.assertIn("SEO030 error 日本 notes/index.html: ", out)
        rc, data, _, _ = run(site)
        self.assertIn("日本 notes/index.html", data["pages"])


# ================================================================ the 404 page
class TestNotFoundPage(ExtraCase):
    def test_content_checks_run_on_the_404_page(self):
        """Reading rules: content checks (SEO030 to SEO052) run on every page, the 404 included."""
        site = self.site()
        self.edit(site, "404.html", "<h1>Page not found</h1>", "<h2>Page not found</h2>")
        self.expect(site, [("SEO030", "error", "404.html")], 1)

    def test_inline_script_on_the_404_page(self):
        """Reading rules: SEO051 on the 404 page too."""
        site = self.site()
        self.insert_in_head(site, "404.html", '<script>console.log("lost")</script>')
        self.expect(site, [("SEO051", "info", "404.html")], 0)

    def test_non_utf8_404_page(self):
        """SEO091 applies to every page, the 404 included."""
        site = self.site()
        p = site / "404.html"
        p.write_bytes(p.read_text(encoding="utf-8").replace("may have moved", "may have moved (déjà)").encode("latin-1"))
        self.expect(site, [("SEO091", "warn", "404.html")], 0)


# ================================================================ HTML parsing
class TestParsing(ExtraCase):
    def test_noindex_inside_a_comma_list(self):
        """Reading rules: `max-snippet:-1, NoIndex` contains the token noindex after split, strip and lower-case."""
        site = self.site()
        (site / "drafts").mkdir()
        (site / "drafts" / "index.html").write_text(
            NOINDEX_PAGE.replace('content="noindex, nofollow"', 'content="max-snippet:-1, NoIndex "'), encoding="utf-8")
        data = self.expect(site, [], 0)
        self.assertNotIn("drafts/index.html", data["indexed_pages"])

    def test_noindex_must_be_a_whole_token(self):
        """Reading rules: `noindexed-later` is not the token noindex, so the page is indexed (and needs a sitemap entry)."""
        site = self.site()
        self.insert_in_head(site, ABOUT, '<meta name="robots" content="index, noindexed-later">')
        data = self.expect(site, [], 0)
        self.assertIn(ABOUT, data["indexed_pages"])

    def test_duplicate_attribute_first_wins(self):
        """HTML parsing rule (browsers keep the first of two equal attribute names): the second href is ignored."""
        site = self.site()
        self.edit(site, ABOUT, 'rel="canonical" href="https://example.test/about/"',
                  'rel="canonical" href="https://example.test/about/" href="https://example.test/elsewhere/"')
        self.expect(site, [], 0)

    def test_self_closing_non_void_tag_is_a_start_tag(self):
        """Reading rules: `handle_startendtag` is treated as a start tag, so `<a href="/notes/"/>text</a>` has its text."""
        site = self.site()
        self.edit(site, ABOUT, NOTES_LINK, '<a href="/notes/"/>reading a registry report before quoting a number</a>')
        self.expect(site, [], 0)

    def test_self_closing_div_changes_nothing(self):
        """Reading rules: a self-closed `<div/>` before the h1 neither hides the h1 nor adds a finding."""
        site = self.site()
        self.edit(site, ABOUT, "<h1>About the lab</h1>", '<div class="spacer"/><h1>About the lab</h1>')
        self.expect(site, [], 0)

    def test_attribute_without_value_does_not_crash(self):
        """Reading rules: valueless attributes (`<meta name="robots" content>`, `<a href>`, `<img alt>`) are not None-crashes."""
        site = self.site()
        self.edit(site, ABOUT, "<h1>About the lab</h1>",
                  '<h1>About the lab</h1><meta name="keywords" content><img src="/images/share.png" alt width="1" height="1">')
        self.expect(site, [], 0)

    def test_one_finding_per_image(self):
        """SEO033 and SEO034: one finding per image, so two images without alt give two findings."""
        site = self.site()
        self.edit(site, ABOUT, ABOUT_IMG, '<img src="/images/a.png"><img src="/images/a.png">')
        self.expect(site, [("SEO033", "error", ABOUT)] * 2 + [("SEO034", "warn", ABOUT)] * 2, 1)

    def test_one_finding_per_inline_script(self):
        """SEO051: one finding per script, even when two inline scripts are identical."""
        site = self.site()
        self.insert_in_head(site, ABOUT, "<script>let a = 1;</script><script>let a = 1;</script>")
        self.expect(site, [("SEO051", "info", ABOUT)] * 2, 0)

    def test_one_finding_per_heading_jump(self):
        """SEO032: one finding per jump; two identical h2 to h4 jumps are two findings."""
        site = self.site()
        self.edit(site, NOTES, "<h3>Denominators</h3>", "<h4>Denominators</h4>")
        self.edit(site, NOTES, "<h2>How a value is made</h2>", "<h2>How a value is made</h2><h4>Medians</h4>")
        self.expect(site, [("SEO032", "warn", NOTES)] * 2, 0)

    def test_stylesheet_href_with_query_string(self):
        """Reading rules (site file: drop query and fragment): `/styles.css?v=2` is `styles.css`, which has @font-face."""
        site = self.site()
        self.edit(site, ABOUT, 'rel="stylesheet" href="/styles.css"', 'rel="stylesheet" href="/styles.css?v=2#x"')
        self.remove_line(site, ABOUT, 'as="font"')
        self.expect(site, [("SEO038", "info", ABOUT)], 0)

    def test_stylesheet_outside_the_site_is_not_read(self):
        """Reading rules: a site file lives under SITE_DIR. `../../outside.css` escapes it, so it is not read or reported."""
        site = self.site()
        (site.parent / "outside.css").write_text("@font-face { font-family: X; src: url(x.woff2); }\n", encoding="utf-8")
        self.edit(site, ABOUT, 'rel="stylesheet" href="/styles.css"', 'rel="stylesheet" href="../../outside.css"')
        self.remove_line(site, ABOUT, 'as="font"')
        self.expect(site, [], 0)

    def test_relative_og_image_is_not_checked(self):
        """SEO016: a root-relative og:image is not an absolute http(s) URL, so it is reported as not checked."""
        site = self.site()
        self.edit(site, ABOUT, base.SHARE, 'og:image" content="/images/share.png"')
        self.expect(site, [("SEO016", "info", ABOUT)], 0)


# ================================================================ structured data
class TestStructuredData(ExtraCase):
    def test_type_list_with_one_medical_member(self):
        """SEO043 once (not SEO042) for `["Article", "MedicalWebPage"]`: Article is allowed, the other is medical."""
        site = self.site()
        self.edit(site, NOTES, '"@type": "Article"', '"@type": ["Article", "MedicalWebPage"]')
        self.expect(site, [("SEO043", "warn", NOTES)], 0)

    def test_graph_members_need_no_context(self):
        """Checks: SEO041 is about top-level objects only; members of `@graph` normally carry no @context."""
        site = self.site()
        self.edit(site, INDEX, '{"@context": "https://schema.org", "@type": "WebSite", "name": "Example Lab", "url": "https://example.test/"}',
                  '{"@context": "https://schema.org", "@graph": [{"@type": "WebSite", "name": "Example Lab"}, '
                  '{"@type": "Organization", "name": "Example Lab"}]}')
        self.expect(site, [], 0)

    def test_graph_inside_a_top_level_list(self):
        """Checks: typed objects include the @graph members of every top-level object, also when the JSON is a list."""
        site = self.site()
        self.edit(site, NOTES, NOTES_LD, '[{"@context": "https://schema.org", "@graph": [{"@type": "Recipe"}]}]')
        self.expect(site, [("SEO042", "warn", NOTES)], 0)

    def test_raw_control_character_is_invalid_json(self):
        """SEO040: a raw tab inside a JSON string is invalid JSON; the checker must parse the block as written."""
        site = self.site()
        self.edit(site, NOTES, '"headline": "Reading a registry report before quoting a number"',
                  '"headline": "Reading a registry report\tbefore quoting a number"')
        self.expect(site, [("SEO040", "error", NOTES)], 1)


# ================================================================ sitemap
class TestSitemapExtra(ExtraCase):
    def test_whitespace_wrapped_loc(self):
        """SEO021 (loc stripped): a `<loc>` wrapped in newlines and spaces still matches."""
        site = self.site()
        self.edit(site, "sitemap.xml", "<loc>https://example.test/notes/</loc>", "<loc>\n    https://example.test/notes/\n  </loc>")
        self.expect(site, [], 0)

    def test_empty_but_well_formed_sitemap(self):
        """SEO022: a well-formed sitemap with no <url> leaves every indexed page without a <loc>."""
        site = self.site()
        (site / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n'
                                          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"></urlset>\n',
                                          encoding="utf-8")
        self.expect(site, [("SEO022", "error", "sitemap.xml")] * 3, 1)

    def test_lastmod_relative_to_today(self):
        """SEO023 uses the local date: tomorrow is a warning, today is not. Computed at test time, so clock-proof."""
        today = datetime.date.today()
        for day, expected in ((today + datetime.timedelta(days=1), [("SEO023", "warn", "sitemap.xml")]), (today, [])):
            with self.subTest(day=day.isoformat()):
                site = self.site()
                self.edit(site, "sitemap.xml", "<loc>https://example.test/notes/</loc><lastmod>2026-10-01</lastmod>",
                          f"<loc>https://example.test/notes/</loc><lastmod>{day.isoformat()}</lastmod>")
                self.expect(site, expected, 0)

    def test_lastmod_impossible_date(self):
        """SEO023: 2026-02-30 is not a valid calendar date."""
        site = self.site()
        self.edit(site, "sitemap.xml", "<loc>https://example.test/notes/</loc><lastmod>2026-10-01</lastmod>",
                  "<loc>https://example.test/notes/</loc><lastmod>2026-02-30</lastmod>")
        self.expect(site, [("SEO023", "warn", "sitemap.xml")], 0)


# ================================================================ robots.txt
class TestRobotsExtra(ExtraCase):
    def write_robots(self, site, body):
        (site / "robots.txt").write_text(body + "\nSitemap: https://example.test/sitemap.xml\n", encoding="utf-8")

    def test_consecutive_user_agent_lines_form_one_group(self):
        """SEO026: `User-agent: *` followed by another User-agent line starts one group that includes `*`."""
        site = self.site()
        self.write_robots(site, "User-agent: *\nUser-agent: examplebot\nDisallow: /notes/\n")
        self.expect(site, [("SEO026", "error", "robots.txt")], 1)

    def test_star_listed_second_in_a_group(self):
        """SEO026: the same group with `*` listed second."""
        site = self.site()
        self.write_robots(site, "User-agent: examplebot\nUser-agent: *\nDisallow: /notes/\n")
        self.expect(site, [("SEO026", "error", "robots.txt")], 1)

    def test_rules_of_another_group_do_not_count(self):
        """SEO026 is only for the `*` group: a Disallow in a group for another agent is not reported."""
        site = self.site()
        self.write_robots(site, "User-agent: examplebot\nDisallow: /notes/\n\nUser-agent: *\nDisallow:\n")
        self.expect(site, [], 0)

    def test_anchored_wildcard_pattern(self):
        """SEO026: `/*/$` uses both `*` and the `$` anchor; it matches `/about/` and `/notes/` (one finding)."""
        site = self.site()
        self.write_robots(site, "User-agent: *\nDisallow: /*/$\n")
        data = self.expect(site, [("SEO026", "error", "robots.txt")], 1)
        self.assertIn("/*/$", data["findings"][0]["message"])

    def test_anchor_does_not_match_a_longer_path(self):
        """SEO026: `/about$` is anchored, so it does not block `/about/`."""
        site = self.site()
        self.write_robots(site, "User-agent: *\nDisallow: /about$\n")
        self.expect(site, [], 0)

    def test_same_pattern_in_two_star_groups_is_one_finding(self):
        """SEO026: one finding per matching pattern, even when the pattern is written twice."""
        site = self.site()
        self.write_robots(site, "User-agent: *\nDisallow: /notes/\n\nUser-agent: *\nDisallow: /notes/\n")
        self.expect(site, [("SEO026", "error", "robots.txt")], 1)


# ================================================================ what the script may do
WRAPPER = r"""
import os, runpy, sys
sys.dont_write_bytecode = True
WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC
BLOCKED = ("socket.", "subprocess.", "os.system", "os.exec", "os.spawn", "os.posix_spawn", "os.startfile",
           "os.remove", "os.rename", "os.rmdir", "os.mkdir", "shutil.", "ctypes.", "urllib.Request", "webbrowser")
writes = []
def hook(event, args):
    if event.startswith(BLOCKED):
        os.write(2, ("BLOCKED " + event + "\n").encode())
        os._exit(97)
    if event == "open":
        path, mode, flags = (tuple(args) + (None, None, None))[:3]
        if (isinstance(mode, str) and any(c in mode for c in "wax+")) or (mode is None and isinstance(flags, int) and flags & WRITE_FLAGS):
            writes.append(str(path))
            os.write(2, ("WRITE " + str(path) + "\n").encode())
sys.addaudithook(hook)
script = sys.argv[1]
sys.argv = sys.argv[1:]
runpy.run_path(script, run_name="__main__")
"""


class TestSideEffects(ExtraCase):
    def run_hooked(self, *args):
        p = subprocess.run([sys.executable, "-B", "-c", WRAPPER, CANDIDATE] + [str(a) for a in args],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=TIMEOUT)
        return p.returncode, p.stdout, p.stderr

    def test_no_network_process_or_write_at_run_time(self):
        """Interface: an audit hook sees no socket, subprocess, file deletion or file write during a whole run."""
        site = self.site()
        self.edit(site, ABOUT, NOTES_LINK, '<a href="/notes/">click here</a>')
        for extra in ([], ["--json"], ["--strict"]):
            rc, out, err = self.run_hooked(site, "--base-url", BASE, *extra)
            self.assertNotIn("BLOCKED", err)
            self.assertNotIn("WRITE", err)
            self.assertIn(rc, (0, 1), err[-300:])

    def test_json_out_is_the_only_write(self):
        """Interface: with --json-out the only file opened for writing is that path."""
        site = self.site()
        target = Path(tempfile.mkdtemp(prefix="seo-out-")) / "report.json"
        self.addCleanup(lambda: target.unlink() if target.exists() else None)
        rc, out, err = self.run_hooked(site, "--base-url", BASE, "--json-out", target)
        writes = [ln[len("WRITE "):] for ln in err.splitlines() if ln.startswith("WRITE ")]
        self.assertNotIn("BLOCKED", err)
        self.assertEqual([Path(w).resolve() for w in writes], [target.resolve()], err[-300:])
        self.assertEqual(rc, 0)

    def test_source_avoids_process_and_code_execution_calls(self):
        """Interface: the source calls nothing that runs a process or code, or deletes files."""
        src = Path(CANDIDATE).read_text(encoding="utf-8")
        for name in ("os.system", "os.popen", "os.exec", "os.spawn", "__import__", "importlib", "pickle", "marshal",
                     "ctypes", "shutil", "os.remove", "unlink(", "rmtree"):
            self.assertNotIn(name, src)
        self.assertIsNone(re.search(r"(?<![\w.])compile\s*\(", src), "builtin compile() is not needed")

    def test_source_is_python_3_9_syntax(self):
        """Requirements: Python 3.9+. No match statement, no runtime `X | Y` unions, no newer str/zip/int methods."""
        src = Path(CANDIDATE).read_text(encoding="utf-8")
        tree = ast.parse(src, feature_version=(3, 9))
        for node in ast.walk(tree):
            self.assertFalse(type(node).__name__ in ("Match", "TryStar", "TypeAlias"), type(node).__name__)
            ann = getattr(node, "annotation", None) or getattr(node, "returns", None)
            if ann is not None:
                self.assertFalse(any(isinstance(n, ast.BinOp) and isinstance(n.op, ast.BitOr) for n in ast.walk(ann)),
                                 "a `X | Y` annotation is evaluated at run time on 3.9")
        # removeprefix/removesuffix arrived in 3.9.0 itself; they are kept out so the file also reads on older tools.
        for name in ("removeprefix", "removesuffix", "strict=True", "bit_count", "pairwise", "aiter("):
            self.assertNotIn(name, src, f"{name} is new or version-sensitive")
        self.assertIsNone(re.search(r"isinstance\([^)]*\|", src), "isinstance with `X | Y` needs 3.10")


if __name__ == "__main__":
    unittest.main()
