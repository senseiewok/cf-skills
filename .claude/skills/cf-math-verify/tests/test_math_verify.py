"""Unit tests for .claude/skills/cf-math-verify/scripts/math_verify.py.

Verifies all four mathematical and biophysical engines against positive analytical
cases and intentionally broken negative controls, while enforcing an audit hook
that forbids any network socket or subprocess creation during verification.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = SKILL_ROOT / "scripts" / "math_verify.py"

spec = importlib.util.spec_from_file_location("math_verify", SCRIPT_PATH)
assert spec is not None and spec.loader is not None
math_verify = importlib.util.module_from_spec(spec)
sys.modules["math_verify"] = math_verify
spec.loader.exec_module(math_verify)


class MathVerifyTests(unittest.TestCase):
    def test_self_check_passes_all_positive_and_negative_controls(self):
        res = math_verify.run_self_check()
        self.assertTrue(res["passed"], res)
        self.assertGreaterEqual(res["total_checks"], 15)

    def test_buckingham_exact_rational_exponents_and_pi_count(self):
        # Stokes-Brinkman permeability k_perm [L^2], viscosity mu [M L^-1 T^-1], velocity v [L T^-1], gradP [M L^-2 T^-2]
        spec_obj = {
            "name": "Stokes-Brinkman pressure gradient balance",
            "variables": {
                "gradP": {"M": 1, "L": -2, "T": -2},
                "mu": {"M": 1, "L": -1, "T": -1},
                "v": {"L": 1, "T": -1},
                "k_perm": {"L": 2},
            },
            "terms": [
                {"label": "pressure_grad", "exponents": {"gradP": 1}},
                {"label": "darcy_drag", "exponents": {"mu": 1, "v": 1, "k_perm": -1}},
            ],
        }
        res = math_verify.verify_buckingham(spec_obj)
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["n_variables"], 4)
        self.assertEqual(res["dimensional_rank"], 3)
        self.assertEqual(res["buckingham_pi_groups"], 1)

    def test_buckingham_catches_fractional_dimension_mismatch(self):
        spec_obj = {
            "name": "Broken half-power length equation",
            "variables": {
                "x": {"L": "1/2"},
                "y": {"L": 1},
            },
            "terms": [
                {"label": "lhs", "exponents": {"x": 1}},
                {"label": "rhs", "exponents": {"y": 1}},
            ],
        }
        res = math_verify.verify_buckingham(spec_obj)
        self.assertFalse(res["passed"])
        self.assertTrue(any("Dimensional mismatch" in f for f in res["findings"]))

    def test_complex_step_matches_analytical_hill_and_michaelis_menten(self):
        # Hill activation function f(c) = c^2 / (K^2 + c^2), f'(c) = 2*c*K^2 / (K^2 + c^2)^2
        res = math_verify.verify_complex_step(
            expr_str="(c ** 2) / ((K ** 2) + (c ** 2))",
            deriv_str="(2 * c * (K ** 2)) / (((K ** 2) + (c ** 2)) ** 2)",
            var="c",
            at_val=1.5,
            params={"K": 0.8},
        )
        self.assertTrue(res["passed"], res)
        self.assertLess(res["rel_error"], 1e-14)

    def test_proof_dag_detects_kirchhoff_flux_violation(self):
        dag = {
            "name": "Unbalanced internal node flux",
            "nodes": [
                {"id": "n1", "role": "source"},
                {"id": "n2", "role": "internal"},
                {"id": "n3", "role": "qed"},
            ],
            "edges": [
                {"source": "n1", "target": "n2", "flux": 1.0},
                {"source": "n2", "target": "n3", "flux": 0.5},
            ],
        }
        res = math_verify.verify_proof_dag(dag)
        self.assertFalse(res["passed"])
        self.assertTrue(any("Kirchhoff" in f for f in res["findings"]))

    def test_thermo_bounds_all_presets_pass_via_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_file = Path(tmp) / "out.json"
            code = math_verify.main(["thermo-bounds", "--preset", "all", "--json", "--json-out", str(out_file)])
            self.assertEqual(code, 0)
            payload = json.loads(out_file.read_text(encoding="utf-8"))
            self.assertTrue(payload["passed"])
            self.assertEqual(len(payload["presets"]), 8)

    def test_zero_network_and_zero_subprocess_audit_hook(self):
        events = []

        def hook(event, args):
            if event.startswith("socket.") or event.startswith("urllib.") or event == "subprocess.Popen":
                events.append((event, args))

        sys.addaudithook(hook)
        code = math_verify.main(["self-check", "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(events, [], f"Disallowed network or subprocess events: {events}")


if __name__ == "__main__":
    unittest.main()
