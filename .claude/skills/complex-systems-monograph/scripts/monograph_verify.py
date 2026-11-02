#!/usr/bin/env python3
"""scripts/monograph_verify.py -- Offline Living Executable Monograph and Companion Verifier.

Pure Python standard library (3.9+) offline verifier for Living Executable Monographs
and downloadable AI-agnostic SKILL.md companions:
1. verify-monograph: Validates 4-Act structure, REV X.Y edition lineage, 4-seat council ledger,
   DOI/PMID/NCT citation grounding, and zero .innerHTML safety.
2. verify-companion: Validates Agent Skills YAML frontmatter, governing equations, offline
   verification logic, and scope/safety boundaries.
3. self-check: Runs built-in positive cases and poisoned negative controls across both engines.

Standard library only; zero network calls; zero subprocess calls; writes no files unless --json-out is given.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


REV_REGEX = re.compile(r"REV\s+[0-9]+\.[0-9]+", re.IGNORECASE)
DATE_REGEX = re.compile(r"\b(19|20)\d{2}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])\b")
CITATION_REGEX = re.compile(r"\b(10\.\d{4,9}/[-._;()/:A-Za-z0-9]+|PMID\s*:\s*\d+|NCT\d{8}|arXiv:\d{4}\.\d{4,5})\b", re.IGNORECASE)

COUNCIL_SEATS = [
    "Claude Opus",
    "Gemini Argon",
    "GPT-OSS",
    "Deterministic Verification Kernel",
]

ACT_MARKERS = [
    ("Act I", re.compile(r"(Act\s+I\b|Historical Grounding)", re.IGNORECASE)),
    ("Act II", re.compile(r"(Act\s+II\b|Governing Equation)", re.IGNORECASE)),
    ("Act III", re.compile(r"(Act\s+III\b|Observatory|Scientific Plate)", re.IGNORECASE)),
    ("Act IV", re.compile(r"(Act\s+IV\b|Frontier Discovery|Research News)", re.IGNORECASE)),
]


def verify_monograph_content(text: str, filename: str = "monograph") -> Dict[str, Any]:
    """Verify an HTML or Markdown monograph against the Living Monograph specification."""
    findings: List[str] = []
    
    # 1. 4-Act Structure
    missing_acts = []
    for act_name, pattern in ACT_MARKERS:
        if not pattern.search(text):
            missing_acts.append(act_name)
    if missing_acts:
        findings.append(f"Missing required 4-Act structural sections: {', '.join(missing_acts)}")

    # 2. Living Dated Edition (REV X.Y)
    rev_match = REV_REGEX.search(text)
    if not rev_match:
        findings.append("Missing Living Edition revision string (expected format: 'REV X.Y', e.g. 'REV 1.0')")
    
    # 3. Publication and Redated Timestamps
    dates_found = DATE_REGEX.findall(text)
    if len(dates_found) < 1:
        findings.append("Missing ISO 8601 publication date timestamp (YYYY-MM-DD)")

    # 4. 4-Seat Multi-Lineage Council Ledger
    missing_seats = []
    text_lower = text.lower()
    if "opus" not in text_lower:
        missing_seats.append("Claude Opus Lineage")
    if "gemini" not in text_lower and "argon" not in text_lower:
        missing_seats.append("Gemini Argon Lineage")
    if "gpt" not in text_lower:
        missing_seats.append("GPT-OSS Lineage")
    if "kernel" not in text_lower and "deterministic" not in text_lower:
        missing_seats.append("Deterministic Verification Kernel")
    
    if missing_seats:
        findings.append(f"Incomplete 4-Seat Council Ledger; missing sign-offs for: {', '.join(missing_seats)}")

    # 5. Persistent Citation Grounding (DOI / PMID / NCT / arXiv)
    citations = CITATION_REGEX.findall(text)
    if not citations:
        findings.append("Zero persistent citation identifiers found (expected at least one DOI, PMID, NCT ID, or arXiv ID)")

    # 6. DOM Security: No unsafe innerHTML usage if script content is present
    if ".innerHTML" in text:
        findings.append("Unsafe .innerHTML assignment detected; interactive plates must use createElementNS, textContent, or safe DOM APIs")

    passed = len(findings) == 0
    return {
        "check": "monograph",
        "file": filename,
        "passed": passed,
        "revision": rev_match.group(0) if rev_match else None,
        "citation_count": len(citations),
        "findings": findings,
    }


def verify_companion_content(text: str, filename: str = "SKILL.md") -> Dict[str, Any]:
    """Verify a companion SKILL.md against Agent Skills and Living Monograph criteria."""
    findings: List[str] = []

    # 1. Frontmatter existence and parsing
    if not text.startswith("---"):
        findings.append("Missing YAML frontmatter block starting with '---'")
        return {"check": "companion", "file": filename, "passed": False, "findings": findings}

    parts = text.split("---", 2)
    if len(parts) < 3:
        findings.append("Malformed YAML frontmatter (unclosed '---')")
        return {"check": "companion", "file": filename, "passed": False, "findings": findings}

    fm_text = parts[1]
    body_text = parts[2]

    # Required frontmatter keys
    for req_key in ("name", "description", "license", "metadata"):
        if not re.search(rf"^{req_key}:", fm_text, re.MULTILINE):
            findings.append(f"Frontmatter missing required top-level key: '{req_key}'")

    # Metadata sub-keys
    for meta_key in ("audience", "level", "category"):
        if not re.search(rf"^\s+{meta_key}:", fm_text, re.MULTILINE):
            findings.append(f"Frontmatter metadata missing required sub-key: '{meta_key}'")

    # 2. Governing Equations / Core Laws
    if not re.search(r"(governing|equations|core laws|principles)", body_text, re.IGNORECASE):
        findings.append("Missing explicit Governing Equations or Core Principles section in body")

    # 3. Offline Verification or Runnable Oracle
    if "```python" not in body_text and "```text" not in body_text and "scripts/" not in body_text:
        findings.append("Missing runnable offline verification oracle or script reference")

    # 4. Scope Limitations & Research Disclaimer
    if not re.search(r"(research,\s*not medical advice|scope|limitations)", body_text, re.IGNORECASE):
        findings.append("Missing explicit research boundary / scope limitations disclaimer")

    passed = len(findings) == 0
    return {
        "check": "companion",
        "file": filename,
        "passed": passed,
        "findings": findings,
    }


def run_self_check() -> Dict[str, Any]:
    """Run built-in positive cases and negative controls."""
    checks: List[Dict[str, Any]] = []

    # Positive monograph case
    pos_monograph = """
    # Civil Engineering Folio E.01
    Edition: REV 1.2 | Published: 2026-10-15 | Redated: 2026-11-01
    
    ## 4-Seat Multi-Lineage Council Ledger
    - Claude Opus 5.5: Verified conceptual integrity and editorial cadence.
    - Gemini 4 Argon: Verified Buckingham Pi homogeneity and dimensional balance.
    - GPT-OSS 120B: Audited edge cases and counterfactual stability.
    - Deterministic Verification Kernel: Offline math verifier exited 0.
    
    ## Act I: Historical Grounding & Discovery Milestones
    Bingham (1922) and Herschel-Bulkley (1926) established non-Newtonian viscoplastic flow.
    
    ## Act II: Governing Equations & Interactive Parameter Scrubbing
    Shear stress equation: tau = tau_0 + K * (gamma_dot ** n).
    
    ## Act III: The Multi-Lens Scientific Observatory
    Interactive 3D potential surface and 2D streamline phase portrait.
    
    ## Act IV: Dual-Horizon Frontier Discovery & Research News
    Connected to automated CFA rig telemetry (DOI 10.1061/(ASCE)GT.1943-5606.0001642).
    """
    res = verify_monograph_content(pos_monograph, "positive_monograph")
    checks.append({"name": "monograph_positive_case", "ok": res["passed"]})

    # Negative monograph: missing Act III & council ledger
    neg_monograph = """
    # Incomplete Monograph
    Edition: REV 1.0 | Published: 2026-10-01
    ## Act I: Historical Grounding
    History here.
    ## Act II: Governing Equations
    Equations here.
    ## Act IV: Frontier Discovery
    DOI 10.1000/182
    """
    res_neg = verify_monograph_content(neg_monograph, "negative_monograph")
    checks.append({"name": "monograph_negative_control_catches_missing_acts_and_council", "ok": not res_neg["passed"]})

    # Negative monograph: unsafe innerHTML injection
    neg_html = pos_monograph + "\n<script>element.innerHTML = '<div>unsafe</div>';</script>"
    res_html = verify_monograph_content(neg_html, "negative_html")
    checks.append({"name": "monograph_negative_control_catches_inner_html", "ok": not res_html["passed"]})

    # Positive companion skill case
    pos_companion = """---
name: companion-example
description: "Offline companion for structural analysis."
license: CC0-1.0
metadata:
    audience: "researchers, builders"
    level: "advanced"
    category: "communication"
---

# Companion Example
Research, not medical advice. Scope and limitations apply.

## Governing Laws
Conservation of momentum and equilibrium equations.

```python
def check_equilibrium(forces):
    return sum(forces) == 0
```
"""
    res_comp = verify_companion_content(pos_companion, "positive_companion")
    checks.append({"name": "companion_positive_case", "ok": res_comp["passed"]})

    # Negative companion skill: missing metadata
    neg_companion = """---
name: broken-companion
description: "Missing metadata block."
license: CC0-1.0
---

# Broken Companion
"""
    res_comp_neg = verify_companion_content(neg_companion, "negative_companion")
    checks.append({"name": "companion_negative_control_catches_missing_metadata", "ok": not res_comp_neg["passed"]})

    total_passed = sum(1 for c in checks if c["ok"])
    all_ok = total_passed == len(checks)

    return {
        "check": "self-check",
        "passed": all_ok,
        "total_checks": len(checks),
        "passed_checks": total_passed,
        "checks": checks,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Living Executable Monograph and Companion Verifier")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # verify-monograph
    p_mono = subparsers.add_parser("verify-monograph", help="Verify monograph HTML or Markdown")
    p_mono.add_argument("--path", required=True, help="Path to monograph file")
    p_mono.add_argument("--json", action="store_true", help="Print JSON output")
    p_mono.add_argument("--json-out", help="Write JSON output to path")

    # verify-companion
    p_comp = subparsers.add_parser("verify-companion", help="Verify companion SKILL.md")
    p_comp.add_argument("--path", required=True, help="Path to companion SKILL.md")
    p_comp.add_argument("--json", action="store_true", help="Print JSON output")
    p_comp.add_argument("--json-out", help="Write JSON output to path")

    # self-check
    p_self = subparsers.add_parser("self-check", help="Run positive and negative self-checks")
    p_self.add_argument("--json", action="store_true", help="Print JSON output")
    p_self.add_argument("--json-out", help="Write JSON output to path")

    args = parser.parse_args(argv)

    if args.subcommand == "self-check":
        payload = run_self_check()
    elif args.subcommand == "verify-monograph":
        p = Path(args.path)
        if not p.is_file():
            sys.stderr.write(f"Error: File not found: {args.path}\n")
            return 2
        try:
            content = p.read_text(encoding="utf-8")
        except OSError as e:
            sys.stderr.write(f"Error reading {args.path}: {e}\n")
            return 2
        payload = verify_monograph_content(content, filename=p.name)
    elif args.subcommand == "verify-companion":
        p = Path(args.path)
        if not p.is_file():
            sys.stderr.write(f"Error: File not found: {args.path}\n")
            return 2
        try:
            content = p.read_text(encoding="utf-8")
        except OSError as e:
            sys.stderr.write(f"Error reading {args.path}: {e}\n")
            return 2
        payload = verify_companion_content(content, filename=p.name)
    else:
        sys.stderr.write(f"Unknown subcommand: {args.subcommand}\n")
        return 2

    # Output handling
    if getattr(args, "json_out", None):
        out_p = Path(args.json_out)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    if getattr(args, "json", False) or not sys.stdout.isatty():
        sys.stdout.write(json.dumps(payload, indent=2) + "\n")
    else:
        if payload.get("passed"):
            sys.stdout.write(f"PASS: {payload.get('check')} checks satisfied ({payload.get('file', 'all')})\n")
        else:
            sys.stdout.write(f"FAIL: {payload.get('check')} found issues:\n")
            for finding in payload.get("findings", []):
                sys.stdout.write(f"  - {finding}\n")

    return 0 if payload.get("passed") else 1


if __name__ == "__main__":
    sys.exit(main())
