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
            self.assertEqual(len(payload["presets"]), len(math_verify.CANONICAL_PRESETS))
            self.assertGreaterEqual(len(payload["presets"]), 126)

    def test_thermo_bounds_g551d_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["g551d"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_n1303k_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["n1303k"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])
        self.assertAlmostEqual(res["w_diss_kcal"], 9.60, places=2)

    def test_thermo_bounds_g542x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["g542x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_r553x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["r553x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_y122x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["y122x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_r1162x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["r1162x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_w1098x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["w1098x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_r709x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["r709x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_r1158x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["r1158x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_r785x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["r785x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_r114x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["r114x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_r851x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["r851x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_e60x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["e60x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_q493x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["q493x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_r75x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["r75x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_w882x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["w882x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_e193x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["e193x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_w496x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["w496x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_s912x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["s912x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_q1042x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["q1042x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_q1291x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["q1291x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_g458x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["g458x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_q685x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["q685x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_l1258x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["l1258x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_q1382x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["q1382x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_s4x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["s4x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_w57x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["w57x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_q359x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["q359x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_q1071x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["q1071x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_k68x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["k68x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_q715x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["q715x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_y849x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["y849x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_y913x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["y913x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_k370x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["k370x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_w514x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["w514x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_w1145x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["w1145x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_w1274x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["w1274x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_e56x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["e56x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_q414x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["q414x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_e1308x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["e1308x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_e1418x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["e1418x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_q1038x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["q1038x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_s1276x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["s1276x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_k1292x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["k1292x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_q1423x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["q1423x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_r347x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["r347x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_r560x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["r560x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_r1066x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["r1066x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_r1070x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["r1070x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_q2x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["q2x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_s13x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["s13x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_w216x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["w216x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_y275x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["y275x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_q552x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["q552x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_s578x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["s578x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_r899x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["r899x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_k1330x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["k1330x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_w19x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["w19x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_q39x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["q39x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_w401x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["w401x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_s466x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["s466x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_c524x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["c524x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_k710x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["k710x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_w846x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["w846x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_w1089x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["w1089x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_s1196x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["s1196x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_s1255x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["s1255x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_w1316x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["w1316x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_q1411x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["q1411x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_q1412x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["q1412x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_g67x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["g67x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_e82x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["e82x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_w202x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["w202x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_q290x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["q290x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_c590x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["c590x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_q72x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["q72x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_r117x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["r117x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_w498x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["w498x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_r810x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["r810x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_w1216x_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["w1216x"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_3905inst_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["3905inst"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_3878delg_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["3878delg"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_2043delg_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["2043delg"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_2869insg_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["2869insg"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_4016inst_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["4016inst"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_3659delc_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["3659delc"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_394deltt_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["394deltt"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_1078delt_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["1078delt"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_2184dela_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["2184dela"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_2183aag_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["2183aag"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_1161delc_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["1161delc"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_2184insa_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["2184insa"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_3876dela_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["3876dela"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_2143delt_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["2143delt"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_2347delg_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["2347delg"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_621_plus_1g_to_t_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["621+1g->t"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_1717_minus_1g_to_a_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["1717-1g->a"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_3120_plus_1g_to_a_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["3120+1g->a"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_711_plus_1g_to_t_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["711+1g->t"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_cftrdele2_3_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["cftrdele2,3"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_1898_plus_1g_to_a_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["1898+1g->a"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_1812_minus_1g_to_a_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["1812-1g->a"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_405_plus_1g_to_a_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["405+1g->a"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_cftrdele1_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["cftrdele1"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_cftrdele22_23_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["cftrdele22,23"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_i507del_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["i507del"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_g85e_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["g85e"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_r117h_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["r117h"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_s549n_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["s549n"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_thermo_bounds_a455e_preset_passes(self):
        res = math_verify.verify_thermo_bounds(math_verify.CANONICAL_PRESETS["a455e"])
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["findings"], [])

    def test_buckingham_cli(self):
        spec_obj = {
            "name": "CLI test",
            "variables": {"v": {"L": 1, "T": -1}, "t": {"T": 1}, "x": {"L": 1}},
            "terms": [
                {"label": "lhs", "exponents": {"x": 1}},
                {"label": "rhs", "exponents": {"v": 1, "t": 1}},
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            spec_file = Path(tmp) / "spec.json"
            spec_file.write_text(json.dumps(spec_obj), encoding="utf-8")
            out_file = Path(tmp) / "out.json"
            code = math_verify.main(["buckingham", "--spec", str(spec_file), "--json", "--json-out", str(out_file)])
            self.assertEqual(code, 0)
            payload = json.loads(out_file.read_text(encoding="utf-8"))
            self.assertTrue(payload["passed"])

    def test_complex_step_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_file = Path(tmp) / "out.json"
            code = math_verify.main([
                "complex-step",
                "--expr", "x ** 2",
                "--deriv", "2 * x",
                "--var", "x",
                "--at", "3.0",
                "--json",
                "--json-out", str(out_file),
            ])
            self.assertEqual(code, 0)
            payload = json.loads(out_file.read_text(encoding="utf-8"))
            self.assertTrue(payload["passed"])

    def test_proof_dag_cli(self):
        dag = {
            "name": "CLI DAG Test",
            "nodes": [
                {"id": "a", "role": "source"},
                {"id": "b", "role": "qed"},
            ],
            "edges": [
                {"source": "a", "target": "b", "flux": 1.0},
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            dag_file = Path(tmp) / "dag.json"
            dag_file.write_text(json.dumps(dag), encoding="utf-8")
            out_file = Path(tmp) / "out.json"
            code = math_verify.main(["proof-dag", "--dag", str(dag_file), "--json", "--json-out", str(out_file)])
            self.assertEqual(code, 0)
            payload = json.loads(out_file.read_text(encoding="utf-8"))
            self.assertTrue(payload["passed"])

    def test_cli_no_subcommand_returns_2(self):
        code = math_verify.main([])
        self.assertEqual(code, 2)

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
