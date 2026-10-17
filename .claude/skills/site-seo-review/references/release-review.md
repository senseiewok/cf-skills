# Release review: `site-seo-review` (Tasks T-0083 and T-0092)

Date: 2026-10-16  
Repository: `senseiewok/cf-skills`  
Review Tier: Elevated / Release Review  
Status: Passed automated gates, frontier challenger review, and defect remediation verification; awaiting final human maintainer sign-off and licence confirmation.

---

## 1. Automated Checks and Test Matrix

- **Repository integrity**: `python scripts/check_repo.py` passed (`ok`, exit code 0).
- **Standard-library checker test suite** (run from `.claude/skills/site-seo-review/`): `python tests/verify_checker.py scripts/seo_audit.py` passed 121 tests (120 passed, 1 skipped).
- **Test discovery** (run from `.claude/skills/site-seo-review/`): `python -m unittest discover -s tests -v` ran 121 tests with zero failures or errors.
- **Python compatibility**:
  - Python 3.13: Ran 121 tests cleanly on Windows (skipped 1 symlink test requiring elevated symlink privileges).
  - Python 3.9: Checked by syntax only via `test_source_is_python_3_9_syntax` (parses with `ast.parse(..., feature_version=(3, 9))`, checks `from __future__ import annotations`, and confirms stdlib-only imports; not runtime-executed on a 3.9 interpreter).
- **Host isolation**: Audit hooks in `TestSideEffects` assert zero sockets, zero child processes, zero file writes outside `--json-out`, and zero process executions.

---

## 2. Frontier Challenger Review (Google Gemini Family / Argon)

- **Reviewer**: Argon (`pro` model, Google Gemini family).
- **Focus**: `SKILL.md`, `references/health-sites.md`, `references/checklist.md`, and `references/structured-data.md` evaluated for overclaims, medical advice, and ranking guarantees.
- **Findings**:
  - **Zero ranking promises**: The skill explicitly and repeatedly disavows ranking and traffic guarantees.
  - **Zero medical advice**: Health sites section strictly mandates *"Research, not medical advice"*, forbids treatment/cure promises, and excludes patient eligibility claims.
  - **Structured data honesty**: Medical types (`MedicalCondition`, `MedicalWebPage`, `Drug`) are prohibited unless the publisher is an authentic clinical authority.
- **Challenger Verdict**: **PASS** (zero overclaims detected, boundaries intact).

---

## 3. SEO008 Defect Documentation and Fix (Task T-0092)

- **Defect Description**:
  When `--base-url` was omitted during an audit and an absolute canonical URL was supplied in `index.html` (for example, `<link rel="canonical" href="http://example.com/foo">`), the checker previously guarded canonical equality behind `is_abs and base_url`. As a consequence, without a base URL, the checker skipped canonical mismatch verification and failed to report `SEO008`.
- **Discovered By**:
  The local reviewer, 3 of 8 runs.
- **Fix**:
  In `scripts/seo_audit.py` (`audit_page` canonical check), `sp = urlsplit(canon)` is evaluated:
  - If `is_abs and base_url`: verifies exact equality `canon == expected`.
  - Otherwise (`base_url` absent or relative/non-base absolute): verifies that `sp.path == url_path`. If `sp.path != url_path`, reports `SEO008` error (`canonical path {sp.path} differs from URL path {url_path}`).
- **Verification**:
  - 4 unit tests in `TestCanonicalWithoutBase` in `tests/test_seo_audit_extra.py` test absolute canonicals without `--base-url` (matching path passes, mismatching path fails with `SEO008`).
  - Reproduction (`index.html`, canonical `http://example.com/foo`, no base, `--json`) cleanly reports `SEO008`.
  - Full suite passes 121 tests.

---

## 4. Remaining Human Deliverables

Per acceptance criteria for T-0083 and T-0092:
- [ ] Human maintainer reads `SKILL.md`, references, and `scripts/seo_audit.py`.
- [ ] Human maintainer confirms the licence (CC0-1.0) and approves release.
