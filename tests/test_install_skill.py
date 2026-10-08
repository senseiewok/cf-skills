"""Tests for scripts/install_skill.py: copy or link one skill folder into the folder an agent reads.
Each test builds a small repository and a project folder in a temporary directory and runs the script as a subprocess. HOME and USERPROFILE are pointed at
a temporary folder, so nothing outside the temporary directory is ever touched. By default the script next to this folder is tested; set INSTALL_SKILL_PATH to test another file.
Standard library only."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(os.environ.get("INSTALL_SKILL_PATH") or Path(__file__).resolve().parents[1] / "scripts" / "install_skill.py")


def skill_md(name, desc):
    return f'---\nname: {name}\ndescription: "{desc}"\nlicense: CC0-1.0\n---\n\n# {name}\n'


class InstallSkillTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="install-skill-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.repo = self.tmp / "repo"
        (self.repo / "scripts").mkdir(parents=True)
        shutil.copy(SCRIPT, self.repo / "scripts" / "install_skill.py")  # the script finds its repository from its own location
        for name, desc in (("alpha", "Does the alpha thing."), ("beta", "Does the beta thing.")):
            d = self.repo / ".claude" / "skills" / name
            (d / "scripts").mkdir(parents=True)
            (d / "references").mkdir()
            (d / "SKILL.md").write_text(skill_md(name, desc), encoding="utf-8")
            (d / "scripts" / "run.py").write_text("print('hello')\n", encoding="utf-8")
            (d / "references" / "notes.md").write_text("notes\n", encoding="utf-8")
            (d / "__pycache__").mkdir()
            (d / "__pycache__" / "x.pyc").write_bytes(b"\0")
        self.proj = self.tmp / "project"
        self.proj.mkdir()
        self.home = self.tmp / "home"
        self.home.mkdir()

    def run_script(self, *args, cwd=None):
        env = dict(os.environ, HOME=str(self.home), USERPROFILE=str(self.home))
        r = subprocess.run([sys.executable, str(self.repo / "scripts" / "install_skill.py"), *args], cwd=str(cwd or self.proj), env=env,
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        return r.returncode, r.stdout + r.stderr

    # ---- listing
    def test_list_shows_every_skill_with_its_description_and_exits_0(self):
        code, out = self.run_script("--list")
        self.assertEqual(code, 0, out)
        self.assertIn("alpha", out)
        self.assertIn("Does the alpha thing.", out)
        self.assertIn("beta", out)

    # ---- the default: Claude Code, project folder
    def test_default_copies_the_whole_skill_folder_into_the_projects_claude_skills(self):
        code, out = self.run_script("alpha")
        self.assertEqual(code, 0, out)
        dest = self.proj / ".claude" / "skills" / "alpha"
        self.assertTrue((dest / "SKILL.md").is_file(), out)
        self.assertTrue((dest / "scripts" / "run.py").is_file(), "scripts are copied, not only SKILL.md")
        self.assertTrue((dest / "references" / "notes.md").is_file())
        self.assertFalse((dest / "__pycache__").exists(), "bytecode caches are not copied")
        self.assertFalse((self.proj / ".claude" / "skills" / "beta").exists(), "only the named skill")

    def test_it_prints_where_it_wrote_and_how_to_check_and_never_runs_the_skills_scripts(self):
        code, out = self.run_script("alpha")
        self.assertEqual(code, 0, out)
        self.assertIn(str(self.proj / ".claude" / "skills" / "alpha"), out.replace("\\\\", "\\"))
        self.assertIn("/skills", out)
        self.assertNotIn("hello", out, "the skill's own script is never run")
        self.assertRegex(out.lower(), r"read .*skill\.md|read the skill")

    # ---- agents and scopes
    def test_each_agent_gets_its_documented_project_folder(self):
        cases = {"claude": ".claude/skills", "copilot": ".github/skills", "codex": ".agents/skills", "gemini": ".agents/skills", "cursor": ".agents/skills",
                 "amp": ".agents/skills", "opencode": ".agents/skills", "goose": ".agents/skills", "windsurf": ".agents/skills", "qwen": ".qwen/skills"}
        for agent, rel in cases.items():
            with self.subTest(agent=agent):
                proj = self.tmp / f"p-{agent}"
                proj.mkdir(exist_ok=True)
                code, out = self.run_script("alpha", "--agent", agent, cwd=proj)
                self.assertEqual(code, 0, out)
                self.assertTrue((proj / rel / "alpha" / "SKILL.md").is_file(), f"{agent}: {rel}")

    def test_user_scope_goes_under_the_home_folder(self):
        cases = {"claude": ".claude/skills", "copilot": ".copilot/skills", "codex": ".agents/skills", "qwen": ".qwen/skills"}
        for agent, rel in cases.items():
            with self.subTest(agent=agent):
                code, out = self.run_script("alpha", "--agent", agent, "--scope", "user")
                self.assertEqual(code, 0, out)
                self.assertTrue((self.home / rel / "alpha" / "SKILL.md").is_file(), f"{agent}: ~/{rel}")
        self.assertFalse((self.proj / ".claude").exists(), "a user-scope install writes nothing into the project")

    def test_an_unknown_agent_is_a_usage_error_that_lists_the_known_ones(self):
        code, out = self.run_script("alpha", "--agent", "nonesuch")
        self.assertEqual(code, 2, out)
        self.assertIn("claude", out)
        self.assertIn("codex", out)
        self.assertFalse((self.proj / ".claude").exists())

    def test_dest_overrides_the_folder(self):
        target = self.tmp / "custom"
        code, out = self.run_script("alpha", "--dest", str(target))
        self.assertEqual(code, 0, out)
        self.assertTrue((target / "alpha" / "SKILL.md").is_file())
        self.assertFalse((self.proj / ".claude").exists())

    # ---- safety
    def test_an_unknown_skill_name_is_refused_and_names_the_known_ones(self):
        code, out = self.run_script("gamma")
        self.assertEqual(code, 2, out)
        self.assertIn("alpha", out)
        self.assertFalse((self.proj / ".claude").exists())

    def test_names_that_try_to_leave_the_skills_folder_are_refused(self):
        for bad in ("..", "../scripts", "alpha/../beta", "skills", "/etc"):
            with self.subTest(bad=bad):
                code, out = self.run_script(bad)
                self.assertIn(code, (1, 2), out)
                self.assertFalse((self.proj / ".claude").exists())

    def test_an_existing_install_is_not_overwritten_without_force(self):
        self.run_script("alpha")
        marker = self.proj / ".claude" / "skills" / "alpha" / "MINE.txt"
        marker.write_text("local edit\n", encoding="utf-8")
        code, out = self.run_script("alpha")
        self.assertEqual(code, 1, out)
        self.assertIn("--force", out)
        self.assertTrue(marker.exists(), "the existing folder is untouched")
        code, out = self.run_script("alpha", "--force")
        self.assertEqual(code, 0, out)
        self.assertFalse(marker.exists(), "--force replaces the folder with a clean copy")
        self.assertTrue((self.proj / ".claude" / "skills" / "alpha" / "SKILL.md").is_file())

    def test_dry_run_writes_nothing_and_says_what_it_would_do(self):
        code, out = self.run_script("alpha", "--dry-run")
        self.assertEqual(code, 0, out)
        self.assertFalse((self.proj / ".claude").exists())
        self.assertIn("would", out.lower())
        self.assertIn("alpha", out)

    def test_the_script_never_runs_or_imports_anything_from_the_skill_and_uses_no_network(self):
        import ast
        tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                names.add(node.module.split(".")[0])
        self.assertFalse(names & {"socket", "urllib", "http", "requests", "subprocess", "ftplib", "smtplib", "runpy", "importlib"}, names)

    # ---- linking
    def symlinks_refused_for_privilege(self):
        """True only when this OS refuses a folder link for lack of privilege (Windows error 1314); any other failure is not an excuse."""
        probe = self.tmp / "probe-link"
        try:
            probe.symlink_to(self.repo, target_is_directory=True)
        except OSError as exc:
            if getattr(exc, "winerror", None) == 1314:
                return True
            raise
        probe.unlink()
        return False

    def test_link_makes_a_working_folder_link_to_the_skill(self):
        if self.symlinks_refused_for_privilege():
            self.skipTest("this Windows account lacks the privilege to create symbolic links (error 1314)")
        code, out = self.run_script("alpha", "--link")
        dest = self.proj / ".claude" / "skills" / "alpha"
        self.assertEqual(code, 0, out)
        self.assertTrue(dest.is_symlink(), f"no link was created: {out}")
        self.assertEqual(dest.resolve(), (self.repo / ".claude" / "skills" / "alpha").resolve())
        self.assertTrue(dest.is_dir(), "the link does not open as a folder")
        self.assertTrue((dest / "SKILL.md").is_file())
        self.assertTrue((dest / "scripts" / "run.py").is_file())

    def test_link_without_the_privilege_says_why_in_plain_words_and_leaves_nothing(self):
        if not self.symlinks_refused_for_privilege():
            self.skipTest("this system allows symbolic links; the refusal path cannot be reached")
        code, out = self.run_script("alpha", "--link")
        dest = self.proj / ".claude" / "skills" / "alpha"
        self.assertEqual(code, 1, out)
        self.assertIn("could not create symlink for alpha", out)
        self.assertIn("Developer Mode", out)
        self.assertIn("without --link", out)
        self.assertFalse(dest.exists() or dest.is_symlink(), "a failed link leaves nothing half-made")

    # ---- output
    def test_install_all_copies_every_skill(self):
        code, out = self.run_script("--all")
        self.assertEqual(code, 0, out)
        for name in ("alpha", "beta"):
            self.assertTrue((self.proj / ".claude" / "skills" / name / "SKILL.md").is_file(), name)

    def test_no_arguments_is_a_usage_error_with_help(self):
        code, out = self.run_script()
        self.assertEqual(code, 2, out)
        self.assertIn("usage", out.lower())


class HowToInstallTests(InstallSkillTests):
    """--how: what a skill can do, and the ways to install it that this machine can actually use (the GitHub CLI is offered only when it is found)."""

    INDEX = {"schema": 1, "repository": "senseiewok/cf-skills", "marketplace": "sensei-ewok-skills",
             "skills": [{"name": "alpha", "description": "Does the alpha thing.", "license": "CC0-1.0", "version": "1.0.0", "path": ".claude/skills/alpha",
                         "capabilities": ["network", "python", "runs-code"], "optional_capabilities": ["browser"],
                         "install": {"script": "python scripts/install_skill.py alpha --agent claude", "gh": "gh skill install senseiewok/cf-skills .claude/skills/alpha --agent claude-code",
                                     "claude_plugin": "/plugin install alpha@sensei-ewok-skills"}}],
             "agents": {"claude": {"project": ".claude/skills", "user": ".claude/skills", "gh_agent": "claude-code"},
                        "copilot": {"project": ".github/skills", "user": ".copilot/skills", "gh_agent": "github-copilot"},
                        "windsurf": {"project": ".agents/skills", "user": ".agents/skills", "gh_agent": None}}}

    def setUp(self):
        super().setUp()
        import json
        (self.repo / "skills-index.json").write_text(json.dumps(self.INDEX), encoding="utf-8")
        self.bin_with = self.tmp / "bin-with"
        self.bin_with.mkdir()
        (self.bin_with / ("gh.cmd" if os.name == "nt" else "gh")).write_text("@echo off\n" if os.name == "nt" else "#!/bin/sh\n", encoding="utf-8")
        if os.name != "nt":
            (self.bin_with / "gh").chmod(0o755)
        self.bin_without = self.tmp / "bin-without"
        self.bin_without.mkdir()

    def how(self, *args, path_dir):
        env = dict(os.environ, HOME=str(self.home), USERPROFILE=str(self.home), PATH=str(path_dir), PATHEXT=".COM;.EXE;.BAT;.CMD")
        r = subprocess.run([sys.executable, str(self.repo / "scripts" / "install_skill.py"), "--how", *args], cwd=str(self.proj), env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
        return r.returncode, r.stdout + r.stderr

    def test_it_says_in_plain_words_what_the_skill_can_do(self):
        code, out = self.how("alpha", path_dir=self.bin_without)
        self.assertEqual(code, 0, out)
        self.assertIn("alpha", out)
        low = out.lower()
        self.assertIn("internet", low)          # network
        self.assertIn("python", low)
        self.assertRegex(low, r"scripts.*(read|review)")  # runs-code: read them first
        self.assertIn("browser", low)            # the optional capability is named as optional
        self.assertIn("optional", low)

    def test_the_script_option_is_always_offered_with_the_chosen_agent(self):
        code, out = self.how("alpha", "--agent", "copilot", path_dir=self.bin_without)
        self.assertEqual(code, 0, out)
        self.assertIn("python scripts/install_skill.py alpha --agent copilot", out)

    def test_the_github_cli_is_offered_only_when_it_is_found_and_the_agent_has_an_id(self):
        code, out = self.how("alpha", "--agent", "claude", path_dir=self.bin_with)
        self.assertEqual(code, 0, out)
        self.assertIn("gh skill install senseiewok/cf-skills .claude/skills/alpha --agent claude-code", out)
        code, out = self.how("alpha", "--agent", "copilot", path_dir=self.bin_with)
        self.assertIn("--agent github-copilot", out)
        code, out = self.how("alpha", "--agent", "claude", path_dir=self.bin_without)
        self.assertNotIn("gh skill install", out)
        self.assertIn("GitHub CLI", out)
        code, out = self.how("alpha", "--agent", "windsurf", path_dir=self.bin_with)
        self.assertNotIn("gh skill install", out, "no gh agent id is documented for this agent")

    def test_the_claude_plugin_route_is_offered_for_claude_only(self):
        code, out = self.how("alpha", "--agent", "claude", path_dir=self.bin_without)
        self.assertIn("/plugin marketplace add senseiewok/cf-skills", out)
        self.assertIn("/plugin install alpha@sensei-ewok-skills", out)
        code, out = self.how("alpha", "--agent", "copilot", path_dir=self.bin_without)
        self.assertNotIn("/plugin install", out)

    def test_it_points_at_the_prompt_page_and_runs_nothing(self):
        code, out = self.how("alpha", path_dir=self.bin_with)
        self.assertIn("docs/prompts.md", out)
        self.assertFalse((self.proj / ".claude").exists(), "--how writes nothing")

    def test_an_unknown_skill_or_agent_is_a_usage_error_and_a_missing_index_is_explained(self):
        code, out = self.how("gamma", path_dir=self.bin_without)
        self.assertEqual(code, 2, out)
        code, out = self.how("alpha", "--agent", "nonesuch", path_dir=self.bin_without)
        self.assertEqual(code, 2, out)
        (self.repo / "skills-index.json").unlink()
        code, out = self.how("alpha", path_dir=self.bin_without)
        self.assertEqual(code, 1, out)
        self.assertIn("make_index.py", out)


if __name__ == "__main__":
    unittest.main()
