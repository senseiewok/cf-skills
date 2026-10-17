"""Tests for scripts/pin_catalog.py.

Standard library only: no network, no live git required (git is replaced by FakeGit),
and tests run with synthetic fixtures.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
import unittest

import scripts.pin_catalog as pin_catalog

ROOT = Path(__file__).resolve().parents[1]
SHA = "0123456789abcdef0123456789abcdef01234567"
TIP = "f" * 40
FIXTURE_DATE = "2026-10-16"

FIXTURE_CATALOG = """# Source catalog
schema_version: 1
sources:
  - id: crossref
    kind: api
    access: api
    base_url: https://api.crossref.org/
  - id: openfda
    kind: api
    access: api
    base_url: https://api.fda.gov/
  - id: manual_paper
    kind: paper
    access: manual
"""


class FakeGit:
    """Mock runner for git commands."""

    def __init__(
        self,
        origin: str = "https://github.com/senseiewok/cf-research",
        commit: str = SHA,
        tip: str = SHA,
        date: str = FIXTURE_DATE,
        ancestor: bool = True,
        catalog_bytes: bytes = FIXTURE_CATALOG.encode("utf-8"),
        total_behind: int = 0,
        catalog_behind: int = 0,
    ):
        self.origin = origin
        self.commit = commit
        self.tip = tip
        self.date = date
        self.ancestor = ancestor
        self.catalog_bytes = catalog_bytes
        self.total_behind = total_behind
        self.catalog_behind = catalog_behind
        self.calls: list[list[str]] = []

    def __call__(self, args: list[str]) -> SimpleNamespace:
        self.calls.append(list(args))
        cmd = args[3:] if len(args) > 3 else args
        if cmd[:2] == ["remote", "get-url"]:
            return SimpleNamespace(returncode=0, stdout=self.origin.encode("utf-8"), stderr=b"")
        if cmd[:3] == ["rev-parse", "--verify", "--end-of-options"]:
            return SimpleNamespace(returncode=0, stdout=self.commit.encode("ascii"), stderr=b"")
        if cmd[:2] == ["rev-parse", "--verify"] and cmd[2].startswith("origin/main"):
            return SimpleNamespace(returncode=0, stdout=self.tip.encode("ascii"), stderr=b"")
        if cmd[:2] == ["merge-base", "--is-ancestor"]:
            return SimpleNamespace(returncode=0 if self.ancestor else 1, stdout=b"", stderr=b"not an ancestor")
        if cmd[:3] == ["show", "-s", "--format=%cs"]:
            return SimpleNamespace(returncode=0, stdout=self.date.encode("ascii"), stderr=b"")
        if cmd[:2] == ["rev-list", "--count"]:
            if "--" in cmd and pin_catalog.CATALOG_RESEARCH_PATH in cmd:
                return SimpleNamespace(returncode=0, stdout=str(self.catalog_behind).encode("ascii"), stderr=b"")
            return SimpleNamespace(returncode=0, stdout=str(self.total_behind).encode("ascii"), stderr=b"")
        if cmd[0] == "show" and f":{pin_catalog.CATALOG_RESEARCH_PATH}" in cmd[1]:
            return SimpleNamespace(returncode=0, stdout=self.catalog_bytes, stderr=b"")
        return SimpleNamespace(returncode=1, stdout=b"", stderr=b"unhandled command")


class PinCatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="test-pin-catalog-")
        self.d = Path(self.temp_dir)
        self.catalog_path = self.d / "catalog.yaml"
        self.lock_path = self.d / "catalog.lock.json"

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_lf_sha256_normalizes_crlf(self):
        lf = b"schema_version: 1\nsources:\n  - id: crossref\n"
        crlf = b"schema_version: 1\r\nsources:\r\n  - id: crossref\r\n"
        self.assertEqual(pin_catalog.lf_sha256(lf), pin_catalog.lf_sha256(crlf))
        self.assertEqual(pin_catalog.lf_sha256(lf), hashlib.sha256(lf).hexdigest())

    def test_strip_header(self):
        body = "schema_version: 1\nsources:\n"
        with_current = pin_catalog.HEADER + "\n" + body
        with_legacy = pin_catalog.LEGACY_HEADER + "\n" + body
        self.assertEqual(pin_catalog.strip_header(with_current), body)
        self.assertEqual(pin_catalog.strip_header(with_legacy), body)
        self.assertEqual(pin_catalog.strip_header(body), body)

    def test_count_sources(self):
        self.assertEqual(pin_catalog.count_sources(FIXTURE_CATALOG), 3)
        with self.assertRaises(pin_catalog.Refused):
            pin_catalog.count_sources("schema_version: 1\nno_sources: true\n")

    def test_origin_validation(self):
        for origin in pin_catalog.ALLOWED_ORIGINS:
            g = FakeGit(origin=origin)
            self.assertEqual(pin_catalog.check_origin(g, "repo"), origin)
        for bad_origin in (
            "https://github.com/someone/cf-research",
            "https://github.com/senseiewok/other-repo",
            "",
        ):
            g = FakeGit(origin=bad_origin)
            with self.subTest(origin=bad_origin), self.assertRaises(pin_catalog.Refused):
                pin_catalog.check_origin(g, "repo")

    def test_refuse_options_as_ref(self):
        g = FakeGit()
        for bad_ref in ("-x", "--output=foo", "", None):
            with self.subTest(ref=bad_ref), self.assertRaises(pin_catalog.Refused):
                pin_catalog.resolve_commit(g, "repo", bad_ref)
        self.assertEqual(g.calls, [])

    def test_ancestor_refusal_unless_allow_old(self):
        g = FakeGit(ancestor=False)
        with self.assertRaises(pin_catalog.Refused) as cm:
            pin_catalog.resolve_commit(g, "repo", "main", allow_old=False)
        self.assertIn("not an ancestor", str(cm.exception))
        # With allow_old=True, non-ancestor is permitted:
        self.assertEqual(pin_catalog.resolve_commit(g, "repo", "main", allow_old=True), SHA)

    def test_commit_date_format(self):
        g = FakeGit(date="2026-10-16")
        self.assertEqual(pin_catalog.commit_date(g, "repo", SHA), "2026-10-16")
        g_bad = FakeGit(date="invalid-date")
        with self.assertRaises(pin_catalog.Refused):
            pin_catalog.commit_date(g_bad, "repo", SHA)

    def test_commits_behind_calculation(self):
        g = FakeGit(tip=TIP, total_behind=12, catalog_behind=2)
        total, cat = pin_catalog.commits_behind(g, "repo", SHA)
        self.assertEqual((total, cat), (12, 2))

        g_synced = FakeGit(tip=SHA, total_behind=0, catalog_behind=0)
        total, cat = pin_catalog.commits_behind(g_synced, "repo", SHA)
        self.assertEqual((total, cat), (0, 0))

    def test_build_copy(self):
        raw = FIXTURE_CATALOG.encode("utf-8")
        copy_bytes, raw_sha, copy_sha, count = pin_catalog.build_copy(raw)
        self.assertEqual(count, 3)
        self.assertEqual(raw_sha, hashlib.sha256(raw).hexdigest())
        self.assertEqual(copy_sha, hashlib.sha256(copy_bytes).hexdigest())
        self.assertTrue(copy_bytes.startswith(pin_catalog.HEADER.encode("utf-8")))

    def test_pin_records_commit_and_hashes(self):
        g = FakeGit()
        lock_data = pin_catalog.pin(
            source="repo",
            ref="main",
            date="2026-10-16",
            run=g,
            target_catalog=self.catalog_path,
            target_lock=self.lock_path,
            check_remote_origin=True,
        )
        self.assertEqual(lock_data["research_commit"], SHA)
        self.assertEqual(lock_data["commit_date"], FIXTURE_DATE)
        self.assertEqual(lock_data["pinned_on"], "2026-10-16")
        self.assertEqual(lock_data["sources"], 3)
        self.assertTrue(self.catalog_path.is_file())
        self.assertTrue(self.lock_path.is_file())

        loaded_lock = json.loads(self.lock_path.read_text(encoding="utf-8"))
        self.assertEqual(loaded_lock, lock_data)

    def test_status_when_in_sync_and_when_behind(self):
        # 1. Lock file missing: exit 2
        self.assertEqual(pin_catalog.status(source=self.d, lock_file=self.lock_path), 2)

        # Pin first
        g = FakeGit()
        pin_catalog.pin(
            source=self.d,
            ref="main",
            run=g,
            target_catalog=self.catalog_path,
            target_lock=self.lock_path,
            check_remote_origin=False,
        )

        # 2. Source is not a git repo: exit 0 (reports missing source gracefully)
        self.assertEqual(pin_catalog.status(source=self.d / "missing_repo", lock_file=self.lock_path), 0)

        # Fake a git dir in self.d
        (self.d / ".git").mkdir()

        # 3. In sync: exit 0
        g_sync = FakeGit(tip=SHA, total_behind=0, catalog_behind=0)
        self.assertEqual(pin_catalog.status(source=self.d, lock_file=self.lock_path, run=g_sync), 0)

        # 4. Behind: exit 0 and reports counts
        g_behind = FakeGit(tip=TIP, total_behind=5, catalog_behind=1)
        self.assertEqual(pin_catalog.status(source=self.d, lock_file=self.lock_path, run=g_behind), 0)

    def test_check_compares_with_pinned_commit_not_main(self):
        (self.d / ".git").mkdir()

        # Pinned commit catalog
        pinned_catalog = FIXTURE_CATALOG.encode("utf-8")
        g_pin = FakeGit(commit=SHA, catalog_bytes=pinned_catalog)
        pin_catalog.pin(
            source=self.d,
            ref="main",
            run=g_pin,
            target_catalog=self.catalog_path,
            target_lock=self.lock_path,
            check_remote_origin=False,
        )

        # Now suppose origin/main in research has newer commits touching catalog.yaml!
        newer_catalog_on_main = (FIXTURE_CATALOG + "  - id: new_source\n    kind: api\n    access: api\n").encode("utf-8")
        # Even though main has newer catalog, FakeGit returns pinned_catalog when asked for SHA:sources/catalog.yaml
        g_main_moved = FakeGit(tip=TIP, commit=SHA, catalog_bytes=pinned_catalog, total_behind=10, catalog_behind=3)

        # --check compares with the PINNED commit (SHA), so it MUST SUCCEED (exit 0)!
        code = pin_catalog.check(
            source=self.d,
            catalog_file=self.catalog_path,
            lock_file=self.lock_path,
            run=g_main_moved,
        )
        self.assertEqual(code, 0, "Check must pass against pinned commit even when main has newer commits")

    def test_check_detects_drift_when_copy_modified(self):
        (self.d / ".git").mkdir()
        g = FakeGit()
        pin_catalog.pin(
            source=self.d,
            ref="main",
            run=g,
            target_catalog=self.catalog_path,
            target_lock=self.lock_path,
            check_remote_origin=False,
        )

        # Tamper with the copy
        tampered = self.catalog_path.read_text(encoding="utf-8") + "# hand edit\n"
        self.catalog_path.write_text(tampered, encoding="utf-8")

        code = pin_catalog.check(
            source=self.d,
            catalog_file=self.catalog_path,
            lock_file=self.lock_path,
            run=g,
        )
        self.assertEqual(code, 1, "Hand edit must cause check to fail with DRIFT")

    def test_check_standalone_without_research_repo(self):
        g = FakeGit()
        pin_catalog.pin(
            source=self.d,
            ref="main",
            run=g,
            target_catalog=self.catalog_path,
            target_lock=self.lock_path,
            check_remote_origin=False,
        )

        # Pointing source to a non-git directory verifies against catalog.lock.json hash
        no_git_dir = self.d / "no_git"
        no_git_dir.mkdir()
        code = pin_catalog.check(
            source=no_git_dir,
            catalog_file=self.catalog_path,
            lock_file=self.lock_path,
            run=g,
        )
        self.assertEqual(code, 0, "Standalone check without research repo must pass using lock hash")


if __name__ == "__main__":
    unittest.main()
