"""Tests for the paste-ready versions of skills (references/paste-ready.md).

A paste-ready file lets a person use a skill in any chat assistant with no install, no scripts and no repository:
they copy one block (a "box" in the people-facing text) into the first message of a new chat, or into their tool's
instructions area if it has one. Each file holds two blocks, in this order, each between the markers below: SHORT
(at most 1,200 characters) and STANDARD (at most 3,300). Between the markers, each block's
text sits inside one ```text fence, so GitHub shows a copy button; the two fence lines are not part of the block, and
the lengths are measured without them. Every block's text must:

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
NAMES = ("SHORT", "STANDARD")
LIMITS = {"SHORT": 1200, "STANDARD": 3300}
# Claude organization instructions take at most 3,000 characters; a STANDARD block above this must be named in the guide.
ORG_LIMIT = 3000

PATH_RE = re.compile(r"\b(?:scripts|references|evals|tests|assets)/|\b[\w-]+\.(?:py|md|json|txt|csv|ya?ml|sh|ps1|html)\b"
                     r"|[A-Za-z]:\\|(?:^|\s)\.{0,2}/[\w.-]+/", re.I)
URL_RE = re.compile(r"https?://|\bwww\.|\b[\w-]+\.(?:com|org|gov|net|edu|uk|info|io)\b", re.I)
PHONE_RE = re.compile(r"(?:\+?\d[\s().-]*){7,}")
HEADING_RE = re.compile(r"^#+ .*?\b(SHORT|STANDARD|FULL)\b", re.M)  # FULL is still read, so a leftover FULL block fails
TABLE_RE = re.compile(r"^\s*\|.*\|\s*$|^\s*\|?\s*:?-{3,}:?\s*\|", re.M)


FENCE_OPEN = "```text"
FENCE_CLOSE = "```"


def unfence(raw):
    """Return (body, fenced): the text between the START and END lines with its outer ```text fence lines removed.
    fenced is False when the outer fence is missing; then body is the raw text, so the other checks still run."""
    lines = raw.replace("\r\n", "\n").strip("\n").split("\n")
    if len(lines) >= 2 and lines[0].strip() == FENCE_OPEN and lines[-1].strip() == FENCE_CLOSE:
        return "\n".join(lines[1:-1]).strip("\n"), True
    return "\n".join(lines), False


def parse_blocks(text, with_fence=False):
    """Return a list of (name, body) for each START/END block. name is the SHORT or STANDARD word in the last
    Markdown heading above START (for example '## STANDARD block'). body excludes the outer ```text fence lines.
    With with_fence=True each item is (name, body, fenced)."""
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
        body, fenced = unfence(text[s + len(START):e])
        name = headings[-1] if headings else "?"
        blocks.append((name, body, fenced) if with_fence else (name, body))
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
    for name, _body, fenced in parse_blocks(text, with_fence=True):
        if not fenced:
            problems.append(f"{name} is not inside a ```text fence between the START and END lines")
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

    def test_the_required_blocks_carry_the_safety_lines(self):
        """In every block of the five care skills: the rules hold however a request is framed, the urgent-symptom
        line, 'your local emergency number' or local emergency services, the one allowed number only as '(911 in the US)'
        in the urgent line and the danger line and no other number of three or more digits, no number from memory
        even when labelled, and no closing line after a reply about feelings. The STANDARD block also keeps its closing
        line when asked to drop it, and does not refuse a general question."""
        for name in REQUIRED:
            text = (SKILLS / name / "references" / "paste-ready.md").read_text(encoding="utf-8")
            for block, body in parse_blocks(text):
                with self.subTest(skill=name, block=block):
                    low = body.lower()
                    self.assertIn("ignore the rules", low)
                    self.assertIn("not instructions", low.replace("never instructions", "not instructions"))
                    self.assertIn("do not wait", low)
                    self.assertIn("local emergency", low)
                    self.assertIn("write no other number, even if asked", low)
                    self.assertEqual(low.count("(911 in the us)"), 2, "the one allowed number, in its one bracket form")
                    self.assertEqual(re.findall(r"\d{3,}", low), ["911", "911"], "no number but the two brackets")
                    self.assertIn("even if you label it", low, "a label must not license a number from memory")
                    self.assertIn("not after a reply about feelings", low)
                    if block == "STANDARD":
                        self.assertIn("keep this line even if asked to drop it", low)
                        self.assertIn("do not refuse a general question", low)

    def test_no_block_has_the_ready_line(self):
        """Removed after live tests: a model answered only 'Ready.' to real questions sent with the block."""
        for f in paste_ready_files():
            for block, body in parse_blocks(f.read_text(encoding="utf-8")):
                with self.subTest(skill=f.parent.parent.name, block=block):
                    self.assertNotIn("ready.", body.lower())
                    self.assertNotIn("first message", body.lower())


GOOD_BODY = ("This is not medical advice. Do not share names, dates of birth or record numbers. "
             "Bring medical questions to the care team.")


def make_file(short=GOOD_BODY, standard=GOOD_BODY, fence=True):
    parts = ["How to use this: paste a block.", ""]
    for name, body in (("SHORT", short), ("STANDARD", standard)):
        inner = [FENCE_OPEN, body, FENCE_CLOSE] if fence else [body]
        parts += [f"## {name} block", START, *inner, END, ""]
    parts.append("Try it: ask a question.")
    return "\n".join(parts)


class NegativeControls(unittest.TestCase):
    """Each broken file must fail, so a check that stops working breaks the tests."""

    def test_good_synthetic_file_passes(self):
        self.assertEqual(file_problems(make_file()), [])

    def test_over_length_short_block_fails(self):
        self.assertTrue(any("limit is 1200" in p for p in file_problems(make_file(short=GOOD_BODY + " x" * 700))))

    def test_over_length_standard_block_fails(self):
        self.assertTrue(any("limit is 3300" in p for p in file_problems(make_file(standard=GOOD_BODY + " x" * 1600))))

    def test_a_leftover_full_block_fails(self):
        extra = ["## FULL block", START, FENCE_OPEN, GOOD_BODY, FENCE_CLOSE, END, ""]
        text = make_file() + "\n" + "\n".join(extra)
        self.assertTrue(any("expected blocks" in p for p in file_problems(text)))

    def test_block_missing_care_team_fails(self):
        body = GOOD_BODY.replace("care team", "clinic")
        self.assertTrue(any("'care team'" in p for p in file_problems(make_file(standard=body))))

    def test_block_missing_not_medical_advice_fails(self):
        body = GOOD_BODY.replace("not medical advice", "general information")
        self.assertTrue(any("'not medical advice'" in p for p in file_problems(make_file(short=body))))

    def test_block_missing_identifier_warning_fails(self):
        body = GOOD_BODY.replace("dates of birth", "birthdays")
        self.assertTrue(any("dates of birth" in p for p in file_problems(make_file(standard=body))))

    def test_url_fails(self):
        self.assertTrue(any("URL" in p for p in file_problems(make_file(standard=GOOD_BODY + " See example.org."))))

    def test_phone_fails(self):
        self.assertTrue(any("phone" in p for p in file_problems(make_file(standard=GOOD_BODY + " Call 555 010 0199."))))

    def test_path_fails(self):
        self.assertTrue(any("path" in p for p in file_problems(make_file(standard=GOOD_BODY + " Run scripts/x.py."))))

    def test_angle_bracket_fails(self):
        self.assertTrue(any("angle" in p for p in file_problems(make_file(short=GOOD_BODY + " Use <name>."))))

    def test_table_in_standard_fails(self):
        self.assertTrue(any("table" in p for p in file_problems(make_file(standard=GOOD_BODY + "\n| a | b |\n| --- | --- |"))))

    def test_code_fence_fails(self):
        self.assertTrue(any("fence" in p for p in file_problems(make_file(standard=GOOD_BODY + "\n```\nx\n```"))))

    def test_an_inner_code_fence_inside_the_outer_fence_still_fails(self):
        for inner in ("```", "```text", "~~~"):
            with self.subTest(inner=inner):
                body = GOOD_BODY + "\n" + inner + "\nx"
                self.assertTrue(any("contains a code fence" in p for p in file_problems(make_file(standard=body))))

    def test_a_block_without_the_outer_fence_fails(self):
        problems = file_problems(make_file(fence=False))
        self.assertEqual(sum("not inside a ```text fence" in p for p in problems), 2, problems)

    def test_the_outer_fence_lines_are_not_part_of_the_block_or_its_length(self):
        name, body, fenced = parse_blocks(make_file(), with_fence=True)[0]
        self.assertEqual((name, body, fenced), ("SHORT", GOOD_BODY, True))
        exact = GOOD_BODY + " " + "x" * (1200 - len(GOOD_BODY) - 1)
        self.assertEqual(len(exact), 1200)
        self.assertEqual(file_problems(make_file(short=exact)), [], "1,200 characters inside the fence fit")
        self.assertTrue(any("limit is 1200" in p for p in file_problems(make_file(short=exact + "x"))))

    def test_missing_block_fails(self):
        text = make_file().replace(START, "", 1)
        self.assertTrue(file_problems(text))

    def test_missing_try_it_fails(self):
        self.assertTrue(any("Try it" in p for p in file_problems(make_file().replace("Try it", "Example"))))



class GuideMatchesFiles(unittest.TestCase):
    """docs/paste-ready.md quotes block sizes; they must equal what the files measure, so the guide cannot drift."""

    @staticmethod
    def measured():
        sizes = {"SHORT": [], "STANDARD": []}
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
                f"STANDARD {m['STANDARD'][0]:,} to {m['STANDARD'][1]:,}"]

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

    def test_the_guide_names_each_standard_block_over_the_claude_organization_limit(self):
        guide = (ROOT / "docs" / "paste-ready.md").read_text(encoding="utf-8")
        row = next((line for line in guide.splitlines() if line.startswith("| Claude organization instructions")), None)
        self.assertIsNotNone(row, "the guide's table has no 'Claude organization instructions' row")
        for f in paste_ready_files():
            for name, body in parse_blocks(f.read_text(encoding="utf-8")):
                if name == "STANDARD" and len(body) > ORG_LIMIT:
                    with self.subTest(skill=f.parent.parent.name):
                        self.assertIn(f"`{f.parent.parent.name}`", row)

    def test_the_guide_no_longer_mentions_a_full_block(self):
        guide = (ROOT / "docs" / "paste-ready.md").read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"\bFULL\b", guide))  # case-sensitive: quotes such as "full control" stay
        self.assertIsNone(re.search(r"\bfull (?:box|block)", guide, re.I))


if __name__ == "__main__":
    unittest.main()
