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
        for bad in ("kdtree", ["cgal", "cgal"], [], "CGAL"):
            with self.assertRaises(config_mod.ConfigError):
                config_mod.resolve(_base_config(spatial_backend=bad))

    def test_final_study_must_use_cgal_only(self):
        config_mod.resolve(_base_config(final=True))
        for other in ("grid", ["cgal", "grid"], "explicit"):
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
                "empirical_ratio": "", "heap_peak_additional_bytes": "", "max_neighbors_per_query": "", "status": "ok", "failure_reason": ""}
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
                (r["neighbor_queries"], r["cgal_box_candidates"], r["cds_hash"]))
        # Backend-specific counters never leak into another backend's columns.
        self.assertTrue(all(r["grid_candidates_examined"] == "" and r["grid_cells_examined"] == "" for r in raw))
        self.assertTrue(all(r["cgal_box_candidates"] != "" for r in raw))
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
