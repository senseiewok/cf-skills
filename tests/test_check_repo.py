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
    audience: "researchers, builders"
    level: "base"
    category: "evidence"
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

    def test_a_frontmatter_key_outside_the_format_is_reported_and_the_defined_keys_are_allowed(self):
        self.edit(".claude/skills/alpha/SKILL.md", "license: CC0-1.0\n", "license: CC0-1.0\nallowed-tools: Read\ncompatibility: Needs Python 3.\n")
        code, errs, text = self.errors()
        self.assertEqual((code, errs), (0, []), "every key the format defines is allowed: " + text)
        self.edit(".claude/skills/alpha/SKILL.md", "license: CC0-1.0\n", "license: CC0-1.0\nversion: 2\nauthor: someone\n")
        code, errs, text = self.errors()
        self.assertEqual(code, 1, text)
        self.assertTrue(any("skills/alpha/SKILL.md" in e and "unexpected" in e and "author, version" in e for e in errs), errs)

    def test_angle_brackets_in_a_description_are_reported(self):
        for bad in ("Use <this> tag.", "Use when a > b.", "Open the page <b"):
            with self.subTest(bad=bad):
                self.setUp()
                self.edit(".claude/skills/alpha/SKILL.md", "Does a thing. Use it when asked about the thing.", bad)
                code, errs, text = self.errors()
                self.assertEqual(code, 1, text)
                self.assertTrue(any("description" in e and "angle brackets" in e for e in errs), errs)

    def test_a_block_description_marker_is_not_also_reported_as_an_angle_bracket(self):
        self.edit(".claude/skills/alpha/SKILL.md", 'description: "Does a thing. Use it when asked about the thing."', "description: >")
        code, errs, text = self.errors()
        self.assertEqual(code, 1, text)
        self.assertFalse(any("angle" in e for e in errs), errs)

    def test_a_compatibility_over_500_characters_is_reported_and_500_is_allowed(self):
        self.edit(".claude/skills/alpha/SKILL.md", "license: CC0-1.0\n", "license: CC0-1.0\ncompatibility: " + "x" * 500 + "\n")
        code, errs, text = self.errors()
        self.assertEqual((code, errs), (0, []), "exactly 500 characters is allowed: " + text)
        self.edit(".claude/skills/alpha/SKILL.md", "x" * 500, "x" * 501)
        code, errs, text = self.errors()
        self.assertEqual(code, 1, text)
        self.assertTrue(any("compatibility" in e and "500" in e for e in errs), errs)

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

    # ---- audience, level and category (required under metadata)
    def test_an_unknown_audience_is_reported_with_the_skill_and_the_allowed_words(self):
        self.edit(".claude/skills/alpha/SKILL.md", 'audience: "researchers, builders"', 'audience: "researchers, parents"')
        code, errs, text = self.errors()
        self.assertEqual(code, 1, text)
        self.assertTrue(any("skills/alpha/SKILL.md" in e and "unknown audience 'parents'" in e and "patients-families, care-teams, researchers, builders" in e for e in errs), errs)
        self.assertFalse(any("researchers'" in e for e in errs), "the valid word in the same list is not reported: " + text)

    def test_every_audience_word_and_both_levels_and_every_category_are_allowed(self):
        cases = [('audience: "researchers, builders"', f'audience: "{a}"') for a in
                 ("patients-families", "care-teams", "researchers", "builders", "patients-families, care-teams, researchers, builders")]
        cases += [('level: "base"', f'level: "{v}"') for v in ("base", "advanced")]
        cases += [('category: "evidence"', f'category: "{c}"') for c in ("safe-ai-use", "communication", "evidence", "tool-evaluation", "web")]
        for old, new in cases:
            with self.subTest(new=new):
                self.setUp()
                self.edit(".claude/skills/alpha/SKILL.md", old, new)
                code, errs, text = self.errors()
                self.assertEqual((code, errs), (0, []), text)

    def test_a_missing_audience_level_or_category_is_reported_with_the_allowed_words(self):
        cases = {
            "audience": ('    audience: "researchers, builders"\n', "patients-families, care-teams, researchers, builders"),
            "level": ('    level: "base"\n', "base, advanced"),
            "category": ('    category: "evidence"\n', "safe-ai-use, communication, evidence, tool-evaluation, web"),
        }
        for key, (line, allowed) in cases.items():
            with self.subTest(key=key):
                self.setUp()
                self.edit(".claude/skills/alpha/SKILL.md", line, "")
                code, errs, text = self.errors()
                self.assertEqual(code, 1, text)
                self.assertTrue(any("skills/alpha/SKILL.md" in e and f"missing metadata '{key}'" in e and allowed in e for e in errs), errs)

    def test_an_empty_audience_is_reported_as_missing(self):
        self.edit(".claude/skills/alpha/SKILL.md", 'audience: "researchers, builders"', 'audience: ""')
        code, errs, text = self.errors()
        self.assertEqual(code, 1, text)
        self.assertTrue(any("missing metadata 'audience'" in e for e in errs), errs)

    def test_a_bad_level_or_category_is_reported_with_the_allowed_words(self):
        for old, new, needle in (('level: "base"', 'level: "expert"', "unknown level 'expert'"),
                                 ('category: "evidence"', 'category: "science"', "unknown category 'science'"),
                                 ('level: "base"', 'level: "base, advanced"', "unknown level 'base, advanced'")):
            with self.subTest(new=new):
                self.setUp()
                self.edit(".claude/skills/alpha/SKILL.md", old, new)
                code, errs, text = self.errors()
                self.assertEqual(code, 1, text)
                self.assertTrue(any("skills/alpha/SKILL.md" in e and needle in e and "allowed" in e for e in errs), errs)

    def test_audience_at_the_top_level_is_reported_with_a_hint_to_move_it_under_metadata(self):
        self.edit(".claude/skills/alpha/SKILL.md", '    audience: "researchers, builders"\n', "")
        self.edit(".claude/skills/alpha/SKILL.md", "license: CC0-1.0\n", 'license: CC0-1.0\naudience: "researchers"\n')
        code, errs, text = self.errors()
        self.assertEqual(code, 1, text)
        self.assertTrue(any("unexpected" in e and "audience" in e and "under metadata" in e for e in errs), errs)
        self.assertTrue(any("missing metadata 'audience'" in e for e in errs), errs)

    def test_a_key_of_the_same_name_outside_metadata_does_not_count(self):
        # an indented 'level' under another top-level key is not metadata
        self.edit(".claude/skills/alpha/SKILL.md", '    level: "base"\n', "")
        self.edit(".claude/skills/alpha/SKILL.md", "license: CC0-1.0\n", 'license: CC0-1.0\nallowed-tools: Read\n    level: "base"\n')
        code, errs, text = self.errors()
        self.assertEqual(code, 1, text)
        self.assertTrue(any("missing metadata 'level'" in e for e in errs), errs)

    def test_a_copy_of_the_repository_template_passes(self):
        template = SCRIPT.parents[1] / "template" / "SKILL.md"
        text = template.read_text(encoding="utf-8").replace("name: template-skill", "name: alpha")
        (self.root / ".claude" / "skills" / "alpha" / "SKILL.md").write_text(text, encoding="utf-8")
        code, errs, text = self.errors()
        self.assertEqual((code, errs), (0, []), text)
        # negative control: the same copy without its level fails
        p = self.root / ".claude" / "skills" / "alpha" / "SKILL.md"
        p.write_text(p.read_text(encoding="utf-8").replace('    level: "base"\n', ""), encoding="utf-8")
        code, errs, text = self.errors()
        self.assertEqual(code, 1, text)
        self.assertTrue(any("missing metadata 'level'" in e for e in errs), errs)

    def test_the_vocabularies_match_the_index_builder(self):
        import ast
        def consts(path):
            tree = ast.parse(Path(path).read_text(encoding="utf-8"))
            out = {}
            for node in tree.body:
                if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and node.targets[0].id in ("AUDIENCES", "LEVELS", "CATEGORIES"):
                    out[node.targets[0].id] = ast.literal_eval(node.value)
            return out
        a = consts(SCRIPT)
        b = consts(SCRIPT.parent / "make_index.py")
        self.assertEqual(set(a), {"AUDIENCES", "LEVELS", "CATEGORIES"})
        self.assertEqual(a, b)

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

    # ---- eval cases that point at pasted text they do not contain
    def write_cases(self, *cases):
        d = self.root / ".claude" / "skills" / "alpha" / "evals"
        d.mkdir(exist_ok=True)
        (d / "cases.json").write_text(json.dumps({"skill": "alpha", "cases": list(cases)}), encoding="utf-8")

    def test_a_case_that_says_translate_this_with_no_text_is_reported(self):
        for situation, um in (("Translate this airway clearance handout into Spanish.", None),
                              ("This AI answer is in English. Translate it into French.", None),
                              ("Simplify the text below for a parent.", ""),
                              ("Here is my clinic letter. Check what the AI said about it.", "   ")):
            with self.subTest(situation=situation):
                case = {"id": "t", "situation": situation, "expected": "e", "forbidden": "f"}
                if um is not None:
                    case["user_message"] = um
                self.write_cases(case)
                code, errs, text = self.errors()
                self.assertEqual(code, 1, text)
                self.assertTrue(any("evals/cases.json" in e and "case 't'" in e and "pasted text" in e for e in errs), errs)

    def test_a_case_that_holds_its_text_passes(self):
        self.write_cases(
            {"id": "inline", "situation": "Rewrite this for a parent: 'Do airway clearance twice a day for 30 minutes.'", "expected": "e", "forbidden": "f"},
            {"id": "message", "situation": "Translate this handout.", "user_message": "Translate this into Spanish:\n\nDo airway clearance twice a day.",
             "expected": "e", "forbidden": "f"},
            {"id": "no-reference", "situation": "What is a sweat test?", "expected": "e", "forbidden": "f"})
        code, errs, text = self.errors()
        self.assertEqual((code, errs), (0, []), text)

    def test_a_suspect_case_passes_only_with_a_note(self):
        case = {"id": "t", "situation": "Translate this handout into Spanish.", "expected": "e", "forbidden": "f", "suspect": True}
        self.write_cases(case)
        code, errs, text = self.errors()
        self.assertEqual(code, 1, text)
        self.assertTrue(any("suspect_note" in e for e in errs), errs)
        case["suspect_note"] = "No handout text; a person writes it."
        self.write_cases(case)
        code, errs, text = self.errors()
        self.assertEqual((code, errs), (0, []), text)
        case["suspect"] = "yes"
        self.write_cases(case)
        code, errs, text = self.errors()
        self.assertTrue(any("'suspect' must be true or false" in e for e in errs), errs)

    def test_the_real_repository_marks_every_such_case_suspect(self):
        root = SCRIPT.resolve().parents[1]
        r = subprocess.run([sys.executable, str(SCRIPT), str(root)], capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertFalse([ln for ln in r.stdout.splitlines() if "evals/cases.json" in ln], r.stdout)

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
