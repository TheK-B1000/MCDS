"""The locked replicate-count rule (experiments/precision/replicate_rule_v1.json)
as applied by python/replicate_decision.py."""

from __future__ import annotations

import csv
import json
import math
import random
import sys
import tempfile
import unittest
from pathlib import Path

_PYTHON_DIR = Path(__file__).resolve().parents[1]
if str(_PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(_PYTHON_DIR))

import replicate_decision as rd  # noqa: E402

RULE = json.loads(rd.RULE.read_text(encoding="utf-8"))
ALGOS = rd.ALGORITHMS


def _comps(hw_by_k: dict[int, tuple[float, float]], strata=(("uniform", 8.0), ("uniform", 12.0)), n_comp=18):
    """Crafted comparison records: every comparison of a stratum at k gets the
    given (CDS half-width pp, runtime multiplicative half-width)."""
    out = []
    for g, d in strata:
        for i in range(n_comp):
            for k, (cds, rt) in hw_by_k.items():
                out.append({"geometry": g, "density": d, "n": 500 + i, "pair": "a-b", "k": k,
                            "cds_hw_pp": cds, "cds_diff_pp": 0.0, "rt_hw_mult": rt, "rt_ratio_geomean": 1.0})
    return out


def _graph_level(path: Path, sigma: float, tau: float, reps: int = 52, seed: int = 3) -> None:
    rng = random.Random(seed)
    base_f = {"marathe": 0.20, "wan": 0.22, "funke": 0.21, "li": 0.18}
    base_t = {"marathe": 2.0, "wan": 3.0, "funke": 2.5, "li": 4.0}
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["graph_id", "spatial_backend", "algorithm", "geometry", "n",
                                          "density_target", "replicate", "cds_fraction", "t_algorithm_ms"])
        w.writeheader()
        for g in ("uniform", "dumbbell"):
            for d in (8.0, 12.0):
                for n in (500, 2000, 10000):
                    for rep in range(1, reps + 1):
                        for a in ALGOS:
                            w.writerow({"graph_id": f"{g}{d}{n}{rep}", "spatial_backend": "cgal", "algorithm": a,
                                        "geometry": g, "n": n, "density_target": d, "replicate": rep,
                                        "cds_fraction": base_f[a] + rng.gauss(0, sigma),
                                        "t_algorithm_ms": base_t[a] * math.exp(rng.gauss(0, tau))})


class RuleFileTests(unittest.TestCase):
    def test_locked_rule_contents(self):
        self.assertEqual(RULE["ladder"], [20, 28, 36, 44, 52])
        self.assertTrue(all(k % 4 == 0 for k in RULE["ladder"]))  # exact Williams balance
        self.assertNotIn("stability", RULE)  # removed before any pilot data (amendment record)
        self.assertTrue(all(a["before_any_pilot_data"] for a in RULE["amendments"]))
        self.assertIn("NOT declared sufficient", RULE["selection"])
        self.assertEqual(RULE["pilot"]["densities"], [8.0, 12.0])

    def test_pilot_config_matches_rule(self):
        cfg = json.loads((rd._ROOT / "experiments" / "precision_pilot.json").read_text(encoding="utf-8"))
        final = json.loads((rd._ROOT / "experiments" / "final.json").read_text(encoding="utf-8"))
        syn = cfg["synthetic"]
        self.assertEqual(syn["replicates"], RULE["pilot"]["graphs_per_cell"])
        self.assertEqual(syn["geometries"], RULE["pilot"]["geometries"])
        self.assertEqual(syn["sizes"], RULE["pilot"]["sizes"])
        self.assertEqual(syn["densities"], RULE["pilot"]["densities"])
        self.assertEqual(cfg["timing"], final["timing"])  # same measurement protocol as the final study
        self.assertEqual(syn["geometry_parameters"], final["synthetic"]["geometry_parameters"])


class PilotRerunConfigTests(unittest.TestCase):
    def test_rerun_is_the_original_design_with_a_new_study_id(self):
        exp = rd._ROOT / "experiments"
        original = json.loads((exp / "precision_pilot.json").read_text(encoding="utf-8"))
        rerun = json.loads((exp / "precision_pilot_rerun.json").read_text(encoding="utf-8"))
        self.assertEqual(rerun["study_id"], "precision_pilot_rerun")
        strip = lambda d: {k: v for k, v in d.items() if k not in ("study_id", "description")}  # noqa: E731
        self.assertEqual(strip(rerun), strip(original))  # same seed and design -> identical graphs


class LockedSelectionTests(unittest.TestCase):
    """final.json is tied to the pilot's mechanical outcome and its evidence."""

    def test_final_uses_selected_count_and_evidence_is_intact(self):
        import hashlib
        prec = rd._ROOT / "experiments" / "precision"
        sel = json.loads((prec / "replicate_selection_v1.json").read_text(encoding="utf-8"))
        final = json.loads((rd._ROOT / "experiments" / "final.json").read_text(encoding="utf-8"))
        self.assertEqual(sel["status"], "selected")
        self.assertEqual(final["synthetic"]["replicates"], sel["selected_replicates"])
        self.assertIn(final["synthetic"]["replicates"], RULE["ladder"])
        h = sel["evidence_sha256"]
        def sha(p):
            return hashlib.sha256(p.read_bytes()).hexdigest()
        self.assertEqual(sha(rd.RULE), h["experiments/precision/replicate_rule_v1.json"])
        self.assertEqual(sha(rd._ROOT / "python" / "replicate_decision.py"), h["python/replicate_decision.py"])
        self.assertEqual(sha(rd._ROOT / "experiments" / "precision_pilot.json"), h["experiments/precision_pilot.json"])
        self.assertEqual(sha(prec / "precision_pilot_replicate_decision.txt"),
                         h["results/studies/precision_pilot/replicate_decision.txt"])
        self.assertEqual(sha(prec / "precision_pilot_graph_level.csv"),
                         h["results/studies/precision_pilot/graph_level.csv (decision input)"])

    def test_committed_decision_input_reproduces_the_selection(self):
        with tempfile.TemporaryDirectory() as d:
            import shutil
            shutil.copyfile(rd._ROOT / "experiments" / "precision" / "precision_pilot_graph_level.csv",
                            Path(d) / "graph_level.csv")
            self.assertEqual(rd.main(["--study", d, "--json", str(Path(d) / "dec.json")]), 0)
            self.assertEqual(json.loads((Path(d) / "dec.json").read_text(encoding="utf-8"))["chosen_k"], 36)


class DecisionTests(unittest.TestCase):
    def test_t_quantile(self):
        for df, ref in ((19, 2.093024), (27, 2.051831), (51, 2.007584)):
            self.assertAlmostEqual(rd.t975(df), ref, places=5)

    def test_smallest_narrow_k_is_selected(self):
        res = rd.decide(_comps({20: (1.3, 0.05), 28: (1.1, 0.05), 36: (0.9, 0.05), 44: (0.8, 0.05),
                                52: (0.7, 0.05)}), RULE)
        self.assertEqual(res["status"], "selected")
        self.assertEqual(res["chosen_k"], 36)

    def test_every_stratum_must_pass(self):
        comps = _comps({k: (0.5, 0.05) for k in RULE["ladder"]}, strata=(("uniform", 8.0),))
        comps += _comps({20: (0.5, 0.15), 28: (0.5, 0.15), 36: (0.5, 0.15), 44: (0.5, 0.08), 52: (0.5, 0.07)},
                        strata=(("uniform", 12.0),))
        self.assertEqual(rd.decide(comps, RULE)["chosen_k"], 44)  # density 12 is the least precise regime

    def test_share_and_max_thresholds(self):
        # 17/18 comparisons narrow (94% >= 90%) passes; one beyond the 2 pp max fails.
        base = _comps({20: (0.5, 0.05)}, strata=(("uniform", 8.0),))
        base[0]["cds_hw_pp"] = 1.9
        self.assertTrue(rd.decide(base, dict(RULE, ladder=[20]))["passing_k"])
        base[0]["cds_hw_pp"] = 2.1
        self.assertFalse(rd.decide(base, dict(RULE, ladder=[20]))["passing_k"])
        # 2/18 too wide (89% < 90%) fails
        base[0]["cds_hw_pp"] = 1.5
        base[1]["cds_hw_pp"] = 1.5
        self.assertFalse(rd.decide(base, dict(RULE, ladder=[20]))["passing_k"])

    def test_failure_at_cap_is_explicit_not_52(self):
        res = rd.decide(_comps({k: (1.5, 0.05) for k in RULE["ladder"]}), RULE)
        self.assertEqual(res["status"], "precision_target_not_met")
        self.assertIsNone(res["chosen_k"])
        self.assertEqual(len(res["failing_strata_at_cap"]), 2)
        self.assertTrue(res["comparisons_missing_targets_at_cap"])

    def test_end_to_end_on_graph_level_csv(self):
        with tempfile.TemporaryDirectory() as d:
            _graph_level(Path(d) / "graph_level.csv", sigma=0.002, tau=0.02)
            self.assertEqual(rd.main(["--study", d, "--json", str(Path(d) / "dec.json"),
                                      "--plots", str(Path(d) / "plots")]), 0)
            dec = json.loads((Path(d) / "dec.json").read_text(encoding="utf-8"))
            self.assertEqual(dec["chosen_k"], 20)
            self.assertEqual(len(list((Path(d) / "plots").glob("trajectory_*.png"))), 4)
        with tempfile.TemporaryDirectory() as d:
            _graph_level(Path(d) / "graph_level.csv", sigma=0.05, tau=0.5)  # far too noisy
            self.assertEqual(rd.main(["--study", d]), 2)

    def test_missing_replicate_breaks_prefix_rule(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "graph_level.csv"
            _graph_level(p, sigma=0.002, tau=0.02)
            rows = [r for r in csv.DictReader(p.open(encoding="utf-8"))
                    if not (r["replicate"] == "7" and r["geometry"] == "uniform")]
            with self.assertRaises(ValueError):
                rd.comparisons(rows, RULE["ladder"])


if __name__ == "__main__":
    unittest.main()
