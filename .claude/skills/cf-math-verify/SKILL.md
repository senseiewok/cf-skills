---
name: cf-math-verify
description: "Offline mathematical and biophysical invariant verifier for scientific models and formal proof dependency graphs: checks exact rational Buckingham Pi dimensional homogeneity across SI base units, machine-precision complex-step derivatives, Lean 4 formal proof DAG acyclicity and zero-sorryAx cones, and 20 non-equilibrium statistical mechanics laws (Kramers escape, Cheeger-Fiedler spectral bounds, Jarzynski and Crooks fluctuation theorems, Landauer erasure, Barato-Seifert TUR, Shiraishi-Funo-Saito thermodynamic speed limits, Evans-Majumdar stochastic resetting, Salamon-Berry thermodynamic length, Benamou-Brenier optimal transport, and Schreiber bipartite transfer entropy). Use when verifying equations, derivatives, dimensional balance, or proof DAGs before publishing research claims."
license: CC0-1.0
compatibility: "The checker (scripts/math_verify.py) requires Python 3.9+ with the standard library only (tested on Python 3.13); it makes zero network requests and writes no files unless --json-out is passed."
metadata:
    version: "0.1.0"
    last-updated: "2026-10-29"
    capabilities: "python, reads-project-files, runs-code"
    optional-capabilities: ""
    audience: "researchers, builders"
    level: "advanced"
    category: "math"
    summary: "Offline verifier for dimensional balance, complex-step derivatives, Lean 4 proof DAGs, and 20 non-equilibrium thermodynamic bounds."
---

# Mathematical and Biophysical Invariant Verifier

Scientific notes and computational models fail silently when an equation is dimensionally inconsistent, a finite-difference derivative suffers subtractive cancellation, a proof dependency graph hides an unproved axiom in its transitive cone, or a kinetic model violates the Second Law of Thermodynamics. This skill provides a standard-library, zero-network command-line verifier (`scripts/math_verify.py`) and a structured review workflow so an agent or researcher can check mathematical and biophysical claims before they reach a public page.

Research, not medical advice. Checking that an equation is dimensionally consistent or satisfies a thermodynamic bound says nothing about clinical efficacy, patient eligibility, or medical care.

## 1. When to use this skill

- A biophysical, pharmacokinetic, or statistical-mechanics model is drafted or modified and needs deterministic invariant checks before publication.
- You need to verify that both sides of an equation share identical rational SI base dimensions (`[M, L, T, I, Theta, N, J]`) via exact `fractions.Fraction` arithmetic.
- You need to verify an analytical derivative against a numerical oracle without finite-difference step-size cancellation, using complex-step differentiation at step $h = 10^{-30}$.
- You are auditing a formal proof dependency graph (such as the four Lean 4 benchmarks in [`references/invariants.md`](references/invariants.md)) for topological acyclicity, zero `sorryAx` contamination, and Noether-Kirchhoff deductive flux conservation.
- You are checking whether a channel-gating or molecular-transport trajectory satisfies the 20 non-equilibrium thermodynamic laws cataloged in [`references/invariants.md`](references/invariants.md).

## 2. The checker

```text
python scripts/math_verify.py SUBCOMMAND [ARGS] [--json] [--json-out PATH]
```

| Subcommand | What it verifies |
| --- | --- |
| `buckingham --spec JSON` | Exact rational (`fractions.Fraction`) SI base-dimension homogeneity (`[M, L, T, I, Theta, N, J]`) across every term of a symbolic equation specification, plus Buckingham Pi nullspace rank. |
| `complex-step --expr EXPR --deriv DERIV --var VAR --at VAL` | Machine-precision derivative check comparing analytical derivative `DERIV` against $\text{Im}(f(x + i h))/h$ at $h = 10^{-30}$ (agreement within $10^{-11}$ relative tolerance). |
| `proof-dag --dag JSON` | Topological acyclicity (Kahn's algorithm), zero `sorryAx` contamination in transitive dependency cones, Noether-Kirchhoff deductive flux conservation, and Hilbert state alignment. |
| `thermo-bounds --preset PRESET` | Runs the 20 non-equilibrium statistical-mechanics and information-thermodynamics invariant checks (Rounds 1 through 20) against canonical CFTR genotypes (`wt`, `eti`, `f508del`, `w1282x`) and Lean 4 formal proof benchmarks (`flt`, `zeta23`, `apsp`, `eth`). |
| `self-check` | Runs all built-in positive and negative-control self-tests across all four engines and exits 0 only when every positive case passes and every negative control is caught. |

| Exit code | Meaning |
| --- | --- |
| `0` | Every invariant check passed. |
| `1` | At least one mathematical or thermodynamic invariant failed. |
| `2` | Usage error or unreadable input file. |

## 3. Workflow

1. **Run `self-check` first.** Confirm that the verifier both passes valid models and rejects intentionally broken negative controls (`python scripts/math_verify.py self-check`). A verifier that cannot fail proves nothing.
2. **Check dimensional homogeneity (`buckingham`).** Express every variable and constant in its seven SI base dimensions (`M` kg, `L` m, `T` s, `I` A, `Theta` K, `N` mol, `J` cd) and verify that every additive term and both sides of every equality match in exact rational arithmetic.
3. **Check sensitivities via complex-step (`complex-step`).** Replace finite differences with complex-step perturbations $x + i h$ ($h = 10^{-30}$) to verify analytical Jacobians and parameter sensitivities to machine epsilon ($\approx 2.22 \times 10^{-16}$).
4. **Verify proof DAG and thermodynamic bounds (`proof-dag` and `thermo-bounds`).** Check that formal deduction graphs contain zero cycles and zero unproved axioms, and that non-equilibrium trajectories satisfy all applicable fluctuation, speed-limit, optimal-transport, and transfer-entropy bounds in [`references/invariants.md`](references/invariants.md).
5. **State scope and limitations.** Label every verified result **OBSERVED** (computed by the script with exact command and output) and state what the mathematical check does *not* establish (mathematical consistency is a necessary condition, never proof of biological or clinical truth).

## 4. Verify the skill works

From the skill folder:

```bash
python -m unittest discover -s tests -v
python scripts/math_verify.py self-check --json
```

The test suite (`tests/test_math_verify.py`) verifies all four subcommands against both valid analytical fixtures and deliberately broken negative controls (dimensional mismatches, wrong derivatives, cyclic or `sorryAx`-contaminated DAGs, and Second-Law / TUR / Wasserstein violations), while installing an audit hook that fails if any test opens a network socket or spawns a subprocess.
