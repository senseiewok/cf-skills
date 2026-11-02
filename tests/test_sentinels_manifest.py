"""Tests for tasks/sentinels.cf-skills.json schedule manifest.

Standard library only: verifies that the sentinel manifest exists, conforms to the
sentinel schema, references existing repository watch paths and test directories,
and that every declared verification command executes deterministically with exit code 0.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "tasks" / "sentinels.cf-skills.json"


class SentinelsManifestTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(MANIFEST_PATH.is_file(), f"Manifest missing at {MANIFEST_PATH}")
        with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
            self.manifest = json.load(f)

    def test_top_level_schema(self):
        self.assertEqual(self.manifest.get("version"), 1)
        self.assertEqual(self.manifest.get("repository"), "senseiewok/cf-skills")
        self.assertTrue(bool(self.manifest.get("mission")), "Missing or empty mission statement")
        self.assertEqual(self.manifest.get("timezone"), "America/Los_Angeles")
        sentinels = self.manifest.get("sentinels")
        self.assertIsInstance(sentinels, dict)
        self.assertIn("cf-skills-verification-sentinel", sentinels)

    def test_sentinel_definition(self):
        sentinel = self.manifest["sentinels"]["cf-skills-verification-sentinel"]
        self.assertEqual(sentinel.get("canonical_lab_sentinel"), "cf-skills-verification-sentinel")
        self.assertEqual(sentinel.get("cron"), "35 * * * *")
        self.assertTrue(bool(sentinel.get("display_name")), "Missing display_name")
        self.assertTrue(bool(sentinel.get("description")), "Missing description")

        watch_paths = sentinel.get("watch_paths")
        self.assertIsInstance(watch_paths, list)
        self.assertGreater(len(watch_paths), 0)
        for wp in watch_paths:
            p = ROOT / wp
            self.assertTrue(p.exists(), f"Declared watch_path does not exist: {wp}")

        commands = sentinel.get("verification_commands")
        self.assertIsInstance(commands, list)
        self.assertGreater(len(commands), 0)

    def test_verification_command_paths(self):
        sentinel = self.manifest["sentinels"]["cf-skills-verification-sentinel"]
        commands = sentinel.get("verification_commands", [])

        for cmd in commands:
            tokens = shlex.split(cmd)
            self.assertGreater(len(tokens), 1)

            # If command runs a script directly: python scripts/xxx.py
            if len(tokens) >= 2 and tokens[0] == "python" and not tokens[1].startswith("-"):
                script_path = ROOT / tokens[1]
                self.assertTrue(script_path.is_file(), f"Script does not exist: {tokens[1]} in '{cmd}'")

            # If command runs unittest discovery: python -m unittest discover -s <dir> -p <pattern>
            if "-s" in tokens:
                s_idx = tokens.index("-s")
                self.assertLess(s_idx + 1, len(tokens))
                test_dir = ROOT / tokens[s_idx + 1]
                self.assertTrue(test_dir.is_dir(), f"Test directory does not exist: {tokens[s_idx + 1]} in '{cmd}'")

                pattern = "test_*.py"
                if "-p" in tokens:
                    p_idx = tokens.index("-p")
                    self.assertLess(p_idx + 1, len(tokens))
                    pattern = tokens[p_idx + 1]

                matching_files = list(test_dir.glob(pattern))
                self.assertGreater(
                    len(matching_files),
                    0,
                    f"No test files matched '{pattern}' in '{test_dir}' for command '{cmd}'",
                )

    def test_verification_commands_pass(self):
        sentinel = self.manifest["sentinels"]["cf-skills-verification-sentinel"]
        commands = sentinel.get("verification_commands", [])

        # Anti-recursion guard: if already running inside child verification test, return
        if os.environ.get("_SENTINELS_TEST_SUBPROCESS"):
            return

        env = os.environ.copy()
        env["_SENTINELS_TEST_SUBPROCESS"] = "1"

        for cmd in commands:
            tokens = shlex.split(cmd)
            # Avoid re-running the full top-level tests/ suite inside itself
            if "-s" in tokens:
                s_idx = tokens.index("-s")
                if s_idx + 1 < len(tokens) and tokens[s_idx + 1] == "tests":
                    continue

            if tokens[0] == "python":
                tokens[0] = sys.executable

            res = subprocess.run(
                tokens,
                cwd=str(ROOT),
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            self.assertEqual(
                res.returncode,
                0,
                f"Verification command failed (exit code {res.returncode}): {cmd}\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}",
            )
            self.assertNotIn("NO TESTS RAN", res.stderr)
            self.assertNotIn("NO TESTS RAN", res.stdout)


if __name__ == "__main__":
    unittest.main()
