"""Tests for the experiment framework (python/study, python/run_study.py)."""

from __future__ import annotations

import copy
import csv
import json
import math
import shutil
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

_PYTHON_DIR = Path(__file__).resolve().parent.parent
if str(_PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(_PYTHON_DIR))

from study import analysis, config as config_mod, fairness  # noqa: E402
from study.bench import find_binary  # noqa: E402
from study.fingerprint import graph_id_for, points_fingerprint  # noqa: E402
from study.runner import Study, StudyError  # noqa: E402
from study.schedule import execution_order, schedule_index, williams_rows  # noqa: E402
from study.seeds import graph_seed  # noqa: E402

REPO_ROOT = _PYTHON_DIR.parent


def _bench_available() -> bool:
    try:
        find_binary(REPO_ROOT, "mcds_bench")
        find_binary(REPO_ROOT, "mcds_bench_mem")
        return True
    except FileNotFoundError:
        return False


def _base_config(**over):
    cfg = {
        "study_id": "t", "study_seed": 7,
        "synthetic": {"geometries": ["uniform"], "sizes": [50], "densities": [8.0], "replicates": 2},
    }
    cfg.update(over)
    return cfg


class FingerprintTests(unittest.TestCase):
    def test_matches_cpp_reference_constants(self):
        # Same constants are asserted in cpp/tests/test_bench_support.cpp.
        pts = [(0, 0.0, 0.0), (1, 0.5, 0.0), (2, 1.0, 0.25), (7, -3.125, 2.0)]
        self.assertEqual(points_fingerprint(pts), "ad972ec0862f3689")
        self.assertEqual(points_fingerprint([]), "a8c7f832281a39c5")

    def test_graph_id_depends_on_radius(self):
        self.assertNotEqual(graph_id_for("abc", 1.0), graph_id_for("abc", 2.0))
        self.assertEqual(graph_id_for("abc", 1.0), graph_id_for("abc", 1.0))


class SeedTests(unittest.TestCase):
    def test_retry_seeds_never_collide_with_other_replicates(self):
        # Pre-upgrade failure mode: base_seed + attempt made replicate r attempt 1 == replicate r+1 attempt 0.
        seeds = {graph_seed(1, "uniform", 1000, 3.0, 1.0, rep, att) for rep in range(1, 31) for att in range(80)}
        self.assertEqual(len(seeds), 30 * 80)

    def test_seeds_are_deterministic_and_factor_sensitive(self):
        a = graph_seed(1, "uniform", 1000, 3.0, 1.0, 1, 0)
        self.assertEqual(a, graph_seed(1, "uniform", 1000, 3.0, 1.0, 1, 0))
        self.assertNotEqual(a, graph_seed(1, "uniform", 1000, 5.0, 1.0, 1, 0))
        self.assertNotEqual(a, graph_seed(2, "uniform", 1000, 3.0, 1.0, 1, 0))


class ScheduleTests(unittest.TestCase):
    def test_williams_even_is_latin_and_carryover_balanced(self):
        rows = williams_rows(4)
        self.assertEqual(len(rows), 4)
        for pos in range(4):
            self.assertEqual(sorted(r[pos] for r in rows), [0, 1, 2, 3])
        pairs = Counter((r[i], r[i + 1]) for r in rows for i in range(3))
        self.assertEqual(len(pairs), 12)
        self.assertTrue(all(v == 1 for v in pairs.values()))

    def test_williams_odd_uses_mirrored_square(self):
        rows = williams_rows(3)
        self.assertEqual(len(rows), 6)
        pairs = Counter((r[i], r[i + 1]) for r in rows for i in range(2))
        self.assertTrue(all(v == 2 for v in pairs.values()))

    def test_cell_is_balanced_when_replicates_multiple_of_rows(self):
        algos = ["marathe", "wan", "funke", "li"]
        counts = Counter()
        for rep in range(1, 9):
            order, _ = execution_order(algos, 99, schedule_index(99, {"cell_id": "c", "replicate": rep}))
            counts.update((a, i) for i, a in enumerate(order))
        self.assertTrue(all(counts[(a, i)] == 2 for a in algos for i in range(4)))


class ConfigTests(unittest.TestCase):
    def test_unknown_keys_rejected(self):
        with self.assertRaises(config_mod.ConfigError):
            config_mod.resolve(_base_config(timming={}))
        bad = _base_config()
        bad["timing"] = {"repetitons": 3}
        with self.assertRaises(config_mod.ConfigError):
            config_mod.resolve(bad)

    def test_external_requires_radius_per_dataset(self):
        cfg = {"study_id": "t", "study_seed": 1, "external": {"datasets": [{"name": "a", "path": "x.csv", "units": "m"}]}}
        with self.assertRaises(config_mod.ConfigError):
            config_mod.resolve(cfg)

    def test_external_forces_accept_all(self):
        cfg = {"study_id": "t", "study_seed": 1,
               "external": {"datasets": [{"name": "a", "path": "x.csv", "units": "m", "radii": [50.0]}]}}
        self.assertEqual(config_mod.resolve(cfg)["connectivity_rule"]["mode"], "accept_all")

    def test_exact_limit_and_exclusive_modes(self):
        with self.assertRaises(config_mod.ConfigError):
            config_mod.resolve(_base_config(exact={"max_n": 25}))
        both = _base_config(external={"datasets": []})
        with self.assertRaises(config_mod.ConfigError):
            config_mod.resolve(both)

    def test_spatial_backend_validation(self):
        self.assertEqual(config_mod.resolve(_base_config())["spatial_backend"], "cgal")  # primary default
        self.assertEqual(config_mod.backends(config_mod.resolve(_base_config(spatial_backend=["cgal", "grid"]))),
                         ["cgal", "grid"])
        for bad in ("kdtree", ["cgal", "cgal"], [], "CGAL", "explicit"):
            with self.assertRaises(config_mod.ConfigError):
                config_mod.resolve(_base_config(spatial_backend=bad))

    def test_final_study_must_use_cgal_only(self):
        config_mod.resolve(_base_config(final=True))
        for other in ("grid", ["cgal", "grid"]):
            with self.assertRaises(config_mod.ConfigError):
                config_mod.resolve(_base_config(final=True, spatial_backend=other))

    def test_hash_changes_with_methodology(self):
        a = config_mod.resolve(_base_config())
        b = config_mod.resolve(_base_config(timing={"repetitions": 9}))
        self.assertNotEqual(config_mod.config_sha256(a), config_mod.config_sha256(b))


def _row(gid, algo, phase="timed", rep=0, **kw):
    base = {"graph_id": gid, "algorithm": algo, "phase": phase, "repetition": rep, "points_fingerprint": "f",
            "dataset_sha256": "d", "radius": 1.0, "solver_sha256": "s", "git_commit": "c", "machine_id": "m",
            "config_sha256": "h", "build_config": "Release", "instrumentation": "none", "execution_position": 0,
            "cds_hash": "x", "spatial_backend": "cgal", "backend_crosscheck": "identical"}
    base.update(kw)
    return base


class GenerationFeasibilityTests(unittest.TestCase):
    CB = {"clusters": 2, "spread": 0.45, "bridge_fraction": 0.25, "bridge_width": 0.6}

    def test_exact_small_cluster_bridge_cells_are_infeasible(self):
        from study.datasets import generation_feasibility
        for n in (10, 13, 16):
            ok, why = generation_feasibility("cluster_bridge", n, 3.0, 1.0, self.CB)
            self.assertFalse(ok, n)
            self.assertIn("negligible probability", why)

    def test_feasible_cells_and_other_geometries_pass(self):
        from study.datasets import generation_feasibility
        main = {"clusters": 3, "spread": 0.45, "bridge_fraction": 0.2, "bridge_width": 0.6}
        for n in (200, 500, 10000):
            self.assertTrue(generation_feasibility("cluster_bridge", n, 8.0, 1.0, main)[0], n)
        for g in ("uniform", "clustered", "perturbed_grid", "corridor"):
            self.assertTrue(generation_feasibility(g, 10, 3.0, 1.0, {})[0])

    def test_flagged_cells_never_connect_empirically(self):
        # Cross-check the analytical argument against the real generator.
        from generators import generate
        from real_dataset import _component_labels
        from study.datasets import generation_feasibility
        for n in (10, 13, 16):
            self.assertFalse(generation_feasibility("cluster_bridge", n, 3.0, 1.0, self.CB)[0])
            for seed in range(300):
                pts = generate("cluster_bridge", n, seed, density=3.0, **self.CB).points
                self.assertGreater(len(set(_component_labels(pts, 1.0))), 1, (n, seed))


class DumbbellFeasibilityTests(unittest.TestCase):
    DB = {"neck_width": 1.0, "neck_length": 3.0}

    def test_domain_rule(self):
        from study.datasets import generation_feasibility
        # n/density <= w*l: no domain
        ok, why = generation_feasibility("dumbbell", 10, 8.0, 1.0, self.DB)
        self.assertFalse(ok)
        self.assertIn("neck area", why)
        # area > w*l but square side a < w
        ok, why = generation_feasibility("dumbbell", 13, 3.0, 1.0, self.DB)
        self.assertFalse(ok)
        self.assertIn("square side", why)
        # a = sqrt((16/3 - 3)/2) ~ 1.08 >= 1: defined
        self.assertTrue(generation_feasibility("dumbbell", 16, 3.0, 1.0, self.DB)[0])

    def test_every_primary_and_pilot_cell_is_feasible(self):
        from study.datasets import generation_feasibility
        for name in ("final", "precision_pilot", "pilot", "smoke", "spatial_backend"):
            cfg = config_mod.load(REPO_ROOT / "experiments" / f"{name}.json")
            syn = cfg["synthetic"]
            for n in syn["sizes"]:
                for d in syn["densities"]:
                    self.assertTrue(generation_feasibility("dumbbell", n, d, syn["radius"],
                                                           syn["geometry_parameters"]["dumbbell"])[0], (name, n, d))


class FrozenConfigTests(unittest.TestCase):
    """Every study config uses the frozen v2 generators (generator_freeze_v2.json)."""

    def test_configs_use_d3_v2_and_dumbbell(self):
        for name in ("final", "precision_pilot", "pilot", "smoke", "spatial_backend",
                     "exact_small", "sparse_density5"):
            cfg = config_mod.load(REPO_ROOT / "experiments" / f"{name}.json")
            syn = cfg["synthetic"]
            self.assertNotIn("cluster_bridge", syn["geometries"], name)
            self.assertIn("dumbbell", syn["geometries"], name)
            self.assertEqual(syn["geometry_parameters"]["clustered"],
                             {"clusters": 4, "background_fraction": 0.5, "spread_relative": 0.05}, name)
            self.assertEqual(syn["geometry_parameters"]["dumbbell"], {"neck_width": 1.0, "neck_length": 3.0}, name)

    def test_final_primary_densities_and_sparse_study_separate(self):
        final = config_mod.load(REPO_ROOT / "experiments" / "final.json")
        self.assertEqual(final["synthetic"]["densities"], [8.0, 12.0])
        sparse = config_mod.load(REPO_ROOT / "experiments" / "sparse_density5.json")
        self.assertEqual(sparse["synthetic"]["densities"], [5.0])
        self.assertFalse(sparse["final"])

    def test_sparse_admission_matches_the_freeze_decision(self):
        from study import datasets
        cfg = config_mod.load(REPO_ROOT / "experiments" / "sparse_density5.json")
        admitted = {}
        for p in datasets.plan(cfg):
            ok, _ = datasets.calibration_feasibility(cfg["feasibility_calibration"], REPO_ROOT, p)
            admitted.setdefault(p.geometry, set())
            if ok:
                admitted[p.geometry].add(int(p.n))
        all_n = {500, 1000, 2000, 5000, 10000}
        self.assertEqual(admitted, {"uniform": all_n, "dumbbell": all_n, "perturbed_grid": all_n,
                                    "corridor": {500, 1000, 2000}, "clustered": set()})


class CalibrationGateTests(unittest.TestCase):
    def _cal(self, d, rate_ok=0.9, rate_bad=0.1):
        import hashlib
        doc = {"cells": [
            {"geometry": "uniform", "n": 100, "density": 5.0, "radius": 1.0, "graphs": 20, "connected": 18,
             "acceptance_rate": rate_ok, "acceptance_wilson_low": 0.7, "acceptance_wilson_high": 0.97},
            {"geometry": "clustered", "n": 100, "density": 5.0, "radius": 1.0, "graphs": 20, "connected": 2,
             "acceptance_rate": rate_bad, "acceptance_wilson_low": 0.03, "acceptance_wilson_high": 0.3}]}
        path = Path(d) / "cal.json"
        path.write_text(json.dumps(doc), encoding="utf-8")
        return {"file": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "min_acceptance_rate": 0.5}

    def test_admits_excludes_and_requires_coverage(self):
        from study.datasets import PlannedDataset, calibration_feasibility
        with tempfile.TemporaryDirectory() as d:
            cal = self._cal(d)
            def planned(g, n):
                return PlannedDataset(0, "x", "c", "synthetic", g, n, 1.0, "unit", 5.0, 1)
            self.assertTrue(calibration_feasibility(cal, REPO_ROOT, planned("uniform", 100))[0])
            ok, why = calibration_feasibility(cal, REPO_ROOT, planned("clustered", 100))
            self.assertFalse(ok)
            self.assertIn("2/20", why)
            ok, why = calibration_feasibility(cal, REPO_ROOT, planned("corridor", 100))
            self.assertFalse(ok)
            self.assertIn("not covered", why)

    def test_tampered_calibration_file_is_refused(self):
        from study.datasets import PlannedDataset, calibration_feasibility
        with tempfile.TemporaryDirectory() as d:
            cal = self._cal(d)
            Path(cal["file"]).write_text("{}", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                calibration_feasibility(cal, REPO_ROOT,
                                        PlannedDataset(0, "x", "c", "synthetic", "uniform", 100, 1.0, "unit", 5.0, 1))

    def test_entry_list_routes_each_geometry_to_its_own_file(self):
        from study.datasets import PlannedDataset, calibration_feasibility
        with tempfile.TemporaryDirectory() as d:
            a = self._cal(d)
            (Path(d) / "b").mkdir()
            b = self._cal(str(Path(d) / "b"), rate_ok=0.9, rate_bad=0.95)  # clustered admitted here
            cal = [dict(a, geometries=["uniform"]), dict(b, geometries=["clustered"])]
            def planned(g):
                return PlannedDataset(0, "x", "c", "synthetic", g, 100, 1.0, "unit", 5.0, 1)
            self.assertTrue(calibration_feasibility(cal, REPO_ROOT, planned("uniform"))[0])
            self.assertTrue(calibration_feasibility(cal, REPO_ROOT, planned("clustered"))[0])
            ok, why = calibration_feasibility(cal, REPO_ROOT, planned("corridor"))
            self.assertFalse(ok)
            self.assertIn("exactly one", why)

    def test_entry_list_validation(self):
        with tempfile.TemporaryDirectory() as d:
            a = self._cal(d)
            with self.assertRaises(config_mod.ConfigError):  # entries without geometries
                config_mod.resolve(_base_config(feasibility_calibration=[a, a]))
            with self.assertRaises(config_mod.ConfigError):  # geometry covered twice
                config_mod.resolve(_base_config(feasibility_calibration=[
                    dict(a, geometries=["uniform"]), dict(a, geometries=["uniform"])]))

    def test_final_study_cannot_be_calibration_gated(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(config_mod.ConfigError):
                config_mod.resolve(_base_config(final=True, feasibility_calibration=self._cal(d)))
            config_mod.resolve(_base_config(feasibility_calibration=self._cal(d)))  # non-final: allowed


class CalibrationGateEvaluationTests(unittest.TestCase):
    """The preregistered gate logic (python/calibration_gates.py) on synthetic inputs."""

    @staticmethod
    def _cell(geometry, n, d, connected, clust, deg):
        q = {"median": clust, "q1": clust - 0.01, "q3": clust + 0.01}
        dd = {"median": deg}
        return {"geometry": geometry, "n": n, "density": d, "graphs": 24, "connected": connected,
                "acceptance_rate": connected / 24, "acceptance_wilson_low": 0.0, "acceptance_wilson_high": 1.0,
                "clustering_share": q, "mean_degree": dd, "median_degree": dd, "min_degree": dd, "max_degree": dd}

    def _gates(self):
        return json.loads((REPO_ROOT / "experiments" / "calibration" / "gates_v1.json").read_text(encoding="utf-8"))

    def _calibration(self, d3_deg_growth):
        cells = []
        for n in (500, 1000, 2000, 5000, 10000):
            for d in (8.0, 12.0):
                for g in ("uniform", "perturbed_grid", "corridor", "cluster_bridge"):
                    cells.append(self._cell(g, n, d, 24, 0.16, 20.0))
                cells.append(self._cell("clustered", n, d, 20, 0.40, 20.0 * (1 + d3_deg_growth * n / 10000)))
        return {"cells": cells}

    def test_scale_stable_d3_passes_and_growing_degree_fails_g3(self):
        from calibration_gates import evaluate
        ok = evaluate(self._calibration(0.0), self._gates())
        self.assertTrue(ok["G1_pass"] and ok["G2_pass"] and ok["G3_pass"] and ok["freeze"])
        bad = evaluate(self._calibration(3.0), self._gates())  # R grows 1.15 -> 4: spread > 2
        self.assertTrue(bad["G1_pass"] and bad["G2_pass"])
        self.assertFalse(bad["G3_pass"])
        self.assertFalse(bad["freeze"])

    def test_g1_threshold_is_18_of_24(self):
        from calibration_gates import evaluate
        cal = self._calibration(0.0)
        cal["cells"][0]["connected"] = 17  # uniform n=500 d=8
        self.assertFalse(evaluate(cal, self._gates())["G1_pass"])
        cal["cells"][0]["connected"] = 18
        self.assertTrue(evaluate(cal, self._gates())["G1_pass"])


class FairnessTests(unittest.TestCase):
    def setUp(self):
        self.cfg = config_mod.resolve(_base_config(algorithms=["wan", "li"]))
        self.datasets = [{"graph_id": "g1", "points_fingerprint": "f", "dataset_sha256": "d",
                          "dataset_id": "r1", "graph_status": "ok"}]

    def tables(self, rows, datasets=None):
        return {"raw_runs": rows, "datasets": datasets or self.datasets}

    def test_clean_passes(self):
        rows = [_row("g1", "wan", execution_position=0), _row("g1", "li", execution_position=1)]
        self.assertTrue(fairness.check(self.tables(rows), self.cfg)["passed"])

    def test_different_points_is_violation(self):
        rows = [_row("g1", "wan"), _row("g1", "li", points_fingerprint="other")]
        rep = fairness.check(self.tables(rows), self.cfg)
        self.assertFalse(rep["passed"])
        self.assertTrue(any(v.startswith("V1") for v in rep["violations"]))

    def test_unequal_repetitions_is_violation(self):
        rows = [_row("g1", "wan", rep=0), _row("g1", "wan", rep=1), _row("g1", "li", rep=0)]
        self.assertTrue(any(v.startswith("V3") for v in fairness.check(self.tables(rows), self.cfg)["violations"]))

    def test_wrong_instrumentation_is_violation(self):
        rows = [_row("g1", "wan", instrumentation="basic"), _row("g1", "li", instrumentation="basic")]
        self.assertTrue(any(v.startswith("V5") for v in fairness.check(self.tables(rows), self.cfg)["violations"]))

    def test_pseudo_replication_is_violation(self):
        ds = self.datasets + [{"graph_id": "g2", "points_fingerprint": "f", "dataset_sha256": "d",
                               "dataset_id": "r2", "graph_status": "ok"}]
        rows = [_row("g1", "wan"), _row("g1", "li")]
        self.assertTrue(any(v.startswith("V4") for v in fairness.check(self.tables(rows, ds), self.cfg)["violations"]))

    def test_missing_algorithm_is_warning(self):
        rep = fairness.check(self.tables([_row("g1", "wan")]), self.cfg)
        self.assertTrue(rep["passed"])
        self.assertTrue(any(w.startswith("W1") for w in rep["warnings"]))

    def test_unrequested_backend_is_violation(self):
        rows = [_row("g1", "wan", spatial_backend="grid"), _row("g1", "li", spatial_backend="grid")]
        self.assertTrue(any(v.startswith("V7") for v in fairness.check(self.tables(rows), self.cfg)["violations"]))

    def test_backend_crosscheck_mismatch_is_violation(self):
        rows = [_row("g1", "wan", backend_crosscheck="mismatch"), _row("g1", "li")]
        self.assertTrue(any(v.startswith("V8") for v in fairness.check(self.tables(rows), self.cfg)["violations"]))

    def test_backend_changing_output_is_violation(self):
        cfg = config_mod.resolve(_base_config(algorithms=["wan", "li"], spatial_backend=["cgal", "grid"]))
        rows = [_row("g1", "wan"), _row("g1", "li"),
                _row("g1", "wan", spatial_backend="grid", backend_crosscheck="not_applicable", cds_hash="y"),
                _row("g1", "li", spatial_backend="grid", backend_crosscheck="not_applicable")]
        rep = fairness.check(self.tables(rows), cfg)
        self.assertTrue(any(v.startswith("V9") and "wan" in v for v in rep["violations"]))

    def test_memory_probe_binary_is_not_a_violation(self):
        rows = [_row("g1", "wan"), _row("g1", "li"),
                _row("g1", "wan", phase="memory_probe", solver_sha256="mem"),
                _row("g1", "li", phase="memory_probe", solver_sha256="mem")]
        self.assertTrue(fairness.check(self.tables(rows), self.cfg)["passed"])


class AnalysisTests(unittest.TestCase):
    def test_quantile_and_wilson(self):
        self.assertEqual(analysis.quantile([1.0, 2.0, 3.0, 4.0], 0.5), 2.5)
        lo, hi = analysis.wilson(10, 10)
        self.assertLess(lo, 1.0)
        self.assertAlmostEqual(hi, 1.0, places=9)

    def test_graph_level_uses_timed_median_only(self):
        base = {"cell_id": "c", "spatial_backend": "cgal", "geometry": "uniform", "n": "10",
                "density_target": "8", "radius": "1", "cds_diameter": "3",
                "source_type": "synthetic", "replicate": "1", "cds_size": "4", "cds_fraction": "0.4",
                "core_count": "", "connector_count": "", "neighbor_queries": "20", "validated": "true", "valid_solution": "true", "opt_size": "",
                "empirical_ratio": "", "algorithm_incremental_peak_bytes": "", "max_neighbors_per_query": "", "status": "ok", "failure_reason": ""}
        raw = [dict(base, graph_id="g", algorithm="wan", phase="warmup", t_algorithm_ms="100"),
               dict(base, graph_id="g", algorithm="wan", phase="timed", t_algorithm_ms="1"),
               dict(base, graph_id="g", algorithm="wan", phase="timed", t_algorithm_ms="3"),
               dict(base, graph_id="g", algorithm="wan", phase="timed", t_algorithm_ms="2")]
        gl = analysis.graph_level(raw, [{"graph_id": "g", "mean_degree": "5", "max_degree": "9"}])
        self.assertEqual(len(gl), 1)
        self.assertEqual(gl[0]["t_algorithm_ms"], 2.0)
        self.assertEqual(gl[0]["timed_repetitions"], 3)
        self.assertEqual(gl[0]["cds_diameter"], 3.0)

    def test_paired_signs_and_ratio(self):
        gl = []
        for g, (a_cds, b_cds, a_t, b_t) in enumerate([(10, 12, 1.0, 2.0), (11, 12, 2.0, 4.0), (12, 12, 3.0, 6.0)]):
            for algo, cds, t in (("wan", a_cds, a_t), ("li", b_cds, b_t)):
                gl.append({"cell_id": "c", "spatial_backend": "cgal", "graph_id": f"g{g}", "algorithm": algo,
                           "cds_size": float(cds), "t_algorithm_ms": t})
        rows = {r["metric"]: r for r in analysis.paired(gl, ["wan", "li"])}
        self.assertEqual(set(rows), {"cds_size", "t_algorithm_ms"})  # metrics without data are skipped
        cds = rows["cds_size"]
        self.assertEqual(cds["n_pairs"], 3)
        self.assertEqual((cds["a_lower"], cds["ties"], cds["b_lower"]), (2, 1, 0))
        self.assertAlmostEqual(cds["diff_mean"], -1.0)
        self.assertAlmostEqual(rows["t_algorithm_ms"]["ratio_geomean"], 0.5)
        self.assertAlmostEqual(rows["t_algorithm_ms"]["diff_mean"], -2.0)

    def test_precision_curve_uses_first_k_replicates(self):
        gl = []
        for rep in range(1, 21):
            for algo, cds in (("wan", 10.0 + (rep % 3)), ("li", 10.0)):
                gl.append({"cell_id": "c", "spatial_backend": "cgal", "graph_id": f"g{rep}", "replicate": str(rep),
                           "algorithm": algo, "cds_size": cds, "t_algorithm_ms": 1.0})
        curve = [r for r in analysis.precision_curve(gl, ["wan", "li"]) if r["metric"] == "cds_size"]
        self.assertEqual([r["k_graphs"] for r in curve], [5, 10, 15, 20])
        first5 = [(rep % 3) for rep in range(1, 6)]
        self.assertAlmostEqual(curve[0]["diff_mean"], sum(first5) / 5)
        self.assertGreater(curve[0]["ci95_half_width_normal"], curve[-1]["ci95_half_width_normal"])

    def test_pairs_never_cross_backends_and_precision_projection(self):
        gl = []
        for g in range(6):
            for backend in ("cgal", "grid"):
                for algo, cds in (("wan", 10 + g), ("li", 9 + g)):
                    gl.append({"cell_id": "c", "spatial_backend": backend, "graph_id": f"g{g}", "algorithm": algo,
                               "cds_size": float(cds), "cds_fraction": cds / 100.0, "t_algorithm_ms": 1.0 + g})
        pairs = analysis.paired(gl, ["wan", "li"])
        self.assertEqual({r["spatial_backend"] for r in pairs}, {"cgal", "grid"})
        self.assertTrue(all(r["n_pairs"] == 6 for r in pairs))  # 6 graphs, not 12 mixed rows
        bp = analysis.backend_paired(gl)
        self.assertTrue(all(r["backend_a"] == "cgal" and r["backend_b"] == "grid" for r in bp))
        prec = analysis.precision(gl)
        row = next(r for r in prec if r["metric"] == "cds_size" and r["spatial_backend"] == "cgal"
                   and r["algorithm"] == "wan")
        self.assertEqual(row["graphs"], 6)
        self.assertGreaterEqual(row["graphs_needed_rel_0.01"], row["graphs_needed_rel_0.05"])


@unittest.skipUnless(_bench_available(), "mcds_bench / mcds_bench_mem not built")
class EndToEndTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="study_test_"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, cfg) -> Path:
        cfg = copy.deepcopy(cfg)
        cfg.setdefault("output_dir", str(self.tmp / "out"))
        path = self.tmp / "cfg.json"
        path.write_text(json.dumps(cfg), encoding="utf-8")
        return path

    def _rows(self, name):
        with (self.tmp / "out" / name).open(encoding="utf-8") as h:
            return list(csv.DictReader(h))

    def test_synthetic_study_symmetry_resume_and_timing_separation(self):
        cfg = _base_config(
            synthetic={"geometries": ["uniform", "perturbed_grid"], "sizes": [60], "densities": [10.0],
                       "replicates": 2, "geometry_parameters": {"perturbed_grid": {"jitter": 0.15}}},
            timing={"repetitions": 2, "warmups": 1}, exact={"max_n": 0})
        path = self._write(cfg)
        res = Study(path, REPO_ROOT, log=lambda m: None, show_progress=False).run()
        self.assertTrue(res["fairness"]["passed"], res["fairness"])
        raw = self._rows("raw_runs.csv")
        # 4 graphs x 4 algorithms x (1 warmup + 2 timed + 1 memory probe + 1 counter pass)
        self.assertEqual(len(raw), 4 * 4 * 5)
        by_graph = {}
        for r in raw:
            by_graph.setdefault(r["graph_id"], set()).add((r["points_fingerprint"], r["radius"]))
        self.assertTrue(all(len(v) == 1 for v in by_graph.values()))
        self.assertTrue(all(r["valid_solution"] == "true" for r in raw))
        # Provenance: every row is on the primary backend, cross-checked against the grid.
        self.assertEqual({r["spatial_backend"] for r in raw}, {"cgal"})
        self.assertEqual({r["backend_crosscheck"] for r in raw}, {"identical"})
        self.assertTrue(all(r["cds_diameter"] != "" for r in raw if r["phase"] == "timed"))
        env = json.loads((self.tmp / "out" / "environment.json").read_text(encoding="utf-8"))
        self.assertTrue(env["cgal"]["available"])
        self.assertTrue(env["cgal"]["version"])
        # Timing-region separation. Wan's algorithm-stage queries are its BFS (n),
        # its rank-MIS scan (n) and one pruning query per pre-pruning black
        # vertex (>= |D|, <= n). Graph statistics (2n) and validation queries
        # would push the count outside [2n + |D|, 3n].
        for r in raw:
            if r["algorithm"] == "wan":
                n, q = int(r["n"]), int(r["neighbor_queries"])
                self.assertGreaterEqual(q, 2 * n + int(r["cds_size"]))
                self.assertLessEqual(q, 3 * n)
        # Every execution of an algorithm on a graph (warmup, timed, memory
        # probe, counter pass) reports the same algorithm-only work.
        work = {}
        for r in raw:
            work.setdefault((r["graph_id"], r["algorithm"]), set()).add(
                (r["neighbor_queries"], r["cgal_range_candidates"], r["cds_hash"]))
        # Backend-specific counters never leak into another backend's columns.
        self.assertTrue(all(r["grid_candidates_examined"] == "" and r["grid_cells_examined"] == "" for r in raw))
        self.assertTrue(all(r["cgal_range_candidates"] != "" for r in raw))
        self.assertTrue(all(len(v) == 1 for v in work.values()))
        # Resume: re-running must not duplicate anything.
        Study(path, REPO_ROOT, log=lambda m: None, show_progress=False).run()
        self.assertEqual(len(self._rows("raw_runs.csv")), len(raw))
        attempts = self._rows("generation_attempts.csv")
        self.assertEqual(sum(1 for a in attempts if a["accepted"] == "true"), 4)

    def test_backend_sensitivity_study_cgal_vs_grid_identical_outputs(self):
        cfg = _base_config(
            synthetic={"geometries": ["clustered", "corridor", "cluster_bridge"], "sizes": [80],
                       "densities": [10.0], "replicates": 2},
            spatial_backend=["cgal", "grid"], timing={"repetitions": 1, "warmups": 0},
            memory_probe=False, counter_pass=None)
        res = Study(self._write(cfg), REPO_ROOT, log=lambda m: None, show_progress=False).run()
        self.assertTrue(res["fairness"]["passed"], res["fairness"])  # includes V9: no backend changed a CDS
        raw = self._rows("raw_runs.csv")
        self.assertEqual({r["spatial_backend"] for r in raw}, {"cgal", "grid"})
        per = {}
        for r in raw:
            per.setdefault((r["graph_id"], r["algorithm"]), {})[r["spatial_backend"]] = (
                r["cds_hash"], r["neighbor_queries"], r["cds_diameter"])
        self.assertTrue(all(v["cgal"] == v["grid"] for v in per.values()))

    def test_exact_failure_keeps_heuristic_rows(self):
        # A timed-out exact search must not drop the graph (survivorship bias).
        cfg = _base_config(synthetic={"geometries": ["uniform"], "sizes": [14], "densities": [3.0], "replicates": 2},
                           timing={"repetitions": 1, "warmups": 0}, memory_probe=False, counter_pass=None,
                           exact={"max_n": 14, "timeout_seconds": 0.001})
        Study(self._write(cfg), REPO_ROOT, log=lambda m: None, show_progress=False).run()
        raw = self._rows("raw_runs.csv")
        self.assertEqual(len(raw), 2 * 4)  # every heuristic execution kept
        self.assertTrue(all(r["opt_size"] == "" and r["empirical_ratio"] == "" for r in raw))
        ds = self._rows("datasets.csv")
        self.assertEqual({d["exact_status"] for d in ds}, {"timeout"})
        self.assertTrue(any(f["phase"] == "exact.json" for f in self._rows("failures.csv")))

    def test_generation_infeasible_under_protocol_cell_is_excluded_before_generation(self):
        cfg = _base_config(
            synthetic={"geometries": ["uniform", "cluster_bridge"], "sizes": [10], "densities": [5.0],
                       "replicates": 2, "geometry_parameters": {
                           "cluster_bridge": {"clusters": 2, "spread": 0.45, "bridge_fraction": 0.25,
                                              "bridge_width": 0.6}}},
            timing={"repetitions": 1, "warmups": 0}, memory_probe=False, counter_pass=None)
        res = Study(self._write(cfg), REPO_ROOT, log=lambda m: None).run()
        self.assertTrue(res["fairness"]["passed"])
        fails = [f for f in self._rows("failures.csv") if f["status"] == "generation_infeasible_under_protocol"]
        self.assertEqual(len(fails), 2)
        self.assertTrue(all("cluster_bridge" in f["cell_id"] and f["stage"] == "dataset" for f in fails))
        # No generation attempts were spent on the infeasible cell; uniform ran normally.
        attempts = self._rows("generation_attempts.csv")
        self.assertFalse(any("cluster_bridge" in a["cell_id"] for a in attempts))
        self.assertEqual({r["geometry"] for r in self._rows("raw_runs.csv")}, {"uniform"})

    def test_changed_config_is_refused_on_resume(self):
        path = self._write(_base_config(timing={"repetitions": 1, "warmups": 0}, memory_probe=False,
                                        counter_pass=None))
        Study(path, REPO_ROOT, log=lambda m: None, show_progress=False).run(datasets_only=True)
        path = self._write(_base_config(timing={"repetitions": 2, "warmups": 0}, memory_probe=False,
                                        counter_pass=None))
        with self.assertRaises(StudyError):
            Study(path, REPO_ROOT, log=lambda m: None, show_progress=False).run(datasets_only=True)

    def test_exact_opt_and_empirical_ratio(self):
        cfg = _base_config(synthetic={"geometries": ["uniform"], "sizes": [12], "densities": [3.0], "replicates": 1},
                           timing={"repetitions": 1, "warmups": 0}, memory_probe=False, counter_pass=None,
                           exact={"max_n": 12})
        Study(self._write(cfg), REPO_ROOT, log=lambda m: None, show_progress=False).run()
        raw = self._rows("raw_runs.csv")
        for r in raw:
            self.assertNotEqual(r["opt_size"], "")
            self.assertGreaterEqual(float(r["empirical_ratio"]), 1.0)

    def test_external_real_data_failures_and_metadata(self):
        real = self.tmp / "real.csv"
        real.write_text("id,x,y\n0,0,0\n1,60,0\n2,120,0\n3,5000,5000\n", encoding="utf-8")
        (self.tmp / "real.meta.json").write_text(json.dumps({
            "units": "meters", "output_crs": "EPSG:32617", "projection_method": "utm", "sampling": "all",
            "input_sha256": "feed"}), encoding="utf-8")
        cfg = {"study_id": "ext", "study_seed": 3, "memory_probe": False, "counter_pass": None,
               "timing": {"repetitions": 1, "warmups": 0},
               "external": {"datasets": [
                   {"name": "line", "path": str(real), "radii": [70.0, 10000.0], "units": "meters"},
                   {"name": "missing", "path": str(self.tmp / "nope.csv"), "radii": [1.0], "units": "meters"}]}}
        res = Study(self._write(cfg), REPO_ROOT, log=lambda m: None, show_progress=False).run()
        self.assertTrue(res["fairness"]["passed"])
        ds = self._rows("datasets.csv")
        r70 = next(d for d in ds if d["radius"] == "70.0")
        self.assertEqual(r70["connected"], "false")
        self.assertEqual(r70["coordinate_system"], "EPSG:32617")
        self.assertEqual(r70["source_sha256"], "feed")
        statuses = {f["status"] for f in self._rows("failures.csv")}
        self.assertIn("input_disconnected", statuses)
        self.assertIn("missing_dataset", statuses)
        raw = self._rows("raw_runs.csv")
        # Disconnected radius: no algorithm rows. Connected radius: all four, at radius 10000.
        self.assertEqual({r["radius"] for r in raw}, {"10000.0"})
        self.assertEqual(len(raw), 4)

    def test_projected_real_fixture_cgal_and_grid_identical(self):
        # Small UTM-scale fixture (metres) with a declared 100 m radius, through both backends.
        import random
        rng = random.Random(7)
        lines = ["id,x,y"]
        for i in range(120):
            lines.append(f"{i},{451000.0 + rng.uniform(0, 600):.3f},{3302000.0 + rng.uniform(0, 600):.3f}")
        real = self.tmp / "utm.csv"
        real.write_text("\n".join(lines) + "\n", encoding="utf-8")
        cfg = {"study_id": "utm", "study_seed": 5, "memory_probe": False, "counter_pass": None,
               "spatial_backend": ["cgal", "grid"], "timing": {"repetitions": 1, "warmups": 0},
               "external": {"datasets": [{"name": "utm", "path": str(real), "radii": [100.0], "units": "meters"}]}}
        res = Study(self._write(cfg), REPO_ROOT, log=lambda m: None, show_progress=False).run()
        self.assertTrue(res["fairness"]["passed"], res["fairness"])
        raw = self._rows("raw_runs.csv")
        self.assertEqual({r["radius"] for r in raw}, {"100.0"})  # never radius 1.0
        self.assertEqual({r["spatial_backend"] for r in raw}, {"cgal", "grid"})
        self.assertTrue(all(r["valid_solution"] == "true" for r in raw))
        per = {}
        for r in raw:
            per.setdefault(r["algorithm"], set()).add((r["cds_hash"], r["neighbor_queries"]))
        self.assertTrue(all(len(v) == 1 for v in per.values()))


if __name__ == "__main__":
    unittest.main()
