"""Tests for scripts/make_paste_ready.py, which builds each CF care skill's paste-ready boxes, and the rules in its
SKILL.md, from one shared core (shared/paste-core/) and the skill's references/paste-parts.md.

They check that the files on disk are what the generator makes, that generating twice gives the same bytes, that
--check fails when the core changes without regenerating, that every box carries its core verbatim (so each box works
alone when pasted), that SKILL.md holds the STANDARD box exactly, and that the generator refuses a box over its limit.
Standard library only; also runs under pytest.
"""
import contextlib
import importlib.util
import io
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / ".claude" / "skills"
CORE = ROOT / "shared" / "paste-core"
REQUIRED = ["cf-ai-safe-use", "cf-plain-language-rewrite", "cf-visit-prep", "cf-answer-check", "cf-ai-tool-review"]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


gen = load("make_paste_ready", ROOT / "scripts" / "make_paste_ready.py")
tpr = load("test_paste_ready_for_generator", ROOT / "tests" / "test_paste_ready.py")


def run(*args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = gen.main([str(a) for a in args])
    return code, out.getvalue()


def core_text(name):
    return (CORE / name).read_text(encoding="utf-8").replace("\r\n", "\n").strip("\n")


class RealRepository(unittest.TestCase):
    def test_the_generated_files_are_up_to_date(self):
        code, out = run(ROOT, "--check")
        self.assertEqual(code, 0, out)

    def test_every_required_skill_has_parts(self):
        for name in REQUIRED:
            with self.subTest(skill=name):
                self.assertTrue((SKILLS / name / "references" / "paste-parts.md").is_file())

    def test_every_box_contains_its_core_verbatim(self):
        cores = {"SHORT": core_text("core-short.txt"), "STANDARD": core_text("core-standard.txt")}
        check = core_text("check-line.txt")
        for name in REQUIRED:
            blocks = tpr.parse_blocks((SKILLS / name / "references" / "paste-ready.md").read_text(encoding="utf-8"))
            self.assertEqual([b[0] for b in blocks], ["SHORT", "STANDARD"])
            for block, body in blocks:
                with self.subTest(skill=name, block=block):
                    self.assertIn(cores[block], body)
                    if block == "STANDARD":
                        self.assertIn(check, body)

    def test_skill_md_holds_the_standard_box_exactly(self):
        for name in REQUIRED:
            with self.subTest(skill=name):
                blocks = dict(tpr.parse_blocks((SKILLS / name / "references" / "paste-ready.md").read_text(encoding="utf-8")))
                skill = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
                s = skill.index(gen.SKILL_START) + len(gen.SKILL_START)
                e = skill.index(gen.SKILL_END)
                self.assertEqual(skill[s:e], "\n```text\n" + blocks["STANDARD"] + "\n```\n")

    def test_the_rules_that_must_stay_in_skill_md_are_there(self):
        """The urgent, phone-number and one-person rules are never moved out of SKILL.md."""
        for name in REQUIRED:
            low = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8").lower()
            with self.subTest(skill=name):
                self.assertIn("urgent symptom", low)
                self.assertIn("add no phone number, even an emergency one", low)
                self.assertIn("for one person, never", low)


class InACopy(unittest.TestCase):
    """Runs the generator on a copy of the relevant files, so the real repository is never written."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        shutil.copytree(CORE, self.root / "shared" / "paste-core")
        for name in REQUIRED:
            src = SKILLS / name
            dst = self.root / ".claude" / "skills" / name
            (dst / "references").mkdir(parents=True)
            shutil.copy2(src / "SKILL.md", dst / "SKILL.md")
            for f in ("paste-parts.md", "paste-ready.md"):
                shutil.copy2(src / "references" / f, dst / "references" / f)

    def tearDown(self):
        self._tmp.cleanup()

    def snapshot(self):
        return {p.relative_to(self.root).as_posix(): p.read_bytes() for p in sorted(self.root.rglob("*")) if p.is_file()}

    def test_generation_is_deterministic_and_matches_the_repository(self):
        before = self.snapshot()
        self.assertEqual(run(self.root)[0], 0)
        first = self.snapshot()
        self.assertEqual(run(self.root)[0], 0)
        self.assertEqual(first, self.snapshot())
        self.assertEqual(first, before, "the repository's files are what the generator makes")

    def test_check_fails_when_a_core_word_changes_without_regenerating(self):
        core = self.root / "shared" / "paste-core" / "core-standard.txt"
        text = core.read_text(encoding="utf-8")
        self.assertIn("Urgent symptom.", text)
        core.write_text(text.replace("Urgent symptom.", "Urgent sign."), encoding="utf-8")
        code, out = run(self.root, "--check")
        self.assertEqual(code, 1)
        self.assertIn("out of date", out)
        self.assertEqual(run(self.root)[0], 0)
        self.assertEqual(run(self.root, "--check")[0], 0)
        pr = (self.root / ".claude" / "skills" / "cf-visit-prep" / "references" / "paste-ready.md").read_text(encoding="utf-8")
        self.assertIn("Urgent sign.", pr)
        self.assertNotIn("Urgent symptom.", pr)

    def test_check_fails_when_a_box_is_edited_by_hand(self):
        pr = self.root / ".claude" / "skills" / "cf-answer-check" / "references" / "paste-ready.md"
        pr.write_text(pr.read_text(encoding="utf-8").replace("Check silently.", "Check.", 1), encoding="utf-8")
        self.assertEqual(run(self.root, "--check")[0], 1)

    def test_check_writes_nothing(self):
        core = self.root / "shared" / "paste-core" / "core-short.txt"
        core.write_text(core.read_text(encoding="utf-8") + "One more line.\n", encoding="utf-8")
        before = self.snapshot()
        self.assertEqual(run(self.root, "--check")[0], 1)
        self.assertEqual(before, self.snapshot())

    def test_a_box_over_its_limit_is_refused(self):
        parts = self.root / ".claude" / "skills" / "cf-ai-safe-use" / "references" / "paste-parts.md"
        text = parts.read_text(encoding="utf-8")
        marker = "## SHORT task\n\n```text\n"
        self.assertIn(marker, text)
        parts.write_text(text.replace(marker, marker + "word " * 60 + "\n"), encoding="utf-8")
        code, out = run(self.root)
        self.assertEqual(code, 1)
        self.assertIn("the limit is 1,200", out)

    def test_a_skill_md_without_markers_is_refused(self):
        sm = self.root / ".claude" / "skills" / "cf-visit-prep" / "SKILL.md"
        sm.write_text(sm.read_text(encoding="utf-8").replace(gen.SKILL_START, ""), encoding="utf-8")
        code, out = run(self.root)
        self.assertEqual(code, 1)
        self.assertIn("paste-standard:start", out)

    def test_text_outside_the_boxes_is_kept(self):
        pr = self.root / ".claude" / "skills" / "cf-visit-prep" / "references" / "paste-ready.md"
        before = pr.read_text(encoding="utf-8")
        self.assertEqual(run(self.root)[0], 0)
        after = pr.read_text(encoding="utf-8")
        for part in ("## How to use this", "## Try it", "## What this version cannot do", "(evidence.md)"):
            self.assertIn(part, after)
        self.assertEqual(before[:before.index("## How to use this") + 200], after[:after.index("## How to use this") + 200])

    def test_usage_errors(self):
        self.assertEqual(run(self.root / "missing")[0], 2)
        self.assertEqual(run("--bad")[0], 2)


if __name__ == "__main__":
    unittest.main()
