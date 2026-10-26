## Summary

<!-- 1-3 sentences describing the change -->

---

## Review Loop Record (`pr-review-loop`)

- **Review Tier**: `routine` | `elevated` | `full`
- **Reviewer(s)**:
  - Round 1: [Self-review or blind reviewer] — [Pass / Findings]
- **Findings Verification**: All findings verified against code with command output (or none raised).

---

## Deterministic Verification & Checks

```text
<!-- Paste output lines from this repository's checks run before opening this PR: -->
<!-- python scripts/check_repo.py -->
<!-- python scripts/make_index.py --check -->
<!-- python scripts/make_tested_grid.py --check -->
<!-- python scripts/pin_catalog.py --check -->
<!-- python -m unittest discover tests -->
<!-- cd .claude/skills/cf-evidence-loop && python -m pytest -q tests -->
```

---

## Provenance & Diff Metrics

- **Diff Size**: `+lines / -lines, N files`
- **Files Copied From Another Repo**: `none` <!-- or: list files with upstream commit SHA -->
- **Agent Instructions / Security Rules Changed**: `no` <!-- or: yes (requires full review tier) -->
- **Third-Party Dependencies / External Calls Added**: `none` <!-- or: list with rationale -->
