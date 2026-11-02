---
name: complex-systems-monograph
description: "AI-agnostic methodology and offline verification tooling for structuring complex scientific, mathematical, architectural, and biomedical systems into interactive Living Executable Monographs with portable SKILL.md companions. Enforces the 4-Act pedagogical narrative structure, 4-Seat Frontier Council peer review, zero-build web accessibility, and offline deterministic falsification."
license: CC0-1.0
compatibility: "The verifier (scripts/monograph_verify.py) runs offline with Python 3.9+ using only the standard library; compatible with Claude Code, GitHub Copilot, Cursor, Google Antigravity, OpenAI Codex, and local Ollama models."
metadata:
    version: "0.2.0"
    last-updated: "2026-11-02"
    capabilities: "python, reads-project-files, runs-code"
    optional-capabilities: ""
    audience: "researchers, builders"
    level: "advanced"
    category: "communication"
    summary: "Structures and verifies interactive Living Executable Monographs with 4-Act narrative architectures, 4-Seat Council review, and portable SKILL.md companions."
---

# Complex Systems Monograph & Human Cognitive Extension

Research, not medical advice. Structuring a scientific, mathematical, architectural, or biomedical system into an interactive monograph or downloadable companion skill says nothing about clinical efficacy, patient diagnosis, or medical care.

Helps researchers, clinicians, engineers, architects, and families master complex systems and extend their intellectual and creative potential alongside frontier AI.

---

## 1. When to Use This Skill

- You are authoring, structuring, or auditing an interactive **Living Executable Monograph** explaining complex multi-scale systems (such as fluid rheology, structural equilibrium, non-equilibrium thermodynamics, or gene delivery barriers).
- You are structuring technical communication to prioritize **human comprehension before automation**, presenting concepts across four simultaneous modalities: plain-language intuition, scrubbable governing equations, multi-lens scientific observatories, and primary source citations.
- You are establishing a **Living Dated Edition** (`REV 1.0 -> REV 1.2`) with transparent peer review across a 4-Seat Multi-Lineage Council (Claude Opus, Gemini Argon, GPT-OSS, and deterministic verification kernels).
- You need to generate a portable, downloadable **AI-Agnostic `SKILL.md` Companion** that allows readers to load the monograph's verified mental model and offline verifiers into any AI tool they use.
- You want to mechanically audit an interactive monograph or companion skill using the offline standard-library verifier (`scripts/monograph_verify.py`).

---

## 2. Core Architectural Principles

See [`references/monograph-schema.md`](references/monograph-schema.md) for the complete schema and specification.

### Principle 1: Human Understanding Before Automation
Never provide black-box assertions. Every complex model must unfold across four synchronized layers:
1. **Plain-Language Intuition**: Grounded analogies and real-world boundary conditions.
2. **Governing Equations**: Exact dimensional expressions with scrubbable tokens that reveal parameter sensitivities.
3. **Multi-Scale Visualizations**: Dual macroscopic form (`1:50`) and microscopic nodal loupes (`1:5`).
4. **Offline Deterministic Oracles**: Executable code verifying physical laws and invariant conservation.

### Principle 2: The 4-Act Narrative Structure
1. **Act I: Historical Grounding & Discovery Milestones**: The human story and 4 chronological breakthroughs leading to modern understanding.
2. **Act II: Governing Equations & Interactive Parameter Scrubbing**: First-principles derivations with inline interactive token scrubbing.
3. **Act III: The Multi-Lens Scientific Observatory**: Multi-modal exploration across 2D/3D potential surfaces, phase-space vector fields, Noether-Kirchhoff alluvial conservation ribbons, or polar performance envelopes.
4. **Act IV: Dual-Horizon Frontier Discovery & Smart Citations**: Connecting foundational equations to contemporary (2024-2026) breakthroughs, verified with persistent DOIs, PMIDs, or NCT trial IDs.

### Principle 3: Living Dated Editions & 4-Seat Frontier Council Sign-Off
Monographs are dated and redated with explicit revision lineages (`REV 1.0 -> REV 1.2`). Every revision is verified across four distinct perspectives:
- **Seat 1 (Claude Opus lineage)**: Conceptual coherence and prose dignity.
- **Seat 2 (Gemini Argon lineage)**: Mathematical precision and code-level verification.
- **Seat 3 (GPT-OSS lineage)**: Edge cases and counterfactual stability.
- **Seat 4 (Deterministic Verification Kernel)**: Offline mathematical and structural checks.

### Principle 4: Portable AI-Agnostic `SKILL.md` Companions
Every monograph packages its verified mental model into a standalone `SKILL.md` that can be loaded into Claude Code, GitHub Copilot, Cursor, Google Antigravity, OpenAI Codex, or local Ollama models without requiring network access.

---

## 3. The Offline Verifier (`scripts/monograph_verify.py`)

Run the standard-library verifier to audit monographs and companion skills:

```text
python scripts/monograph_verify.py SUBCOMMAND [ARGS] [--json] [--json-out PATH]
```

| Subcommand | What it verifies |
| :--- | :--- |
| `verify-monograph --path PATH` | Validates a monograph HTML or Markdown file against the 4-Act structure, `REV X.Y` edition format, ISO 8601 timestamps, 4-Seat Council ledger, persistent citation grounding, and DOM security (no unsafe `.innerHTML`). |
| `verify-companion --path PATH` | Validates a companion `SKILL.md` against Agent Skills frontmatter schema, governing equations, runnable offline verification code, and scope/safety disclaimers. |
| `self-check` | Executes built-in positive cases and deterministic negative controls across both verification engines; exits 0 only when all tests pass. |

| Exit code | Meaning |
| :--- | :--- |
| `0` | Every invariant check passed. |
| `1` | One or more structural, editorial, or verification invariants failed. |
| `2` | Usage error or unreadable input file. |

---

## 4. Verification Workflow

1. **Verify the verifier**: Run `python scripts/monograph_verify.py self-check` to confirm positive and negative control detection.
2. **Audit the monograph document**: Run `python scripts/monograph_verify.py verify-monograph --path <monograph.html>`.
3. **Audit the companion skill**: Run `python scripts/monograph_verify.py verify-companion --path <SKILL.md>`.
4. **Run unit test suite**: Run `python -m unittest discover -s tests -p "test_*.py"`.
