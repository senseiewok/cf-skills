"""Tests for scripts/check_repo.py: the mechanical checks every skill in this repository must pass.
Each test builds a small repository in a temporary folder, breaks it in one way and runs the checker as a subprocess.
By default the script next to this folder is tested; set CHECK_REPO_PATH to test another file. Standard library only."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(os.environ.get("CHECK_REPO_PATH") or Path(__file__).resolve().parents[1] / "scripts" / "check_repo.py")

SKILL = """---
name: {name}
description: "{desc}"
license: CC0-1.0
metadata:
    version: "1.0.0"
---

# {name}

Read the [notes](references/notes.md) first.
"""
GOOD_README = "# Skills\n\nSee [the first skill](.claude/skills/alpha/SKILL.md) and [install notes](docs/install.md#top).\n"
MARKET = {"name": "m", "owner": {"name": "Someone"}, "plugins": [{"name": "alpha", "description": "d", "source": "./", "strict": False, "skills": ["./.claude/skills/alpha"]}]}


def build(root, extra_skills=()):
    """A repository that passes every check."""
    (root / ".claude" / "skills" / "alpha" / "references").mkdir(parents=True)
    (root / ".claude" / "skills" / "alpha" / "SKILL.md").write_text(SKILL.format(name="alpha", desc="Does a thing. Use it when asked about the thing."), encoding="utf-8")
    (root / ".claude" / "skills" / "alpha" / "references" / "notes.md").write_text("Notes.\n", encoding="utf-8")
    (root / "docs").mkdir()
    (root / "docs" / "install.md").write_text("# Install\n\nBack to the [README](../README.md).\n", encoding="utf-8")
    (root / "README.md").write_text(GOOD_README, encoding="utf-8")
    (root / ".claude-plugin").mkdir()
    (root / ".claude-plugin" / "marketplace.json").write_text(json.dumps(MARKET), encoding="utf-8")


def run(root, *args):
    r = subprocess.run([sys.executable, str(SCRIPT), str(root), *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.returncode, r.stdout, r.stderr


class CheckRepoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="check-repo-"))
        self.root = self.tmp / "repo"
        self.root.mkdir()
        build(self.root)
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def edit(self, rel, old, new):
        p = self.root / rel
        s = p.read_text(encoding="utf-8")
        self.assertIn(old, s, f"test setup: {old!r} not in {rel}")
        p.write_text(s.replace(old, new), encoding="utf-8")

    def errors(self, *args):
        code, out, err = run(self.root, *args)
        return code, [ln for ln in out.splitlines() if ln.startswith("ERROR")], out + err

    # ---- the good repository
    def test_a_good_repository_passes_with_exit_0_and_says_ok(self):
        code, errs, text = self.errors()
        self.assertEqual((code, errs), (0, []), text)
        self.assertIn("ok", text.lower())

    def test_it_defaults_to_the_repository_that_holds_the_script(self):
        r = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertIn(r.returncode, (0, 1), r.stderr[-300:])  # it ran on the real repository without crashing

    def test_a_missing_root_is_a_usage_error_with_exit_2(self):
        code, out, err = run(self.tmp / "nowhere")
        self.assertEqual(code, 2, out + err)

    # ---- frontmatter
    def test_a_folder_name_that_differs_from_the_name_is_reported(self):
        self.edit(".claude/skills/alpha/SKILL.md", "name: alpha", "name: beta")
        code, errs, text = self.errors()
        self.assertEqual(code, 1, text)
        self.assertTrue(any("skills/alpha/SKILL.md" in e and "name" in e for e in errs), errs)

    def test_a_name_with_capitals_or_underscores_is_reported(self):
        for bad in ("Alpha", "al_pha", "-alpha", "alpha-"):
            with self.subTest(bad=bad):
                self.setUp()
                self.edit(".claude/skills/alpha/SKILL.md", "name: alpha", f"name: {bad}")
                code, errs, text = self.errors()
                self.assertEqual(code, 1, text)
                self.assertTrue(any("name" in e for e in errs), errs)

    def test_a_name_longer_than_64_characters_is_reported(self):
        long = "a" * 65
        (self.root / ".claude" / "skills" / long).mkdir()
        (self.root / ".claude" / "skills" / long / "SKILL.md").write_text(SKILL.format(name=long, desc="x y z").replace("[notes](references/notes.md)", "nothing"), encoding="utf-8")
        code, errs, text = self.errors()
        self.assertEqual(code, 1, text)
        self.assertTrue(any("64" in e for e in errs), errs)

    def test_a_missing_description_is_reported(self):
        self.edit(".claude/skills/alpha/SKILL.md", 'description: "Does a thing. Use it when asked about the thing."\n', "")
        code, errs, text = self.errors()
        self.assertEqual(code, 1, text)
        self.assertTrue(any("description" in e for e in errs), errs)

    def test_a_description_over_1024_characters_is_reported_and_1024_is_allowed(self):
        self.edit(".claude/skills/alpha/SKILL.md", "Does a thing. Use it when asked about the thing.", "x" * 1024)
        code, errs, text = self.errors()
        self.assertEqual((code, errs), (0, []), "exactly 1,024 characters is allowed: " + text)
        self.edit(".claude/skills/alpha/SKILL.md", "x" * 1024, "x" * 1025)
        code, errs, text = self.errors()
        self.assertEqual(code, 1, text)
        self.assertTrue(any("1024" in e or "1,024" in e for e in errs), errs)

    def test_a_folded_or_literal_block_description_is_reported_not_read_as_one_character(self):
        for marker in (">", "|", ">-"):
            with self.subTest(marker=marker):
                self.setUp()
                self.edit(".claude/skills/alpha/SKILL.md", 'description: "Does a thing. Use it when asked about the thing."', "description: " + marker)
                code, errs, text = self.errors()
                self.assertEqual(code, 1, text)
                self.assertTrue(any("description" in e and "one-line" in e for e in errs), errs)

    def test_a_missing_licence_is_reported(self):
        self.edit(".claude/skills/alpha/SKILL.md", "license: CC0-1.0\n", "")
        code, errs, text = self.errors()
        self.assertEqual(code, 1, text)
        self.assertTrue(any("license" in e.lower() for e in errs), errs)

    def test_a_skill_without_frontmatter_is_reported_not_a_crash(self):
        (self.root / ".claude" / "skills" / "alpha" / "SKILL.md").write_text("# no frontmatter here\n", encoding="utf-8")
        code, errs, text = self.errors()
        self.assertEqual(code, 1, text)
        self.assertTrue(any("frontmatter" in e.lower() for e in errs), errs)
        self.assertNotIn("Traceback", text)

    def test_a_skill_folder_without_a_skill_md_is_reported(self):
        (self.root / ".claude" / "skills" / "empty").mkdir()
        code, errs, text = self.errors()
        self.assertEqual(code, 1, text)
        self.assertTrue(any("skills/empty" in e and "SKILL.md" in e for e in errs), errs)

    # ---- links
    def test_a_broken_relative_link_in_a_skill_is_reported_with_its_target(self):
        self.edit(".claude/skills/alpha/SKILL.md", "references/notes.md", "references/gone.md")
        code, errs, text = self.errors()
        self.assertEqual(code, 1, text)
        self.assertTrue(any("references/gone.md" in e for e in errs), errs)

    def test_a_broken_link_in_the_readme_and_in_docs_is_reported(self):
        self.edit("README.md", "docs/install.md#top", "docs/missing.md#top")
        self.edit("docs/install.md", "../README.md", "../NOPE.md")
        code, errs, text = self.errors()
        self.assertEqual(code, 1, text)
        self.assertTrue(any("README.md" in e and "docs/missing.md" in e for e in errs), errs)
        self.assertTrue(any("docs/install.md" in e and "NOPE.md" in e for e in errs), errs)

    def test_web_links_and_page_anchors_are_not_checked(self):
        (self.root / "README.md").write_text(GOOD_README + "[a](https://example.org/x) [b](http://example.org) [d](#top)\n", encoding="utf-8")
        code, errs, text = self.errors()
        self.assertEqual((code, errs), (0, []), text)

    def test_a_link_inside_a_code_fence_is_not_checked(self):
        (self.root / "README.md").write_text(GOOD_README + "\n```text\n[not a link](nowhere/at/all.md)\n```\n", encoding="utf-8")
        code, errs, text = self.errors()
        self.assertEqual((code, errs), (0, []), text)

    # ---- marketplace
    def test_a_marketplace_entry_for_a_skill_that_does_not_exist_is_reported(self):
        m = json.loads((self.root / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
        m["plugins"].append({"name": "ghost", "description": "d", "source": "./", "strict": False, "skills": ["./.claude/skills/ghost"]})
        (self.root / ".claude-plugin" / "marketplace.json").write_text(json.dumps(m), encoding="utf-8")
        code, errs, text = self.errors()
        self.assertEqual(code, 1, text)
        self.assertTrue(any("ghost" in e for e in errs), errs)

    def test_a_skill_that_is_not_in_the_marketplace_is_reported(self):
        (self.root / ".claude" / "skills" / "beta" / "references").mkdir(parents=True)
        (self.root / ".claude" / "skills" / "beta" / "SKILL.md").write_text(SKILL.format(name="beta", desc="Another thing."), encoding="utf-8")
        (self.root / ".claude" / "skills" / "beta" / "references" / "notes.md").write_text("n\n", encoding="utf-8")
        code, errs, text = self.errors()
        self.assertEqual(code, 1, text)
        self.assertTrue(any("beta" in e and "marketplace" in e.lower() for e in errs), errs)

    def test_a_skill_listed_twice_is_reported(self):
        m = json.loads((self.root / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
        m["plugins"].append({"name": "alpha-again", "description": "d", "source": "./", "strict": False, "skills": ["./.claude/skills/alpha"]})
        (self.root / ".claude-plugin" / "marketplace.json").write_text(json.dumps(m), encoding="utf-8")
        code, errs, text = self.errors()
        self.assertEqual(code, 1, text)
        self.assertTrue(any("alpha" in e and ("twice" in e or "more than once" in e or "duplicate" in e.lower()) for e in errs), errs)

    def test_invalid_marketplace_json_is_reported_not_a_crash(self):
        (self.root / ".claude-plugin" / "marketplace.json").write_text("{not json", encoding="utf-8")
        code, errs, text = self.errors()
        self.assertEqual(code, 1, text)
        self.assertTrue(any("marketplace.json" in e for e in errs), errs)
        self.assertNotIn("Traceback", text)

    # ---- hygiene
    def test_a_local_path_a_key_a_private_key_and_an_email_address_are_reported(self):
        cases = {
            "a Windows drive path": "See C:\\Users\\someone\\project for details.",
            "a home folder path": "See /Users/someone/project for details.",
            "an email address": "Write to person@example.org for details.",
            "a token": "Use ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8" + " as the token.",
            "a private key": "-----BEGIN " + "RSA PRIVATE KEY-----",
        }
        for label, line in cases.items():
            with self.subTest(label=label):
                self.setUp()
                (self.root / "docs" / "install.md").write_text("# Install\n\n" + line + "\n", encoding="utf-8")
                code, errs, text = self.errors()
                self.assertEqual(code, 1, f"{label}: {text}")
                self.assertTrue(any("docs/install.md" in e for e in errs), f"{label}: {errs}")

    def test_the_same_text_inside_a_skills_scripts_folder_is_not_scanned(self):
        (self.root / ".claude" / "skills" / "alpha" / "scripts").mkdir()
        (self.root / ".claude" / "skills" / "alpha" / "scripts" / "t.py").write_text("PATH = 'C:\\\\Users\\\\x'  # a test fixture\n", encoding="utf-8")
        code, errs, text = self.errors()
        self.assertEqual((code, errs), (0, []), text)

    # ---- output shape
    def test_errors_are_sorted_each_on_its_own_line_and_the_run_is_deterministic(self):
        self.edit(".claude/skills/alpha/SKILL.md", "references/notes.md", "references/gone.md")
        self.edit("README.md", "docs/install.md#top", "docs/missing.md#top")
        a = self.errors()
        b = self.errors()
        self.assertEqual(a, b)
        self.assertEqual(a[1], sorted(a[1]))
        self.assertGreaterEqual(len(a[1]), 2)
        self.assertTrue(all(e.startswith("ERROR ") for e in a[1]))

    def test_it_never_writes_into_the_repository(self):
        before = sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*"))
        self.errors()
        self.assertEqual(sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*")), before)

    def test_the_script_does_not_import_network_or_process_modules(self):
        import ast
        tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names |= {a.name for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                names.add(node.module)
        banned = {"socket", "urllib.request", "http.client", "requests", "subprocess", "ftplib", "smtplib"}
        self.assertFalse({n for n in names if n in banned or n.split(".")[0] in {"requests", "socket", "subprocess"}}, f"the checker must not import {names & banned}")


if __name__ == "__main__":
    unittest.main()
