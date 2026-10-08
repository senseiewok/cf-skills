"""Tests for the paste-ready versions of skills (references/paste-ready.md).

A paste-ready file lets a person use a skill in any chat assistant with no install, no scripts and no repository:
they copy one block into their tool's instructions area (if it has one) or into the first message of a new chat.
Each file holds three blocks, in this order, each between the markers below: SHORT (at most 1,200 characters),
STANDARD (at most 4,000) and FULL (no limit, plain text). Every block must:

- contain "care team" and "not medical advice";
- ask the person not to share names, dates of birth or record numbers;
- contain no script or file path, no angle bracket, no URL and no phone number;
- contain no table, no code fence and no Markdown heading or bold marker (it is pasted into a chat box).

The file must also have a "How to use this" part and a "Try it" part.
The checks are mechanical: they do not decide whether a block is safe or well written. A person reads each block.
Standard library only; also runs under pytest.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / ".claude" / "skills"
REQUIRED = ["cf-ai-safe-use", "cf-plain-language-rewrite", "cf-visit-prep", "cf-answer-check", "cf-ai-tool-review"]

START = "=== START: copy from here ==="
END = "=== END: copy to here ==="
NAMES = ("SHORT", "STANDARD", "FULL")
LIMITS = {"SHORT": 1200, "STANDARD": 4000}

PATH_RE = re.compile(r"\b(?:scripts|references|evals|tests|assets)/|\b[\w-]+\.(?:py|md|json|txt|csv|ya?ml|sh|ps1|html)\b"
                     r"|[A-Za-z]:\\|(?:^|\s)\.{0,2}/[\w.-]+/", re.I)
URL_RE = re.compile(r"https?://|\bwww\.|\b[\w-]+\.(?:com|org|gov|net|edu|uk|info|io)\b", re.I)
PHONE_RE = re.compile(r"(?:\+?\d[\s().-]*){7,}")
HEADING_RE = re.compile(r"^#+ .*?\b(SHORT|STANDARD|FULL)\b", re.M)
TABLE_RE = re.compile(r"^\s*\|.*\|\s*$|^\s*\|?\s*:?-{3,}:?\s*\|", re.M)


def parse_blocks(text):
    """Return a list of (name, body) for each START/END block. name is the SHORT, STANDARD or FULL word in the last
    Markdown heading above START (for example '## STANDARD block')."""
    blocks = []
    pos = 0
    while True:
        s = text.find(START, pos)
        if s == -1:
            break
        e = text.find(END, s)
        if e == -1:
            raise ValueError("a START marker has no END marker")
        headings = HEADING_RE.findall(text[:s])
        body = text[s + len(START):e].strip("\n")
        blocks.append((headings[-1] if headings else "?", body))
        pos = e + len(END)
    if text.count(END) != text.count(START):
        raise ValueError("START and END markers are not paired")
    return blocks


def block_problems(name, body):
    """Return a list of problems with one block. An empty list means it passes."""
    problems = []
    low = body.lower()
    limit = LIMITS.get(name)
    if limit is not None and len(body) > limit:
        problems.append(f"{name} has {len(body)} characters; the limit is {limit}")
    if not body.strip():
        problems.append(f"{name} is empty")
    if "care team" not in low:
        problems.append(f"{name} does not contain 'care team'")
    if "not medical advice" not in low:
        problems.append(f"{name} does not contain 'not medical advice'")
    for words in ("names", "dates of birth", "record numbers"):
        if words not in low:
            problems.append(f"{name} does not ask the person not to share {words}")
    if "<" in body or ">" in body:
        problems.append(f"{name} contains an angle bracket")
    if PATH_RE.search(body):
        problems.append(f"{name} contains a script or file path: {PATH_RE.search(body).group(0)!r}")
    if URL_RE.search(body):
        problems.append(f"{name} contains a URL: {URL_RE.search(body).group(0)!r}")
    if PHONE_RE.search(body):
        problems.append(f"{name} contains something like a phone number: {PHONE_RE.search(body).group(0)!r}")
    if "```" in body or "~~~" in body:
        problems.append(f"{name} contains a code fence")
    if TABLE_RE.search(body):
        problems.append(f"{name} contains a table")
    if re.search(r"^\s*#", body, re.M) or "**" in body or "__" in body:
        problems.append(f"{name} contains Markdown that needs rendering (a heading or bold)")
    return problems


def file_problems(text):
    problems = []
    try:
        blocks = parse_blocks(text)
    except ValueError as exc:
        return [str(exc)]
    if [b[0] for b in blocks] != list(NAMES):
        problems.append(f"expected blocks {list(NAMES)} in order, found {[b[0] for b in blocks]}")
    for name, body in blocks:
        problems.extend(block_problems(name, body))
    if "how to use this" not in text.lower():
        problems.append("no 'How to use this' part")
    if "try it" not in text.lower():
        problems.append("no 'Try it' part")
    return problems


def paste_ready_files():
    return sorted(SKILLS.glob("*/references/paste-ready.md"))


class PasteReadyFiles(unittest.TestCase):
    def test_required_skills_have_a_paste_ready_file(self):
        for name in REQUIRED:
            with self.subTest(skill=name):
                self.assertTrue((SKILLS / name / "references" / "paste-ready.md").is_file())

    def test_every_paste_ready_file_passes(self):
        files = paste_ready_files()
        self.assertTrue(files, "no paste-ready files found; the check would be vacuous")
        for f in files:
            with self.subTest(file=f.parent.parent.name):
                self.assertEqual(file_problems(f.read_text(encoding="utf-8")), [])


GOOD_BODY = ("This is not medical advice. Do not share names, dates of birth or record numbers. "
             "Bring medical questions to the care team.")


def make_file(short=GOOD_BODY, standard=GOOD_BODY, full=GOOD_BODY):
    parts = ["How to use this: paste a block.", ""]
    for name, body in (("SHORT", short), ("STANDARD", standard), ("FULL", full)):
        parts += [f"## {name} block", START, body, END, ""]
    parts.append("Try it: ask a question.")
    return "\n".join(parts)


class NegativeControls(unittest.TestCase):
    """Each broken file must fail, so a check that stops working breaks the tests."""

    def test_good_synthetic_file_passes(self):
        self.assertEqual(file_problems(make_file()), [])

    def test_over_length_short_block_fails(self):
        self.assertTrue(any("limit is 1200" in p for p in file_problems(make_file(short=GOOD_BODY + " x" * 700))))

    def test_over_length_standard_block_fails(self):
        self.assertTrue(any("limit is 4000" in p for p in file_problems(make_file(standard=GOOD_BODY + " x" * 2100))))

    def test_block_missing_care_team_fails(self):
        body = GOOD_BODY.replace("care team", "clinic")
        self.assertTrue(any("'care team'" in p for p in file_problems(make_file(full=body))))

    def test_block_missing_not_medical_advice_fails(self):
        body = GOOD_BODY.replace("not medical advice", "general information")
        self.assertTrue(any("'not medical advice'" in p for p in file_problems(make_file(short=body))))

    def test_block_missing_identifier_warning_fails(self):
        body = GOOD_BODY.replace("dates of birth", "birthdays")
        self.assertTrue(any("dates of birth" in p for p in file_problems(make_file(standard=body))))

    def test_url_fails(self):
        self.assertTrue(any("URL" in p for p in file_problems(make_file(full=GOOD_BODY + " See example.org."))))

    def test_phone_fails(self):
        self.assertTrue(any("phone" in p for p in file_problems(make_file(full=GOOD_BODY + " Call 555 010 0199."))))

    def test_path_fails(self):
        self.assertTrue(any("path" in p for p in file_problems(make_file(full=GOOD_BODY + " Run scripts/x.py."))))

    def test_angle_bracket_fails(self):
        self.assertTrue(any("angle" in p for p in file_problems(make_file(short=GOOD_BODY + " Use <name>."))))

    def test_table_in_full_fails(self):
        self.assertTrue(any("table" in p for p in file_problems(make_file(full=GOOD_BODY + "\n| a | b |\n| --- | --- |"))))

    def test_code_fence_fails(self):
        self.assertTrue(any("fence" in p for p in file_problems(make_file(full=GOOD_BODY + "\n```\nx\n```"))))

    def test_missing_block_fails(self):
        text = make_file().replace(START, "", 1)
        self.assertTrue(file_problems(text))

    def test_missing_try_it_fails(self):
        self.assertTrue(any("Try it" in p for p in file_problems(make_file().replace("Try it", "Example"))))


if __name__ == "__main__":
    unittest.main()


class GuideMatchesFiles(unittest.TestCase):
    """docs/paste-ready.md quotes block sizes; they must equal what the files measure, so the guide cannot drift."""

    @staticmethod
    def measured():
        sizes = {"SHORT": [], "STANDARD": [], "FULL": []}
        for f in paste_ready_files():
            for name, body in parse_blocks(f.read_text(encoding="utf-8")):
                sizes[name].append(len(body))
        return {k: (min(v), max(v)) for k, v in sizes.items()}

    @staticmethod
    def stated_line(guide):
        for line in guide.splitlines():
            if line.startswith("Block sizes in this repository"):
                return line
        raise AssertionError("the guide has no 'Block sizes in this repository' line")

    @staticmethod
    def expected_line_parts(m):
        return [f"SHORT {m['SHORT'][0]:,} to {m['SHORT'][1]:,} characters",
                f"STANDARD {m['STANDARD'][0]:,} to {m['STANDARD'][1]:,}",
                f"FULL {m['FULL'][0]:,} to {m['FULL'][1]:,}"]

    def test_guide_block_sizes_match_the_files(self):
        guide = (ROOT / "docs" / "paste-ready.md").read_text(encoding="utf-8")
        line = self.stated_line(guide)
        for part in self.expected_line_parts(self.measured()):
            self.assertIn(part, line)

    def test_a_guide_with_a_wrong_size_would_fail(self):
        m = self.measured()
        wrong = dict(m)
        wrong["STANDARD"] = (m["STANDARD"][0], m["STANDARD"][1] + 1)
        line = "Block sizes in this repository: " + "; ".join(self.expected_line_parts(m))
        parts = self.expected_line_parts(wrong)
        self.assertTrue(any(part not in line for part in parts))
