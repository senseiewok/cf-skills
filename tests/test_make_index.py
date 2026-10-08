"""Tests for scripts/make_index.py: builds skills-index.json from each skill's frontmatter, so people and agents can see what a skill can do before they install it.
Each test builds a small repository in a temporary folder and runs the script as a subprocess. By default the script next to this folder is tested; set MAKE_INDEX_PATH to test
another file. Standard library only."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(os.environ.get("MAKE_INDEX_PATH") or Path(__file__).resolve().parents[1] / "scripts" / "make_index.py")

SKILL = """---
name: {name}
description: "{desc}"
license: CC0-1.0
metadata:
    version: "{version}"
    capabilities: "{caps}"
    optional-capabilities: "{opt}"
    audience: "{aud}"
    level: "{level}"
    category: "{cat}"
---

# {name}
"""


def skill(name, desc, version="1.0.0", caps="python", opt="", aud="researchers", level="base", cat="evidence"):
    return SKILL.format(name=name, desc=desc, version=version, caps=caps, opt=opt, aud=aud, level=level, cat=cat)


README = "# Repo\n\nIntro stays.\n\n## Skills\n\n<!-- skills-table:start -->\nold table\n<!-- skills-table:end -->\n\nAfter stays.\n"


class MakeIndexTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="make-index-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.root = self.tmp / "repo"
        for name, desc, version, caps, opt, aud, level, cat in (
                ("beta", "Does beta. Then more about beta.", "2.0.0", "runs-code, python", "browser", "builders, researchers", "advanced", "tool-evaluation"),
                ("alpha", "Does alpha.", "1.0.0", "network, runs-code, python", "", "patients-families", "base", "safe-ai-use")):
            d = self.root / ".claude" / "skills" / name
            d.mkdir(parents=True)
            (d / "SKILL.md").write_text(skill(name, desc, version, caps, opt, aud, level, cat), encoding="utf-8")
        # alpha has a copy-and-paste version; beta does not
        (self.root / ".claude" / "skills" / "alpha" / "references").mkdir()
        (self.root / ".claude" / "skills" / "alpha" / "references" / "paste-ready.md").write_text("# alpha, paste-ready\n", encoding="utf-8")
        self.out = self.root / "skills-index.json"
        self.page = self.root / "docs" / "skills-by-audience.md"

    def run_script(self, *args):
        r = subprocess.run([sys.executable, str(SCRIPT), str(self.root), *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
        return r.returncode, r.stdout + r.stderr

    def build(self):
        code, out = self.run_script()
        self.assertEqual(code, 0, out)
        return json.loads(self.out.read_text(encoding="utf-8"))

    def test_it_writes_a_sorted_index_with_one_entry_per_skill(self):
        data = self.build()
        self.assertEqual(data["schema"], 1)
        self.assertEqual([s["name"] for s in data["skills"]], ["alpha", "beta"])

    def test_each_entry_carries_the_frontmatter_facts(self):
        a = self.build()["skills"][0]
        self.assertEqual(a["description"], "Does alpha.")
        self.assertEqual(a["license"], "CC0-1.0")
        self.assertEqual(a["version"], "1.0.0")
        self.assertEqual(a["path"], ".claude/skills/alpha")

    def test_capabilities_are_split_into_a_clean_sorted_list_and_optional_ones_are_kept_apart(self):
        data = self.build()
        a, b = data["skills"]
        self.assertEqual(a["capabilities"], ["network", "python", "runs-code"])
        self.assertEqual(a["optional_capabilities"], [])
        self.assertEqual(b["capabilities"], ["python", "runs-code"])
        self.assertEqual(b["optional_capabilities"], ["browser"])

    def test_install_commands_name_the_skill_and_the_agents_and_never_include_a_secret_or_path(self):
        a = self.build()["skills"][0]
        self.assertEqual(a["install"]["script"], "python scripts/install_skill.py alpha --agent claude")
        self.assertEqual(a["install"]["gh"], "gh skill install senseiewok/cf-skills .claude/skills/alpha --agent claude-code")
        self.assertEqual(a["install"]["claude_plugin"], "/plugin install alpha@sensei-ewok-skills")

    def test_the_index_lists_each_agent_with_its_folders_and_its_gh_agent_id(self):
        agents = self.build()["agents"]
        self.assertEqual(agents["claude"], {"project": ".claude/skills", "user": ".claude/skills", "gh_agent": "claude-code"})
        self.assertEqual(agents["copilot"], {"project": ".github/skills", "user": ".copilot/skills", "gh_agent": "github-copilot"})
        self.assertEqual(agents["codex"]["gh_agent"], "codex")
        self.assertEqual(agents["qwen"]["project"], ".qwen/skills")
        self.assertIsNone(agents["windsurf"]["gh_agent"], "no gh agent id is documented for Windsurf")

    def test_the_output_is_deterministic_and_ends_with_a_newline(self):
        self.build()
        first = self.out.read_text(encoding="utf-8")
        self.build()
        self.assertEqual(first, self.out.read_text(encoding="utf-8"))
        self.assertTrue(first.endswith("\n"))
        self.assertNotIn(str(self.tmp), first, "no local path is written into the index")

    def test_check_passes_when_the_index_is_current_and_fails_when_it_is_stale_or_missing(self):
        code, out = self.run_script("--check")
        self.assertEqual(code, 1, "a missing index is stale: " + out)
        self.build()
        code, out = self.run_script("--check")
        self.assertEqual(code, 0, out)
        (self.root / ".claude" / "skills" / "alpha" / "SKILL.md").write_text(skill("alpha", "Changed.", aud="patients-families", level="base", cat="safe-ai-use"), encoding="utf-8")
        code, out = self.run_script("--check")
        self.assertEqual(code, 1, out)
        self.assertIn("skills-index.json", out)

    def test_check_never_writes(self):
        self.run_script("--check")
        self.assertFalse(self.out.exists())

    def test_a_skill_without_declared_capabilities_is_an_error_not_a_guess(self):
        p = self.root / ".claude" / "skills" / "alpha" / "SKILL.md"
        p.write_text(p.read_text(encoding="utf-8").replace('    capabilities: "network, runs-code, python"\n', ""), encoding="utf-8")
        code, out = self.run_script()
        self.assertEqual(code, 1, out)
        self.assertIn("alpha", out)
        self.assertIn("capabilities", out)
        self.assertFalse(self.out.exists(), "nothing is written when a skill is incomplete")

    def test_an_unknown_capability_word_is_reported(self):
        p = self.root / ".claude" / "skills" / "alpha" / "SKILL.md"
        p.write_text(p.read_text(encoding="utf-8").replace("network, runs-code, python", "network, teleportation"), encoding="utf-8")
        code, out = self.run_script()
        self.assertEqual(code, 1, out)
        self.assertIn("teleportation", out)

    def test_a_skill_without_a_skill_md_is_reported_not_a_crash(self):
        (self.root / ".claude" / "skills" / "empty").mkdir()
        code, out = self.run_script()
        self.assertEqual(code, 1, out)
        self.assertIn("empty", out)
        self.assertNotIn("Traceback", out)

    # ---- audience, level and category
    def edit_alpha(self, old, new):
        p = self.root / ".claude" / "skills" / "alpha" / "SKILL.md"
        s = p.read_text(encoding="utf-8")
        self.assertIn(old, s, "test setup")
        p.write_text(s.replace(old, new), encoding="utf-8")

    def section(self, page, heading):
        """The text of one '## heading' section of the generated page."""
        part = page.split("## " + heading + "\n", 1)[1]
        return part.split("\n## ", 1)[0]

    def test_each_entry_carries_audience_as_a_list_in_vocabulary_order_and_level_and_category(self):
        a, b = self.build()["skills"]
        self.assertEqual((a["audience"], a["level"], a["category"]), (["patients-families"], "base", "safe-ai-use"))
        self.assertEqual((b["audience"], b["level"], b["category"]), (["researchers", "builders"], "advanced", "tool-evaluation"),
                         "written 'builders, researchers'; listed in the fixed order")

    def test_an_unknown_or_missing_audience_level_or_category_is_an_error_and_nothing_is_written(self):
        cases = (
            ('audience: "patients-families"', 'audience: "parents"', "unknown audience 'parents'"),
            ('audience: "patients-families"', 'audience: ""', "missing metadata 'audience'"),
            ('    level: "base"\n', "", "missing metadata 'level'"),
            ('level: "base"', 'level: "expert"', "unknown level 'expert'"),
            ('category: "safe-ai-use"', 'category: "science"', "unknown category 'science'"),
        )
        for old, new, needle in cases:
            with self.subTest(needle=needle):
                self.setUp()
                self.edit_alpha(old, new)
                code, out = self.run_script()
                self.assertEqual(code, 1, out)
                self.assertIn(needle, out)
                self.assertIn("alpha", out)
                self.assertFalse(self.out.exists() or self.page.exists(), "nothing is written when a skill is incomplete")

    def test_the_page_lists_each_skill_under_each_of_its_audiences_and_nowhere_else(self):
        self.build()
        page = self.page.read_text(encoding="utf-8")
        self.assertIn("<!-- Generated file: do not edit by hand. Run python scripts/make_index.py. -->", page.split("\n## ", 1)[0],
                      "the header names the command that generates it")
        self.assertIn("`alpha`", self.section(page, "Patients and families"))
        self.assertNotIn("`beta`", self.section(page, "Patients and families"))
        for heading in ("Researchers", "Builders"):
            self.assertIn("`beta`", self.section(page, heading))
            self.assertNotIn("`alpha`", self.section(page, heading))
        self.assertIn("No skill for this group yet.", self.section(page, "Care teams"))

    def test_a_skill_with_two_audiences_appears_twice_and_one_with_one_appears_once(self):
        self.build()
        page = self.page.read_text(encoding="utf-8")
        self.assertEqual(page.count("[`beta`]"), 2)
        self.assertEqual(page.count("[`alpha`]"), 1)

    def page_row(self, name):
        return [ln for ln in self.page.read_text(encoding="utf-8").splitlines() if ln.startswith(f"| [`{name}`]")][0]

    def test_a_page_row_has_the_first_sentence_the_use_now_cell_level_and_category(self):
        self.build()
        row = self.page_row("beta")
        self.assertIn("| Does beta. | (install route only) | advanced | tool-evaluation |", row)
        self.assertNotIn("Then more", row, "only the first sentence")
        self.assertIn("(../.claude/skills/beta/SKILL.md)", row)

    def test_every_table_has_the_use_now_column(self):
        self.build()
        page = self.page.read_text(encoding="utf-8")
        for heading in ("Patients and families", "Researchers", "Builders"):
            with self.subTest(section=heading):
                self.assertIn("| Skill | What it does | Use it now, no install | Level | Category |", self.section(page, heading))

    def test_a_skill_with_a_paste_ready_file_links_it_and_one_without_is_labelled(self):
        self.build()
        self.assertIn("| [Use it now](../.claude/skills/alpha/references/paste-ready.md) |", self.page_row("alpha"))
        self.assertIn("| (install route only) |", self.page_row("beta"))
        self.assertNotIn("Use it now](", self.page_row("beta"))

    def test_the_page_opens_in_plain_words_and_keeps_the_install_route_for_a_builders_section_at_the_end(self):
        self.build()
        page = self.page.read_text(encoding="utf-8")
        head = page.split("\n## ", 1)[0]
        self.assertIn('A skill with a "Use it now" link needs no install.', head)
        self.assertIn("[Where to paste](paste-ready.md)", head)
        self.assertIn("not medical advice", head)
        self.assertNotIn("install.md", head, "the install route is not in the opening lines")
        self.assertNotIn("SKILL.md", head)
        last = page.rsplit("\n## ", 1)[1]
        self.assertTrue(last.startswith("For builders: install a skill in your agent\n"), "the builders section is last")
        self.assertIn("[install.md](install.md)", last)
        self.assertIn("python scripts/make_index.py --check", last)

    def test_patients_and_care_team_sections_open_with_the_no_install_line_and_the_others_do_not(self):
        opening = 'You do not need to install anything. Open the "Use it now" link, copy the box, and paste it into a new chat.'
        self.edit_alpha('audience: "patients-families"', 'audience: "patients-families, care-teams"')
        self.build()
        page = self.page.read_text(encoding="utf-8")
        for heading in ("Patients and families", "Care teams"):
            with self.subTest(section=heading):
                self.assertTrue(self.section(page, heading).lstrip("\n").startswith(opening + "\n"), self.section(page, heading))
        for heading in ("Researchers", "Builders"):
            with self.subTest(section=heading):
                self.assertNotIn(opening, self.section(page, heading))

    def test_an_empty_patients_section_says_so_without_the_no_install_line(self):
        self.edit_alpha('audience: "patients-families"', 'audience: "researchers"')
        self.build()
        section = self.section(self.page.read_text(encoding="utf-8"), "Patients and families")
        self.assertIn("No skill for this group yet.", section)
        self.assertNotIn("You do not need to install anything", section)

    def test_check_fails_when_a_paste_ready_file_is_added_and_the_page_was_not_rebuilt(self):
        self.build()
        d = self.root / ".claude" / "skills" / "beta" / "references"
        d.mkdir()
        (d / "paste-ready.md").write_text("# beta, paste-ready\n", encoding="utf-8")
        code, out = self.run_script("--check")
        self.assertEqual(code, 1, out)
        self.assertIn("docs/skills-by-audience.md", out)
        self.build()
        self.assertIn("[Use it now](../.claude/skills/beta/references/paste-ready.md)", self.page_row("beta"))

    # ---- metadata.summary: a plain one-line "What it does" for people
    SUMMARY = "Plain words for a parent: what alpha does."

    def add_alpha_summary(self, text):
        self.edit_alpha('    category: "safe-ai-use"\n', f'    category: "safe-ai-use"\n    summary: "{text}"\n')

    def test_the_summary_is_carried_into_the_index_and_is_empty_when_absent(self):
        self.add_alpha_summary(self.SUMMARY)
        a, b = self.build()["skills"]
        self.assertEqual(a["summary"], self.SUMMARY)
        self.assertEqual(b["summary"], "", "a skill without a summary gets an empty string, not a guess")

    def test_the_page_and_readme_use_the_summary_and_fall_back_to_the_first_sentence(self):
        (self.root / "README.md").write_text(README, encoding="utf-8")
        self.add_alpha_summary(self.SUMMARY)
        self.build()
        self.assertIn(f"| {self.SUMMARY} |", self.page_row("alpha"))
        self.assertNotIn("Does alpha.", self.page_row("alpha"), "the summary replaces the description's first sentence")
        self.assertIn("| Does beta. |", self.page_row("beta"), "no summary: the first sentence of the description")
        inner = (self.root / "README.md").read_text(encoding="utf-8").split("<!-- skills-table:start -->", 1)[1]
        self.assertIn(f"| [`alpha`](.claude/skills/alpha/SKILL.md) | {self.SUMMARY} | Patients and families |", inner)
        self.assertIn("| [`beta`](.claude/skills/beta/SKILL.md) | Does beta. | Researchers, Builders |", inner)

    def test_check_fails_when_a_summary_changes_and_the_page_was_not_rebuilt(self):
        self.build()
        self.add_alpha_summary(self.SUMMARY)
        code, out = self.run_script("--check")
        self.assertEqual(code, 1, out)
        self.assertIn("docs/skills-by-audience.md", out)

    def test_a_too_long_or_marked_up_summary_is_an_error_and_nothing_is_written(self):
        for text, needle in (("x" * 161, "161 characters"), ("Does <b>alpha</b>.", "angle brackets")):
            with self.subTest(needle=needle):
                self.setUp()
                self.add_alpha_summary(text)
                code, out = self.run_script()
                self.assertEqual(code, 1, out)
                self.assertIn("summary", out)
                self.assertIn(needle, out)
                self.assertFalse(self.out.exists() or self.page.exists(), "nothing is written when a summary is wrong")

    def test_a_summary_of_exactly_the_limit_is_accepted(self):
        self.add_alpha_summary("x" * 160)
        self.assertEqual(self.build()["skills"][0]["summary"], "x" * 160)

    def test_a_pipe_in_a_description_does_not_break_the_table(self):
        self.edit_alpha("Does alpha.", "Does a or b.")
        self.edit_alpha("Does a or b.", "Does a | b.")
        self.build()
        row = [ln for ln in self.page.read_text(encoding="utf-8").splitlines() if ln.startswith("| [`alpha`]")][0]
        self.assertIn("Does a \\| b.", row)

    def test_check_fails_on_a_stale_page_and_passes_after_regeneration(self):
        self.build()
        code, out = self.run_script("--check")
        self.assertEqual(code, 0, out)
        self.page.write_text(self.page.read_text(encoding="utf-8") + "hand edit\n", encoding="utf-8")
        code, out = self.run_script("--check")
        self.assertEqual(code, 1, out)
        self.assertIn("docs/skills-by-audience.md", out)
        self.assertNotIn("ERROR skills-index.json", out, "only the stale file is named")
        self.build()
        code, out = self.run_script("--check")
        self.assertEqual(code, 0, out)

    def test_check_fails_when_a_skills_audience_changes_and_the_page_was_not_rebuilt(self):
        self.build()
        self.edit_alpha('audience: "patients-families"', 'audience: "patients-families, care-teams"')
        code, out = self.run_script("--check")
        self.assertEqual(code, 1, out)
        self.assertIn("docs/skills-by-audience.md", out)

    def test_the_readme_table_is_written_between_the_markers_and_the_rest_is_kept(self):
        (self.root / "README.md").write_text(README, encoding="utf-8")
        self.build()
        text = (self.root / "README.md").read_text(encoding="utf-8")
        self.assertIn("Intro stays.", text)
        self.assertIn("After stays.", text)
        self.assertNotIn("old table", text)
        inner = text.split("<!-- skills-table:start -->", 1)[1].split("<!-- skills-table:end -->", 1)[0]
        self.assertIn("| Skill | What it does | For whom | Use it now, no install | Level |", inner)
        self.assertIn("| [`alpha`](.claude/skills/alpha/SKILL.md) | Does alpha. | Patients and families | "
                      "[Use it now](.claude/skills/alpha/references/paste-ready.md) | base |", inner)
        self.assertIn("| [`beta`](.claude/skills/beta/SKILL.md) | Does beta. | Researchers, Builders | (install route only) | advanced |", inner)

    def test_the_readme_keeps_its_own_line_endings(self):
        (self.root / "README.md").write_bytes(README.replace("\n", "\r\n").encode("utf-8"))
        self.build()
        raw = (self.root / "README.md").read_bytes()
        self.assertNotIn(b"\n", raw.replace(b"\r\n", b""), "every line end stays CRLF")

    def test_check_fails_on_a_stale_readme_table_and_passes_after_regeneration(self):
        (self.root / "README.md").write_text(README, encoding="utf-8")
        self.build()
        code, out = self.run_script("--check")
        self.assertEqual(code, 0, out)
        self.edit_alpha('level: "base"', 'level: "advanced"')
        code, out = self.run_script("--check")
        self.assertEqual(code, 1, out)
        self.assertIn("README.md", out)
        self.build()
        code, out = self.run_script("--check")
        self.assertEqual(code, 0, out)

    def test_a_readme_without_the_markers_is_an_error_and_is_left_alone(self):
        (self.root / "README.md").write_text("# Repo\n\nNo markers.\n", encoding="utf-8")
        code, out = self.run_script()
        self.assertEqual(code, 1, out)
        self.assertIn("skills-table:start", out)
        self.assertEqual((self.root / "README.md").read_text(encoding="utf-8"), "# Repo\n\nNo markers.\n")

    def test_check_never_writes_the_page_or_the_readme(self):
        (self.root / "README.md").write_text(README, encoding="utf-8")
        self.run_script("--check")
        self.assertFalse(self.page.exists())
        self.assertIn("old table", (self.root / "README.md").read_text(encoding="utf-8"))

    def test_a_missing_root_is_a_usage_error(self):
        r = subprocess.run([sys.executable, str(SCRIPT), str(self.tmp / "nowhere")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)

    def test_the_script_uses_no_network_or_process_modules(self):
        import ast
        tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                names.add(node.module.split(".")[0])
        self.assertFalse(names & {"socket", "urllib", "http", "requests", "subprocess", "ftplib", "smtplib"}, names)


if __name__ == "__main__":
    unittest.main()
