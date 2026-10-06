#!/usr/bin/env python3
"""seo_audit.py: audit a folder of static HTML for search and link-preview basics.

Standard library only, Python 3.9+. Reads files; opens no network connection, runs nothing from a page, and
writes nothing unless --json-out is given. Usage: python seo_audit.py SITE_DIR [--base-url URL] [--json]
[--strict] [--json-out PATH]. See the skill's references/checklist.md for what each finding ID means.
"""
import argparse
import json
import re
import struct
import sys
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

VERSION = 1


class Node:
    __slots__ = ("tag", "attrs", "children", "parent")

    def __init__(self, tag, attrs=None, parent=None):
        self.tag = tag
        self.attrs = {}
        for k, v in attrs or []:
            if k not in self.attrs:  # as in browsers, the first of two equal attribute names wins
                self.attrs[k] = v
        self.children = []
        self.parent = parent

    def walk(self, skip=()):
        """Yield every descendant (Node or text) in document order, without recursion (deep pages are common)."""
        stack = [iter(self.children)]
        while stack:
            c = next(stack[-1], None)
            if c is None:
                stack.pop()
                continue
            yield c
            if not isinstance(c, str) and c.tag not in skip:
                stack.append(iter(c.children))

    def text(self, skip=()):
        return "".join(c for c in self.walk(skip) if isinstance(c, str))

    def find_all(self, tag):
        return [c for c in self.walk() if not isinstance(c, str) and c.tag == tag]


VOID = {"meta", "link", "img", "br", "input", "hr", "source"}


class TreeParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("root")
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        n = Node(tag, attrs, self.stack[-1])
        self.stack[-1].children.append(n)
        if tag not in VOID:
            self.stack.append(n)

    def handle_startendtag(self, tag, attrs):
        # spec: treat it as a start tag, as browsers do (`<div/>` opens a div; `<meta ... />` is void anyway)
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def norm(s):
    return re.sub(r"\s+", " ", s or "").strip()


def is_indexed(meta_robots_content):
    if meta_robots_content is None:
        return True
    for part in meta_robots_content.split(","):
        if part.strip().lower() == "noindex":
            return False
    return True


def get_first(root, tag, name=None, value=None, prop=None):
    for n in root.find_all(tag):
        a = n.attrs
        ok = True
        if name is not None and a.get("name") != name:
            ok = False
        if value is not None and a.get(name) != value:
            ok = False
        if prop is not None and a.get("property") != prop:
            ok = False
        if ok:
            return n
    return None


def address_of(path):
    """'index.html' -> '', 'dir/index.html' -> 'dir/', any other 'x.html' stays 'x.html'."""
    p = path.replace("\\", "/")
    if p == "index.html":
        return ""
    if p.endswith("/index.html"):
        return p[: -len("index.html")]
    return p


def page_dir_of(path):
    """The page's folder relative to SITE_DIR, posix ('' at the root)."""
    return path.rpartition("/")[0]


def url_path_of(path):
    addr = address_of(path)
    return "/" + addr if addr else "/"


def resolve_site_file(href, page_dir, base_url):
    """Return the site file an href names, as a posix path relative to SITE_DIR, or None.

    `page_dir` is the page's own folder relative to SITE_DIR ('' at the root). Query and fragment are dropped.
    An absolute URL is a site file only when it starts with the base (the remainder is the path) or when there
    is no base (its URL path is used). A path that climbs out of SITE_DIR is not a site file.
    """
    if href is None:
        return None
    h = href.strip()
    if not h:
        return None
    sp = urlsplit(h)
    scheme = sp.scheme.lower()
    if scheme in ("http", "https") or (scheme == "" and h.startswith("//")):
        if base_url:
            full = h if scheme else urlsplit(base_url).scheme + ":" + h
            if not full.startswith(base_url):
                return None
            rel = urlsplit(full[len(base_url):]).path
        else:
            rel = sp.path.lstrip("/")
    elif scheme == "":
        if sp.path.startswith("/"):
            rel = sp.path.lstrip("/")
        else:
            rel = (page_dir + "/" if page_dir else "") + sp.path
    else:
        return None
    parts = []
    for seg in unquote(rel).replace("\\", "/").split("/"):
        if seg in ("", "."):
            continue
        if seg == "..":
            if not parts:
                return None  # climbs out of SITE_DIR
            parts.pop()
        else:
            parts.append(seg)
    return "/".join(parts)


def host_of(href):
    if href is None:
        return None
    sp = urlsplit(href.strip())
    if sp.scheme in ("http", "https"):
        return (sp.netloc or "").lower()
    if sp.scheme == "" and href.strip().startswith("//"):
        return (urlsplit(href).netloc or "").lower()
    return None


def png_dims(path):
    try:
        with open(path, "rb") as f:
            data = f.read(24)
    except Exception:
        return None
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    w = struct.unpack(">I", data[16:20])[0]
    h = struct.unpack(">I", data[20:24])[0]
    return (w, h)


def visible_text(root):
    text = norm(root.text(skip=("script", "style", "template", "noscript")))
    titles = [norm(t.text()) for t in root.find_all("title")]
    if titles:
        text = (text + " " + titles[0]).strip()
    return text


def accessible_name(a):
    parts = []
    parts.append(norm(a.text()))
    for img in a.find_all("img"):
        alt = img.attrs.get("alt")
        if alt is not None:
            parts.append(alt)
    aria = a.attrs.get("aria-label")
    if aria is not None:
        parts.append(aria)
    return norm(" ".join(p for p in parts if p))


def link_rel_tokens(a):
    rel = a.attrs.get("rel")
    if rel is None:
        return set()
    return {t.strip().lower() for t in rel.split()}


def check_metadata(page, pages_data, indexed, base_url, findings):
    path = page["path"]
    root = page["root"]
    addr = address_of(path)
    url_path = url_path_of(path)
    expected = (base_url + addr) if base_url else None

    # title
    titles = root.find_all("title")
    title_text = norm(titles[0].text()) if titles else ""
    has_title = bool(title_text)
    if not has_title:
        findings.append(("SEO001", "error", path, "no <title> or empty title text"))
    else:
        L = len(title_text)
        if not (20 <= L <= 70):
            findings.append(("SEO002", "warn", path, f"title length {L} not in 20..70"))

    # description
    mdesc = get_first(root, "meta", name="description")
    desc_text = norm(mdesc.attrs.get("content", "")) if mdesc else ""
    has_desc = bool(desc_text)
    if not has_desc:
        findings.append(("SEO004", "error", path, "no <meta name=\"description\"> or empty content"))
    else:
        L = len(desc_text)
        if not (60 <= L <= 160):
            findings.append(("SEO005", "warn", path, f"description length {L} not in 60..160"))

    # canonical
    links = [l for l in root.find_all("link") if "canonical" in link_rel_tokens(l)]
    canon = None
    if links:
        canon = (links[0].attrs.get("href") or "").strip()
    has_canon = bool(canon)
    if not has_canon:
        findings.append(("SEO007", "error", path, "no canonical link or empty href"))
    else:
        sp = urlsplit(canon)
        is_abs = sp.scheme in ("http", "https")
        if is_abs and base_url:
            if canon != expected:
                findings.append(("SEO008", "error", path, f"canonical is {canon} but the page's address is {expected}"))
        else:
            if sp.path != url_path:
                findings.append(("SEO008", "error", path, f"canonical path {sp.path} differs from URL path {url_path}"))
        if not (canon.startswith("http://") or canon.startswith("https://")):
            findings.append(("SEO009", "error", path, f"canonical {canon} is not an absolute http(s) URL"))

    # og tags
    def og(prop):
        n = get_first(root, "meta", prop=prop)
        if n is None:
            return None
        v = n.attrs.get("content")
        return (v or "").strip()

    if has_title:
        ot = og("og:title")
        if ot is None or norm(ot) != title_text:
            findings.append(("SEO010", "error", path, f"og:title missing or differs from title"))
    if has_desc:
        od = og("og:description")
        if od is None or norm(od) != desc_text:
            findings.append(("SEO011", "error", path, f"og:description missing or differs from description"))
    if has_canon:
        ou = og("og:url")
        if ou is None or ou.strip() != canon.strip():
            findings.append(("SEO012", "error", path, f"og:url missing or differs from canonical"))

    # og:image
    oi = og("og:image")
    if oi is None:
        findings.append(("SEO013", "info", path, "no og:image"))
    else:
        sp = urlsplit(oi)
        is_abs = sp.scheme in ("http", "https")
        sf = resolve_site_file(oi, page_dir_of(path), base_url) if is_abs else None
        if not is_abs:
            findings.append(("SEO016", "info", path, f"og:image {oi} is not an absolute http(s) URL; not checked"))
        elif sf is None:
            findings.append(("SEO016", "info", path, f"og:image {oi} is not on this site; not checked"))
        else:
            full = Path(page["site_dir"]) / sf
            if not full.is_file():
                findings.append(("SEO014", "error", path, f"og:image site file for {oi} does not exist"))
            else:
                dims = png_dims(str(full))
                if dims is None:
                    findings.append(("SEO016", "info", path, f"og:image {sf} is not a PNG; not checked"))
                else:
                    w, h = dims
                    if (w, h) != (1200, 630):
                        findings.append(("SEO015", "warn", path, f"og:image dimensions {w}x{h} differ from 1200x630"))


def check_content(page, base_url, findings):
    path = page["path"]
    root = page["root"]

    # headings
    hs = [n for n in root.find_all("h1")]
    if len(hs) == 0:
        findings.append(("SEO030", "error", path, "no <h1>"))
    elif len(hs) > 1:
        findings.append(("SEO031", "warn", path, f"{len(hs)} <h1> elements"))

    # heading order: walk h1..h6 in document order
    levels = [int(c.tag[1]) for c in root.walk()
              if not isinstance(c, str) and c.tag in ("h1", "h2", "h3", "h4", "h5", "h6")]
    prev = None
    for lv in levels:
        if prev is not None and lv - prev > 1:
            findings.append(("SEO032", "warn", path, f"heading level jumps from h{prev} to h{lv}"))
        prev = lv

    # images (one finding per image; the message names its src)
    imgs = root.find_all("img")
    for im in imgs:
        src = im.attrs.get("src") or ""
        if "alt" not in im.attrs:
            findings.append(("SEO033", "error", path, f"<img src={src!r}> missing alt attribute"))
        if ("width" not in im.attrs) or ("height" not in im.attrs):
            findings.append(("SEO034", "warn", path, f"<img src={src!r}> missing width or height"))

    # links
    bad_words = {"click here", "here", "read more", "more", "link", "this",
                 "this page", "learn more", "open", "continue", "details", "go"}
    for a in root.find_all("a"):
        if "href" not in a.attrs:
            continue
        name = accessible_name(a)
        low = name.lower().rstrip(".,:;!")
        if not name:
            findings.append(("SEO036", "error", path, f"link with empty accessible name (href={a.attrs.get('href')})"))
        elif low in bad_words:
            findings.append(("SEO035", "warn", path, f"link text '{name}' is generic"))

    # module preload
    has_module_script = any(
        s.attrs.get("type") and s.attrs["type"].strip().lower() == "module" and "src" in s.attrs
        for s in root.find_all("script")
    )
    if has_module_script:
        has_mp = any("modulepreload" in link_rel_tokens(l) for l in root.find_all("link"))
        if not has_mp:
            findings.append(("SEO037", "info", path, "module script without modulepreload link"))

    # font preload
    ss_links = [l for l in root.find_all("link") if "stylesheet" in link_rel_tokens(l)]
    has_font_preload = any(
        "preload" in link_rel_tokens(l) and (l.attrs.get("as") or "").lower() == "font"
        for l in root.find_all("link")
    )
    if ss_links and not has_font_preload:
        page_dir = page_dir_of(path)
        for l in ss_links:
            href = l.attrs.get("href")
            sf = resolve_site_file(href, page_dir, base_url)
            if sf is None:
                continue
            full = Path(page["site_dir"]) / sf
            if not full.is_file():
                continue
            try:
                with open(full, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
            except Exception:
                continue
            if "@font-face" in content:
                findings.append(("SEO038", "info", path, f"stylesheet {sf} has @font-face but no font preload"))
                break

    # JSON-LD
    block = 0
    for s in root.find_all("script"):
        t = (s.attrs.get("type") or "").strip().lower()
        if t != "application/ld+json":
            continue
        block += 1
        content = s.text()  # parsed as written: normalising first would hide raw control characters
        try:
            data = json.loads(content)
        except Exception:
            findings.append(("SEO040", "error", path, f"JSON-LD block {block} is not valid JSON"))
            continue
        allowlist = {"WebSite", "WebPage", "AboutPage", "CollectionPage", "ContactPage",
                     "Article", "BlogPosting", "NewsArticle", "ScholarlyArticle",
                     "TechArticle", "CreativeWork", "Dataset", "SoftwareSourceCode",
                     "SoftwareApplication", "Organization", "Person", "BreadcrumbList",
                     "ListItem", "ImageObject", "FAQPage", "Question", "Answer"}
        medical = {"Drug", "Physician", "Hospital", "Patient", "DietarySupplement"}

        vtext = visible_text(root).lower()

        def check_obj(obj, top_level):
            if not isinstance(obj, dict):
                return
            if top_level and "@context" not in obj:  # @graph members normally carry no @context
                findings.append(("SEO041", "warn", path, f"JSON-LD block {block}: top-level object missing @context"))
            tval = obj.get("@type")
            types = []
            if isinstance(tval, str):
                types = [tval]
            elif isinstance(tval, list):
                types = [x for x in tval if isinstance(x, str)]
            for ty in types:
                if ty.startswith("Medical") or ty in medical:
                    findings.append(("SEO043", "warn", path, f"JSON-LD @type '{ty}' is medical"))
                elif ty not in allowlist:
                    findings.append(("SEO042", "warn", path, f"JSON-LD @type '{ty}' not in allowlist"))
            for key in ("name", "headline"):
                if key in obj and isinstance(obj[key], str):
                    val = norm(obj[key]).lower()
                    if val and val not in vtext:
                        findings.append(("SEO044", "warn", path, f"JSON-LD {key} '{norm(obj[key])}' not found in visible text"))

        # typed objects: each top-level object (the JSON itself, or each element of a list) and its @graph members
        for top in (data if isinstance(data, list) else [data]):
            check_obj(top, True)
            graph = top.get("@graph") if isinstance(top, dict) else None
            if isinstance(graph, list):
                for el in graph:
                    check_obj(el, False)

    # external scripts
    base_host = urlsplit(base_url).netloc.lower() if base_url else None
    for s in root.find_all("script"):
        src = s.attrs.get("src")
        t = (s.attrs.get("type") or "").strip().lower()
        if src:
            sp = urlsplit(src)
            if sp.scheme in ("http", "https") or src.startswith("//"):
                h = host_of(src)
                if base_url is None:
                    findings.append(("SEO050", "warn", path, f"external script {src}"))
                elif h != base_host:
                    findings.append(("SEO050", "warn", path, f"external script {src} on another host"))
        else:
            if t == "" or t != "application/ld+json":
                findings.append(("SEO051", "info", path, f"inline <script> without src: {norm(s.text())[:60]}"))

    # external links
    for l in root.find_all("link"):
        href = l.attrs.get("href")
        if not href:
            continue
        sp = urlsplit(href)
        if sp.scheme not in ("http", "https") and not href.startswith("//"):
            continue
        h = host_of(href)
        rels = link_rel_tokens(l)
        interesting = {"stylesheet", "preload", "modulepreload", "preconnect", "dns-prefetch", "icon"}
        if not (rels & interesting):
            continue
        if base_url is None:
            findings.append(("SEO052", "info", path, f"external link {href}"))
        elif h != base_host:
            findings.append(("SEO052", "info", path, f"external link {href} on another host"))


def check_site(site_dir, pages_data, indexed, base_url, findings):
    # 404
    if "404.html" not in pages_data:
        findings.append(("SEO018", "info", "404.html", "no 404.html at the root"))
    else:
        meta_robots = None
        for n in pages_data["404.html"]["root"].find_all("meta"):
            if n.attrs.get("name") == "robots":
                meta_robots = n.attrs.get("content")
                break
        if is_indexed(meta_robots):
            findings.append(("SEO017", "error", "404.html", "404.html is not noindex"))
        has_canon = any("canonical" in link_rel_tokens(l) for l in pages_data["404.html"]["root"].find_all("link"))
        if has_canon:
            findings.append(("SEO019", "error", "404.html", "404.html has a canonical link"))

    # sitemap
    smap = Path(site_dir) / "sitemap.xml"
    locs = []
    lastmods = []
    sitemap_sound = False
    if not smap.is_file():
        findings.append(("SEO020", "error", "sitemap.xml", "sitemap.xml missing at the root"))
    else:
        try:
            import xml.etree.ElementTree as ET
            tree = ET.parse(str(smap))
            for el in tree.iter():
                ln = el.tag.rsplit("}", 1)[-1]
                if ln == "loc":
                    locs.append((el.text or "").strip())
                elif ln == "lastmod":
                    lastmods.append((el.text or "").strip())
            sitemap_sound = True
        except Exception:
            findings.append(("SEO020", "error", "sitemap.xml", "sitemap.xml is not well-formed XML"))

    if sitemap_sound:  # a sound sitemap with no <loc> still leaves every indexed page unlisted (SEO022)
        indexed_urls = set()
        for p in indexed:
            addr = address_of(p)
            if base_url:
                indexed_urls.add(base_url + addr)
            else:
                indexed_urls.add(url_path_of(p))
        for loc in locs:
            sp = urlsplit(loc)
            if base_url:
                ok = loc in indexed_urls
            else:
                ok = sp.path in indexed_urls
            if not ok:
                findings.append(("SEO021", "error", "sitemap.xml", f"loc {loc} is not an indexed page"))
        for p in indexed:
            addr = address_of(p)
            up = url_path_of(p)
            matched = False
            for loc in locs:
                sp = urlsplit(loc)
                if base_url:
                    if loc == base_url + addr:
                        matched = True
                        break
                else:
                    if sp.path == up:
                        matched = True
                        break
            if not matched:
                findings.append(("SEO022", "error", "sitemap.xml", f"indexed page {up} has no loc"))

        today = date.today()
        for lm in lastmods:
            m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", lm)
            if not m:
                findings.append(("SEO023", "warn", "sitemap.xml", f"lastmod {lm} is not a valid YYYY-MM-DD date"))
                continue
            try:
                y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
                dt = date(y, mo, d)
            except ValueError:
                findings.append(("SEO023", "warn", "sitemap.xml", f"lastmod {lm} is not a valid YYYY-MM-DD date"))
                continue
            if dt > today:
                findings.append(("SEO023", "warn", "sitemap.xml", f"lastmod {lm} is after today"))

    # robots
    rob = Path(site_dir) / "robots.txt"
    if not rob.is_file():
        findings.append(("SEO024", "error", "robots.txt", "robots.txt missing at the root"))
    else:
        try:
            with open(rob, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except Exception:
            lines = []
        has_sitemap = False
        sitemap_ok = False
        star_disallows = []
        in_star = False
        prev_was_agent = False  # consecutive User-agent lines open one group (RFC 9309)
        for raw in lines:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            # strip comment after #
            idx = line.find("#")
            if idx != -1:
                line = line[:idx].strip()
            if ":" not in line:
                continue
            key, _, val = line.partition(":")
            key = key.strip().lower()
            val = val.strip()
            if key == "user-agent":
                in_star = (in_star and prev_was_agent) or val.lower() == "*"
                prev_was_agent = True
                continue
            prev_was_agent = False
            if key == "sitemap":
                has_sitemap = True
                if base_url and val == base_url + "sitemap.xml":
                    sitemap_ok = True
            elif key == "disallow" and in_star and val and val not in star_disallows:
                star_disallows.append(val)  # one finding per pattern, even if written twice

        if not has_sitemap or (base_url and not sitemap_ok):
            findings.append(("SEO025", "warn", "robots.txt", "no Sitemap line pointing to base + sitemap.xml"))

        indexed_paths = [url_path_of(p) for p in indexed]
        for pat in star_disallows:
            anchor = pat.endswith("$")
            p = pat[:-1] if anchor else pat
            # `*` matches any run of characters; a trailing `$` anchors the end; otherwise a prefix match
            regex = ".*".join(re.escape(part) for part in p.split("*")) + ("$" if anchor else "")
            matched = any(re.match(regex, ip) for ip in indexed_paths)
            if matched:
                findings.append(("SEO026", "error", "robots.txt", f"Disallow pattern '{pat}' matches an indexed page"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("site_dir")
    ap.add_argument("--base-url", default=None)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--json-out", default=None)

    # page paths, titles and link text may be any Unicode; a legacy console code page must not crash the run
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace", newline="\n")
        except (AttributeError, ValueError):
            pass

    try:
        args = ap.parse_args()
    except SystemExit as e:
        if e.code == 0:  # --help
            raise
        sys.stderr.write("usage error\n")
        sys.exit(2)

    site_dir = Path(args.site_dir)
    if not site_dir.is_dir():
        sys.stderr.write(f"SITE_DIR is not a directory: {site_dir}\n")
        sys.exit(2)

    base_url = args.base_url
    if base_url and not base_url.endswith("/"):
        base_url += "/"

    # pages are files only: a folder that happens to be called `x.html` is not a page
    html_files = sorted(f for f in site_dir.rglob("*.html") if f.is_file())
    if not html_files:
        sys.stderr.write("no .html files found in SITE_DIR\n")
        sys.exit(2)

    pages_data = {}
    for f in html_files:
        rel = f.relative_to(site_dir).as_posix()
        raw = f.read_bytes()
        try:
            text = raw.decode("utf-8")
            utf8_ok = True
        except UnicodeDecodeError:
            text = raw.decode("utf-8", errors="replace")
            utf8_ok = False
        parser = TreeParser()
        try:
            parser.feed(text)
            parser.close()
        except Exception:
            pass
        pages_data[rel] = {
            "path": rel,
            "root": parser.root,
            "site_dir": str(site_dir),
            "utf8_ok": utf8_ok,
        }

    findings = []

    # 404 detection
    is_404 = lambda p: (p == "404.html")

    def robots_content(p):
        for n in p["root"].find_all("meta"):
            if n.attrs.get("name") == "robots":
                return n.attrs.get("content")
        return None

    indexed = []
    for rel, pd in pages_data.items():
        if not pd["utf8_ok"]:  # every page, the 404 included
            findings.append(("SEO091", "warn", rel, "file is not valid UTF-8"))
        if is_404(rel):
            continue
        if is_indexed(robots_content(pd)):
            indexed.append(rel)

    for rel in sorted(pages_data):
        pd = pages_data[rel]
        if rel in indexed:  # metadata checks: indexed pages only (never the 404 page)
            check_metadata(pd, pages_data, indexed, base_url, findings)
        check_content(pd, base_url, findings)  # content checks: every page, the 404 included

    check_site(site_dir, pages_data, indexed, base_url, findings)

    # duplicate title/desc across indexed pages
    if len(indexed) > 1:
        titles = {}
        descs = {}
        for rel in indexed:
            pd = pages_data[rel]
            ts = pd["root"].find_all("title")
            t = norm(ts[0].text()) if ts else ""
            if t:
                titles.setdefault(t, []).append(rel)
            md = get_first(pd["root"], "meta", name="description")
            d = norm(md.attrs.get("content", "")) if md else ""
            if d:
                descs.setdefault(d, []).append(rel)
        for t, pages_ in titles.items():
            if len(pages_) > 1:
                for p in pages_:
                    findings.append(("SEO003", "error", p, f"duplicate title '{t}'"))
        for d, pages_ in descs.items():
            if len(pages_) > 1:
                for p in pages_:
                    findings.append(("SEO006", "error", p, f"duplicate description '{d}'"))

    # sort; no de-duplication, because the spec asks for one finding per image, script, link or jump
    uniq = sorted(findings, key=lambda x: (x[2], x[0], x[3]))

    counts = {"error": 0, "warn": 0, "info": 0}
    for _, sev, _, _ in uniq:
        counts[sev] += 1

    doc = {
        "version": VERSION,
        "base_url": base_url,
        "pages": sorted(pages_data.keys()),
        "indexed_pages": sorted(indexed),
        "findings": [{"id": i, "severity": s, "page": p, "message": m} for (i, s, p, m) in uniq],
        "counts": counts,
    }

    if args.json:
        out = json.dumps(doc, indent=2, sort_keys=True) + "\n"
        sys.stdout.write(out)
    else:
        for i, s, p, m in uniq:
            sys.stdout.write(f"{i} {s} {p}: {m}\n")
        n_err = counts["error"]
        n_warn = counts["warn"]
        n_info = counts["info"]
        npages = len(doc["pages"])
        nidx = len(indexed)
        sys.stdout.write(f"{n_err} errors, {n_warn} warnings, {n_info} info in {npages} pages ({nidx} indexed)\n")

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(doc, indent=2, sort_keys=True) + "\n")

    has_error = counts["error"] > 0
    has_warn = counts["warn"] > 0
    if args.strict and (has_error or has_warn):
        sys.exit(1)
    elif has_error:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
