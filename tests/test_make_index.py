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
---

# {name}
"""


class MakeIndexTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="make-index-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.root = self.tmp / "repo"
        for name, desc, version, caps, opt in (("beta", "Does beta.", "2.0.0", "runs-code, python", "browser"), ("alpha", "Does alpha.", "1.0.0", "network, runs-code, python", "")):
            d = self.root / ".claude" / "skills" / name
            d.mkdir(parents=True)
            (d / "SKILL.md").write_text(SKILL.format(name=name, desc=desc, version=version, caps=caps, opt=opt), encoding="utf-8")
        self.out = self.root / "skills-index.json"

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
        (self.root / ".claude" / "skills" / "alpha" / "SKILL.md").write_text(SKILL.format(name="alpha", desc="Changed.", version="1.0.0", caps="python", opt=""), encoding="utf-8")
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
