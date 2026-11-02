"""Unit tests for .claude/skills/complex-systems-monograph/scripts/monograph_verify.py.

Verifies the Living Executable Monograph and Companion verification engines against
positive cases, edge cases, and deterministic negative controls, while enforcing an
audit hook that forbids any network socket or subprocess creation.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = SKILL_ROOT / "scripts" / "monograph_verify.py"

spec = importlib.util.spec_from_file_location("monograph_verify", SCRIPT_PATH)
assert spec is not None and spec.loader is not None
monograph_verify = importlib.util.module_from_spec(spec)
sys.modules["monograph_verify"] = monograph_verify
spec.loader.exec_module(monograph_verify)


class MonographVerifyTests(unittest.TestCase):
    def test_self_check_passes_all_controls(self):
        res = monograph_verify.run_self_check()
        self.assertTrue(res["passed"], res)
        self.assertGreaterEqual(res["total_checks"], 5)
        self.assertEqual(res["passed_checks"], res["total_checks"])

    def test_verify_monograph_positive(self):
        doc = """
        # Structural Shell Monograph
        Edition: REV 1.0 | Published: 2026-10-20 | Redated: 2026-11-01
        
        ## Council Sign-Off Ledger
        - Claude Opus 5.5: Verified prose and clarity.
        - Gemini 4 Argon: Audited equations and parameters.
        - GPT-OSS 120B: Checked adversarial edge cases.
        - Deterministic Verification Kernel: Offline equilibrium checks passed.
        
        ## Act I: Historical Grounding & Discovery Milestones
        Historical evolution from Robert Hooke (1675) to Heinz Isler (1959).
        
        ## Act II: Governing Equations & Interactive Parameter Scrubbing
        Thrust line equation: y(x) = (H / w) * (cosh(w*x / H) - 1).
        
        ## Act III: The Multi-Lens Scientific Observatory
        Interactive Maxwell-Cremona reciprocal force diagram and 3D funicular surface.
        
        ## Act IV: Dual-Horizon Frontier Discovery & Research News
        Grounded in modern funicular optimization (DOI 10.1016/j.engstruct.2023.116542).
        """
        res = monograph_verify.verify_monograph_content(doc, "funicular_shell")
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["revision"], "REV 1.0")
        self.assertGreaterEqual(res["citation_count"], 1)

    def test_verify_monograph_catches_missing_acts(self):
        doc = """
        # Incomplete Monograph
        Edition: REV 1.0 | Published: 2026-11-01
        Claude Opus, Gemini Argon, GPT-OSS, Deterministic Verification Kernel.
        DOI 10.1000/182
        ## Act I: Historical Grounding
        History here.
        ## Act II: Governing Equations
        Equations here.
        """
        res = monograph_verify.verify_monograph_content(doc, "missing_acts")
        self.assertFalse(res["passed"])
        self.assertTrue(any("Missing required 4-Act" in f for f in res["findings"]))

    def test_verify_monograph_catches_unsafe_inner_html(self):
        doc = """
        # HTML Monograph
        Edition: REV 1.0 | Published: 2026-11-01
        Claude Opus, Gemini Argon, GPT-OSS, Deterministic Verification Kernel.
        DOI 10.1000/182
        ## Act I: Historical Grounding
        History.
        ## Act II: Governing Equations
        Math.
        ## Act III: The Scientific Observatory
        Plate.
        ## Act IV: Frontier Discovery
        Frontier.
        <script>
            plate.innerHTML = "<div>unsafe dynamic html</div>";
        </script>
        """
        res = monograph_verify.verify_monograph_content(doc, "unsafe_html")
        self.assertFalse(res["passed"])
        self.assertTrue(any(".innerHTML" in f for f in res["findings"]))

    def test_verify_monograph_catches_missing_council_seats(self):
        doc = """
        # Monograph with partial council
        Edition: REV 1.0 | Published: 2026-11-01
        - Claude Opus: Reviewed.
        DOI 10.1000/182
        ## Act I: Historical Grounding
        History.
        ## Act II: Governing Equations
        Math.
        ## Act III: The Scientific Observatory
        Plate.
        ## Act IV: Frontier Discovery
        Frontier.
        """
        res = monograph_verify.verify_monograph_content(doc, "partial_council")
        self.assertFalse(res["passed"])
        self.assertTrue(any("Council Ledger" in f for f in res["findings"]))

    def test_verify_companion_positive(self):
        companion = """---
name: my-companion-skill
description: "AI-agnostic companion skill for engineering analysis."
license: CC0-1.0
metadata:
    audience: "researchers, builders"
    level: "advanced"
    category: "math"
---

# My Companion Skill
Research, not medical advice. Scope and limitations apply.

## Governing Equations & Principles
Navier-Stokes and Darcy-Brinkman porous formulations.

```python
def check_porous_drag(mu, k, v):
    return (mu / k) * v
```
"""
        res = monograph_verify.verify_companion_content(companion, "companion_test")
        self.assertTrue(res["passed"], res)

    def test_verify_companion_catches_missing_metadata(self):
        companion = """---
name: missing-meta
description: "No metadata section."
license: CC0-1.0
---

# Body
Research, not medical advice.
## Governing Laws
Laws here.
```python
x = 1
```
"""
        res = monograph_verify.verify_companion_content(companion, "no_meta")
        self.assertFalse(res["passed"])
        self.assertTrue(any("metadata" in f for f in res["findings"]))

    def test_cli_verify_monograph(self):
        doc = """
        # CLI Monograph
        Edition: REV 1.0 | Published: 2026-11-01
        Claude Opus, Gemini Argon, GPT-OSS, Deterministic Verification Kernel.
        DOI 10.1000/182
        ## Act I: Historical Grounding
        Act 1.
        ## Act II: Governing Equations
        Act 2.
        ## Act III: The Scientific Observatory
        Act 3.
        ## Act IV: Frontier Discovery
        Act 4.
        """
        with tempfile.TemporaryDirectory() as tmp:
            doc_file = Path(tmp) / "monograph.md"
            doc_file.write_text(doc, encoding="utf-8")
            out_file = Path(tmp) / "out.json"
            code = monograph_verify.main([
                "verify-monograph",
                "--path", str(doc_file),
                "--json",
                "--json-out", str(out_file),
            ])
            self.assertEqual(code, 0)
            payload = json.loads(out_file.read_text(encoding="utf-8"))
            self.assertTrue(payload["passed"])

    def test_cli_missing_file_returns_2(self):
        code = monograph_verify.main(["verify-monograph", "--path", "nonexistent_file_path_xyz.md"])
        self.assertEqual(code, 2)

    def test_zero_network_and_zero_subprocess_audit_hook(self):
        events = []

        def hook(event, args):
            if event.startswith("socket.") or event.startswith("urllib.") or event == "subprocess.Popen":
                events.append((event, args))

        sys.addaudithook(hook)
        code = monograph_verify.main(["self-check", "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(events, [], f"Disallowed network or subprocess events detected: {events}")


if __name__ == "__main__":
    unittest.main()
