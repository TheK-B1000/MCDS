"""Study orchestration (the project's single experiment runner).

Layout of a study directory (``cfg["output_dir"]``)::

    config.json              resolved config (+ sha256); immutable once written
    environment.json         snapshot at study start
    environment_history.jsonl  one line per (re)start
    state/datasets/*.json    one record per planned dataset (all attempts)
    graphs/<graph_id>/       raw bench JSON per graph and step
    datasets/                generated CSVs (accepted instances)
    raw_runs.csv  datasets.csv  generation_attempts.csv  failures.csv
    fairness_report.json

The CSVs are *derived*: they are rebuilt from the per-graph JSON artifacts on
every run, so a resumed study can never contain duplicated or half-written rows.
"""

from __future__ import annotations

import csv
import json
import os
import time
from pathlib import Path
from typing import Any, Callable

from . import METHODOLOGY_VERSION
from . import bench as bench_mod
from . import config as config_mod
from . import datasets as datasets_mod
from . import environment as env_mod
from . import fairness
from . import progress as progress_mod
from .schedule import execution_order, schedule_index
from .schema import (
    DATASET_COLUMNS,
    FAILURE_COLUMNS,
    GENERATION_ATTEMPT_COLUMNS,
    PHASE_COUNTERS,
    PHASE_MEMORY,
    RAW_RUN_COLUMNS,
    SCHEMA_VERSION,
)


class StudyError(RuntimeError):
    pass


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_csv(path: Path, columns: list[str], rows: list[dict[str, Any]]) -> None:
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="raise")
        writer.writeheader()
        for row in rows:
            writer.writerow({c: _cell(row.get(c)) for c in columns})
    os.replace(tmp, path)


def _display_path(path: str, root: Path) -> str:
    """Repo-relative when possible (portable), absolute otherwise."""
    try:
        return Path(path).resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def _backend_counters(backend: str, run: dict[str, Any], queries: Any) -> dict[str, Any]:
    """Backend-specific work counters, each under its own backend's name.

    grid: points in scanned cells (incl. the query point), exact distance
    tests (= candidates - queries), cells scanned. cgal: points reported by the
    CGAL Fuzzy_iso_box search (incl. the query point) and the exact distance
    tests on them; CGAL's internal kd-tree node visits are not exposed and are
    not reported. explicit: no per-query candidate work exists.
    """
    cand = run.get("candidates_examined")
    out: dict[str, Any] = {}
    if backend == "grid":
        out["grid_candidates_examined"] = cand
        out["grid_distance_computations"] = run.get("distance_computations")
        out["grid_avg_candidates_per_query"] = (cand / queries) if (queries and cand is not None) else None
        out["grid_cells_examined"] = run.get("cells_examined")
        out["grid_max_candidates_per_query"] = run.get("max_candidates_per_query")
    elif backend == "cgal":
        out["cgal_box_candidates"] = cand
        out["cgal_exact_distance_evaluations"] = run.get("distance_computations")
        out["cgal_max_box_candidates_per_query"] = run.get("max_candidates_per_query")
    return out


def _cell(v: Any) -> Any:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    return v


class Study:
    def __init__(self, config_path: Path, repo_root: Path, *, log: Callable[[str], None] | None = None,
                 allow_dirty: bool = False, allow_environment_change: bool = False,
                 show_progress: bool = True):
        self.repo_root = repo_root
        self.config_path = config_path
        self.cfg = config_mod.load(config_path)
        self.config_sha = config_mod.config_sha256(self.cfg)
        out = Path(self.cfg["output_dir"])
        self.out = out if out.is_absolute() else repo_root / out
        self.show_progress = show_progress
        self.log = progress_mod.make_logger(log)
        self.allow_dirty = allow_dirty
        self.allow_environment_change = allow_environment_change
        self.bench = bench_mod.find_binary(repo_root, "mcds_bench")
        self.bench_mem = bench_mod.find_binary(repo_root, "mcds_bench_mem") if self.cfg["memory_probe"] else None
        self.env: dict[str, Any] = {}
        self.current: dict[str, Any] = {}

    # ------------------------------------------------------------------ setup
    @property
    def study_id(self) -> str:
        return self.cfg["study_id"]

    @property
    def experiment_id(self) -> str:
        return f"{self.study_id}@{self.config_sha[:12]}"

    def _init_dir(self) -> None:
        self.out.mkdir(parents=True, exist_ok=True)
        cfg_file = self.out / "config.json"
        if not cfg_file.is_file() and any(self.out.iterdir()):
            raise StudyError(
                f"{self.out} already contains files that were not written by this runner "
                "(e.g. pre-upgrade results). Move them or choose another study_id / output_dir."
            )
        if cfg_file.is_file():
            existing = _read_json(cfg_file)
            if existing.get("config_sha256") != self.config_sha:
                raise StudyError(
                    f"{cfg_file} was written by a different configuration "
                    f"({existing.get('config_sha256', '?')[:12]} != {self.config_sha[:12]}). "
                    "Methodology changes require a new study_id / output_dir."
                )
        else:
            _atomic_json(cfg_file, {"config_sha256": self.config_sha, "config": self.cfg,
                                    "source_config_path": str(self.config_path),
                                    "methodology_version": METHODOLOGY_VERSION, "schema_version": SCHEMA_VERSION})

        solvers = {"mcds_bench": self.bench}
        if self.bench_mem:
            solvers["mcds_bench_mem"] = self.bench_mem
        snap = env_mod.snapshot(self.repo_root, solvers, bench_mod.build_info(self.bench))
        if snap["git"]["dirty"] and self.cfg["final"] and not self.allow_dirty:
            raise StudyError("final study refused: git working tree is dirty (commit first or pass --allow-dirty)")
        if snap["git"]["dirty"]:
            self.log("WARNING: git working tree is dirty; results will record git_dirty=true.")
        build = snap.get("solver_build") or {}
        needs_cgal = [b for b in config_mod.backends(self.cfg) if b in ("cgal", "explicit")]
        if needs_cgal and not build.get("cgal_available"):
            raise StudyError(f"config requests spatial backend(s) {needs_cgal} but the solver was built without "
                             "CGAL (MCDS_WITH_CGAL=OFF or CGAL not found). Refusing to run: no fallback to grid.")
        if build.get("config") not in ("Release", None) or build.get("ndebug") is False:
            msg = f"solver build is {build.get('config')!r} (ndebug={build.get('ndebug')}); timings unreliable"
            if self.cfg["final"]:
                raise StudyError(msg)
            self.log("WARNING: " + msg)

        env_file = self.out / "environment.json"
        if env_file.is_file():
            first = _read_json(env_file)
            changed = [k for k in ("machine_id",) if first.get(k) != snap.get(k)]
            if first["solvers"]["mcds_bench"]["sha256"] != snap["solvers"]["mcds_bench"]["sha256"]:
                changed.append("solver_sha256")
            if first["git"].get("commit") != snap["git"].get("commit"):
                changed.append("git_commit")
            if changed and not self.allow_environment_change:
                raise StudyError(f"environment changed since study start ({changed}); "
                                 "resuming would mix conditions. Use a new study or --allow-environment-change.")
            self.env = first
        else:
            env_mod.write(env_file, snap)
            self.env = snap
        self.current = snap
        with (self.out / "environment_history.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(snap) + "\n")

    # --------------------------------------------------------------- datasets
    def _dataset_state_path(self, p: datasets_mod.PlannedDataset) -> Path:
        return self.out / "state" / "datasets" / f"{p.plan_index:06d}_{p.key}.json"

    def prepare_datasets(self) -> list[dict[str, Any]]:
        planned = datasets_mod.plan(self.cfg)
        records: list[dict[str, Any] | None] = [None] * len(planned)
        pending = [p for p in planned if not self._dataset_state_path(p).is_file()]
        cached = len(planned) - len(pending)
        progress_mod.announce(
            f"datasets: {len(planned)} planned, {cached} cached, {len(pending)} to generate",
            enabled=self.show_progress,
        )
        # Load cached first (instant); bar covers only remaining work so ETA is honest.
        for p in planned:
            path = self._dataset_state_path(p)
            if path.is_file():
                records[p.plan_index] = _read_json(path)
        with progress_mod.track(
            pending,
            total=len(pending),
            desc=f"{self.study_id} datasets",
            unit="graph",
            enabled=self.show_progress,
        ) as bar:
            for p in bar:
                path = self._dataset_state_path(p)
                rec = datasets_mod.prepare(p, self.cfg, self.repo_root, self.out, self.bench)
                _atomic_json(path, rec)
                records[p.plan_index] = rec
                if not self.show_progress or rec["status"] != "ok":
                    self.log(
                        f"[dataset {p.plan_index + 1}/{len(planned)}] {p.dataset_id}: "
                        f"{rec['status']} (attempts={len(rec['attempts'])})"
                    )
                if hasattr(bar, "set_postfix_str"):
                    bar.set_postfix_str(f"{rec['status']} {p.dataset_id[:36]}", refresh=False)
        return [r for r in records if r is not None]

    # ------------------------------------------------------------------- runs
    def _graph_dir(self, rec: dict[str, Any]) -> Path:
        return self.out / "graphs" / rec["graph_id"]

    def _steps(self, rec: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
        """Execution steps for one graph.

        Every step of a backend gives all algorithms the same backend; a
        backend is never mixed within an algorithm comparison. With several
        backends (sensitivity / ablation studies only) the backend order
        alternates between replicates so neither backend always runs first.
        """
        t = self.cfg["timing"]
        algos = self.cfg["algorithms"]
        sidx = schedule_index(self.cfg["study_seed"], rec["planned"])
        order, row = execution_order(algos, self.cfg["study_seed"], sidx)
        backends = config_mod.backends(self.cfg)
        shift = sidx % len(backends)
        backends = backends[shift:] + backends[:shift]
        steps: list[tuple[str, dict[str, Any]]] = []
        # Exact OPT never runs inside a timing process: it has its own step
        # (below) so a slow or failing exact search cannot lose heuristic rows.
        common = {"exact_max_n": 0, "validate": t["validate"]}
        for b in backends:
            if t["process_mode"] == "shared":
                steps.append((f"timing__{b}.json", {"binary": self.bench, "algorithms": order,
                                                    "repetitions": t["repetitions"], "warmups": t["warmups"],
                                                    "instrumentation": t["instrumentation"],
                                                    "emit_solution": True, "spatial_backend": b, **common}))
            else:
                for a in order:
                    steps.append((f"timing__{b}__{a}.json", {"binary": self.bench, "algorithms": [a],
                                                             "repetitions": t["repetitions"], "warmups": t["warmups"],
                                                             "instrumentation": t["instrumentation"],
                                                             "emit_solution": True, "spatial_backend": b, **common}))
            if self.bench_mem is not None:
                for a in order:
                    steps.append((f"memory__{b}__{a}.json", {"binary": self.bench_mem, "algorithms": [a],
                                                             "repetitions": 1, "warmups": 0, "instrumentation": "none",
                                                             "exact_max_n": 0, "validate": "all",
                                                             "spatial_backend": b}))
            if self.cfg["counter_pass"]:
                steps.append((f"counters__{b}.json", {"binary": self.bench, "algorithms": order, "repetitions": 1,
                                                      "warmups": 0, "instrumentation": self.cfg["counter_pass"],
                                                      "exact_max_n": 0, "validate": "all", "spatial_backend": b}))
        max_n = int(self.cfg["exact"]["max_n"])
        if max_n > 0:
            steps.append(("exact.json", {"binary": self.bench, "algorithms": None, "repetitions": 1, "warmups": 0,
                                         "instrumentation": "none", "exact_max_n": max_n, "validate": "all",
                                         "spatial_backend": config_mod.backends(self.cfg)[0], "graph_only": True,
                                         "timeout_s": float(self.cfg["exact"]["timeout_seconds"])}))
        for _, st in steps:
            st["schedule_row"] = row
            st["order"] = order
        return steps

    def run_graphs(self, records: list[dict[str, Any]]) -> None:
        runnable = [r for r in records if r["status"] == "ok"]
        timeout = float(self.cfg["timing"]["timeout_seconds"])
        pending: list[tuple[dict[str, Any], str, dict[str, Any]]] = []
        for rec in runnable:
            gdir = self._graph_dir(rec)
            gdir.mkdir(parents=True, exist_ok=True)
            for fname, step in self._steps(rec):
                target = gdir / fname
                failed = gdir / (fname + ".failed.json")
                if target.is_file() or failed.is_file():
                    continue
                pending.append((rec, fname, step))

        remaining_by_graph: dict[str, int] = {}
        for rec, _, _ in pending:
            remaining_by_graph[rec["graph_id"]] = remaining_by_graph.get(rec["graph_id"], 0) + 1
        n_graphs = len(remaining_by_graph)
        progress_mod.announce(
            f"executions: {len(pending)} pending steps across {n_graphs} graphs "
            f"({len(runnable) - n_graphs} graphs already complete)",
            enabled=self.show_progress,
        )

        with progress_mod.track(
            pending,
            total=len(pending),
            desc=f"{self.study_id} exec",
            unit="step",
            enabled=self.show_progress,
        ) as bar:
            for rec, fname, step in bar:
                gdir = self._graph_dir(rec)
                target = gdir / fname
                failed = gdir / (fname + ".failed.json")
                label = f"{rec['planned']['dataset_id'][:32]} {fname}"
                if hasattr(bar, "set_postfix_str"):
                    bar.set_postfix_str(label[:48], refresh=False)
                t0 = time.perf_counter()
                outcome = bench_mod.run_bench(
                    step["binary"], Path(rec["csv_path"]), rec["planned"]["radius"],
                    spatial_backend=step["spatial_backend"], algorithms=step["algorithms"],
                    repetitions=step["repetitions"], warmups=step["warmups"],
                    instrumentation=step["instrumentation"], validate=step["validate"],
                    exact_max_n=step["exact_max_n"], emit_solution=step.get("emit_solution", False),
                    graph_only=step.get("graph_only", False),
                    timeout_s=step.get("timeout_s", timeout), output_json=target,
                )
                if not outcome.ok:
                    _atomic_json(failed, {"step": fname, "error": outcome.error, "returncode": outcome.returncode,
                                          "algorithms": step["algorithms"]})
                    self.log(f"  FAILED {rec['planned']['dataset_id']} {fname}: {outcome.error}")
                else:
                    fp = outcome.data["input"]["points_fingerprint"]
                    if fp != rec["points_fingerprint"]:
                        raise StudyError(
                            f"FAIRNESS VIOLATION: {fname} for {rec['planned']['dataset_id']} "
                            f"saw fingerprint {fp}, expected {rec['points_fingerprint']}"
                        )
                    solver_name = "mcds_bench_mem" if step["binary"] == self.bench_mem else "mcds_bench"
                    _atomic_json(gdir / (fname + ".meta.json"), {
                        "schedule_row": step["schedule_row"], "order": step["order"],
                        "spatial_backend": step["spatial_backend"],
                        "wall_s": time.perf_counter() - t0,
                        # Provenance at execution time (not study start), so a
                        # resumed study can never mislabel rows.
                        "git_commit": self.current["git"]["commit"], "git_dirty": self.current["git"]["dirty"],
                        "machine_id": self.current["machine_id"],
                        "solver_sha256": self.current["solvers"][solver_name]["sha256"],
                        "build_config": (self.current.get("solver_build") or {}).get("config"),
                    })
                gid = rec["graph_id"]
                remaining_by_graph[gid] -= 1
                if remaining_by_graph[gid] == 0 and not self.show_progress:
                    self.log(f"[graph] {rec['planned']['dataset_id']} done")

    # --------------------------------------------------------------- assembly
    def assemble(self, records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        env = self.env or (_read_json(self.out / "environment.json") if (self.out / "environment.json").is_file() else {})
        git = env.get("git", {})
        alg_src = env.get("sources", {}).get("algorithms", {})
        solver_sha = env.get("solvers", {}).get("mcds_bench", {}).get("sha256")
        build_cfg = (env.get("solver_build") or {}).get("config")

        raw: list[dict[str, Any]] = []
        datasets: list[dict[str, Any]] = []
        attempts: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []

        for rec in records:
            p = rec["planned"]
            for a in rec["attempts"]:
                attempts.append({"schema_version": SCHEMA_VERSION, "study_id": self.study_id, "cell_id": p["cell_id"],
                                 "dataset_id": p["dataset_id"], "replicate": p["replicate"], "geometry": p["geometry"],
                                 "n": p["n"], "density_target": p["density_target"], "radius": p["radius"], **a})
            if rec["status"] != "ok":
                failures.append({"schema_version": SCHEMA_VERSION, "study_id": self.study_id, "stage": "dataset",
                                 "graph_id": rec.get("graph_id"), "dataset_id": p["dataset_id"], "cell_id": p["cell_id"],
                                 "status": rec["status"], "detail": rec.get("error", "")})
            if "probe" not in rec:
                continue

            probe = rec["probe"]
            g = probe["graph"]
            real = rec.get("real_metadata") or {}
            gdir = self._graph_dir(rec)
            exact: dict[str, Any] = {"status": "disabled"}
            t_exact = None
            if int(self.cfg["exact"]["max_n"]) > 0:
                exact_file = gdir / "exact.json"
                exact_failed = gdir / "exact.json.failed.json"
                if exact_file.is_file():
                    exact_doc = _read_json(exact_file)
                    exact = exact_doc.get("exact", {})
                    t_exact = exact_doc["timing_ms"]["exact"]
                elif exact_failed.is_file():
                    err = _read_json(exact_failed).get("error") or ""
                    exact = {"status": "timeout" if err.startswith("timeout") else "error", "error": err}
                else:
                    exact = {"status": "not_run"}
            opt = exact.get("opt_size") if exact.get("status") == "computed" else None
            tm = probe["timing_ms"]
            idx = probe["index"]
            bbox = probe["input"]["bbox"]
            datasets.append({
                "schema_version": SCHEMA_VERSION, "study_id": self.study_id, "graph_id": rec["graph_id"],
                "dataset_id": p["dataset_id"], "cell_id": p["cell_id"], "replicate": p["replicate"],
                "source_type": p["source_type"], "geometry": p["geometry"], "n": probe["input"]["n"],
                "radius": p["radius"], "radius_units": p["radius_units"], "density_target": p["density_target"],
                "target_expected_degree": datasets_mod.target_expected_degree(p["density_target"], p["radius"]),
                "graph_seed": rec.get("graph_seed"), "generation_attempt": rec.get("generation_attempt"),
                "dataset_path": _display_path(rec["csv_path"], self.repo_root),
                "dataset_sha256": rec["dataset_sha256"], "points_fingerprint": rec["points_fingerprint"],
                "source_path": p.get("source_path") or p.get("external_path"),
                "source_sha256": real.get("source_sha256"),
                "coordinate_system": real.get("coordinate_system") or ("synthetic_planar" if p["source_type"] == "synthetic" else None),
                "projection": real.get("projection"), "units": real.get("units") or p["radius_units"],
                "sampling": real.get("sampling"),
                "bbox_min_x": bbox[0], "bbox_min_y": bbox[1], "bbox_max_x": bbox[2], "bbox_max_y": bbox[3],
                "generator_parameters_json": json.dumps(rec.get("generator_parameters", {}), sort_keys=True),
                "probe_spatial_backend": probe["spatial_backend"],
                "backend_crosscheck": probe["backend_crosscheck"]["status"],
                "t_dataset_ms": tm["dataset"], "t_spatial_index_ms": tm["spatial_index"],
                "t_graph_stats_ms": tm["graph_stats"], "t_connectivity_ms": tm.get("connectivity"),
                "t_exact_ms": t_exact,
                "index_backend": idx["backend"], "index_cell_size": idx.get("cell_size"),
                "index_cells": (idx["cells_x"] * idx["cells_y"]) if "cells_x" in idx else None,
                "index_bytes": idx.get("index_bytes"),
                "dataset_bytes": probe["input"]["dataset_bytes"],
                "edges": g["edges"], "mean_degree": g["mean_degree"], "min_degree": g["min_degree"],
                "max_degree": g["max_degree"], "median_degree": g["median_degree"], "degree_std": g["degree_std"],
                "graph_density": g["graph_density"], "isolated_count": g["isolated_count"],
                "component_count": g["component_count"], "largest_component": g["largest_component"],
                "connected": g["connected"], "opt_size": opt, "exact_status": exact.get("status"),
                "graph_status": rec["status"],
            })
            if rec["status"] != "ok" or not gdir.is_dir():
                continue

            for failed in sorted(gdir.glob("*.failed.json")):
                info = _read_json(failed)
                for a in info.get("algorithms") or [""]:
                    failures.append({"schema_version": SCHEMA_VERSION, "study_id": self.study_id, "stage": "execution",
                                     "graph_id": rec["graph_id"], "dataset_id": p["dataset_id"], "cell_id": p["cell_id"],
                                     "algorithm": a, "phase": info["step"], "status": "bench_failed",
                                     "detail": info.get("error", "")})

            for f in sorted(gdir.glob("*.json")):
                if f.name.endswith((".meta.json", ".failed.json")) or f.name == "exact.json":
                    continue
                meta_path = f.with_name(f.name + ".meta.json")
                meta = _read_json(meta_path) if meta_path.is_file() else {}
                data = _read_json(f)
                phase_override = PHASE_MEMORY if f.name.startswith("memory__") else (
                    PHASE_COUNTERS if f.name.startswith("counters__") else None)
                process_mode = self.cfg["timing"]["process_mode"] if f.name.startswith("timing") else "isolated" \
                    if phase_override == PHASE_MEMORY else "shared"
                for run in data.get("runs", []):
                    row = self._raw_row(rec, data, run, meta, phase_override, process_mode, opt,
                                        git, alg_src, solver_sha, build_cfg, env.get("machine_id"))
                    raw.append(row)
                    if row["status"] not in ("ok", "ok_unvalidated"):
                        failures.append({"schema_version": SCHEMA_VERSION, "study_id": self.study_id,
                                         "stage": "execution", "graph_id": rec["graph_id"], "dataset_id": p["dataset_id"],
                                         "cell_id": p["cell_id"], "algorithm": row["algorithm"], "phase": row["phase"],
                                         "repetition": row["repetition"], "status": row["status"],
                                         "detail": row.get("failure_reason") or row.get("error") or ""})
        return {"raw_runs": raw, "datasets": datasets, "generation_attempts": attempts, "failures": failures}

    def _raw_row(self, rec, data, run, meta, phase_override, process_mode, opt, git, alg_src, solver_sha,
                 build_cfg, machine_id) -> dict[str, Any]:
        p = rec["planned"]
        phase = phase_override or run["phase"]
        n = data["input"]["n"]
        q = run.get("neighbor_queries")
        cds = run.get("cds_size")
        algo = run["algorithm"]
        order = meta.get("order") or data.get("execution_order")
        return {
            "schema_version": SCHEMA_VERSION, "methodology_version": METHODOLOGY_VERSION, "study_id": self.study_id,
            "experiment_id": self.experiment_id, "config_sha256": self.config_sha,
            "trial_id": f"{rec['graph_id']}:{algo}:{phase}:{run['repetition']}",
            "graph_id": rec["graph_id"], "dataset_id": p["dataset_id"], "cell_id": p["cell_id"],
            "replicate": p["replicate"], "graph_seed": rec.get("graph_seed"), "algorithm": algo,
            "algorithm_seed": "n/a (deterministic)", "algorithm_source_sha256": alg_src.get(algo),
            "git_commit": meta.get("git_commit", git.get("commit")),
            "git_dirty": meta.get("git_dirty", git.get("dirty")),
            "machine_id": meta.get("machine_id", machine_id),
            "solver_sha256": meta.get("solver_sha256", solver_sha),
            "build_config": meta.get("build_config", build_cfg),
            "source_type": p["source_type"], "geometry": p["geometry"], "n": n, "radius": p["radius"],
            "radius_units": p["radius_units"], "density_target": p["density_target"],
            "dataset_sha256": rec["dataset_sha256"], "points_fingerprint": data["input"]["points_fingerprint"],
            "spatial_backend": data["spatial_backend"], "spatial_index_name": data["index"]["backend"],
            "t_spatial_index_ms": data["timing_ms"]["spatial_index"],
            "index_bytes": data["index"].get("index_bytes"),
            "index_heap_peak_bytes": data["index"].get("index_heap_peak_bytes"),
            "backend_crosscheck": data["backend_crosscheck"]["status"],
            "phase": phase, "repetition": run["repetition"], "sequence": run["sequence"],
            "process_mode": process_mode, "instrumentation": data["instrumentation"],
            "execution_order": ">".join(order or []),
            "execution_position": (order.index(algo) if order and algo in order else run["execution_position"]),
            "schedule_row": meta.get("schedule_row"),
            "t_algorithm_ns": run["t_algorithm_ns"], "t_algorithm_ms": run["t_algorithm_ms"],
            "t_validation_ms": run.get("t_validation_ms"),
            "neighbor_queries": q,
            **_backend_counters(data["spatial_backend"], run, q),
            "neighbors_returned": run.get("neighbors_returned"),
            "avg_neighbors_per_query": (run["neighbors_returned"] / q) if q else None,
            "max_neighbors_per_query": run.get("max_neighbors_per_query"),
            "query_time_ns": run.get("query_time_ns"),
            "heap_peak_additional_bytes": run.get("heap_peak_additional_bytes"),
            "heap_allocation_count": run.get("heap_allocation_count"),
            "heap_allocated_bytes": run.get("heap_allocated_bytes"),
            "rss_before_algorithm_bytes": run.get("rss_before_algorithm_bytes"),
            "process_peak_rss_bytes": run.get("process_peak_rss_bytes"),
            "cds_size": cds, "cds_fraction": (cds / n) if (cds is not None and n) else None,
            "core_count": run.get("core_count"), "connector_count": run.get("connector_count"),
            "roles_reported": run.get("roles_reported"), "duplicate_ids": run.get("duplicate_ids"),
            "cds_hash": run.get("cds_hash"), "cds_diameter": run.get("cds_diameter"), "opt_size": opt,
            "empirical_ratio": (cds / opt) if (cds is not None and opt) else None,
            "validated": run.get("validated"), "valid_solution": run.get("valid_solution"),
            "domination_valid": run.get("domination_valid"), "connectivity_valid": run.get("connectivity_valid"),
            "undominated_count": run.get("undominated_count"), "failure_reason": run.get("failure_reason"),
            "status": run["status"], "error": run.get("error"),
        }

    def write_outputs(self, tables: dict[str, list[dict[str, Any]]]) -> None:
        _write_csv(self.out / "raw_runs.csv", RAW_RUN_COLUMNS, tables["raw_runs"])
        _write_csv(self.out / "datasets.csv", DATASET_COLUMNS, tables["datasets"])
        _write_csv(self.out / "generation_attempts.csv", GENERATION_ATTEMPT_COLUMNS, tables["generation_attempts"])
        _write_csv(self.out / "failures.csv", FAILURE_COLUMNS, tables["failures"])

    # --------------------------------------------------------------- preflight
    def preflight(self) -> None:
        """Every configured algorithm must return a valid CDS on a small connected
        graph before a campaign starts (ported from the pre-upgrade preflight)."""
        import tempfile  # noqa: PLC0415

        from generators import generate, write_csv  # noqa: PLC0415

        with tempfile.TemporaryDirectory(prefix="mcds_preflight_") as d:
            csv_path = Path(d) / "preflight.csv"
            write_csv(str(csv_path), generate("perturbed_grid", 64, 1, density=8.0, jitter=0.15).points)
            binaries = [self.bench] + ([self.bench_mem] if self.bench_mem else [])
            for binary, backend in ((bin_, b) for bin_ in binaries for b in config_mod.backends(self.cfg)):
                out = bench_mod.run_bench(binary, csv_path, 1.0, spatial_backend=backend,
                                          algorithms=self.cfg["algorithms"], repetitions=1, warmups=0,
                                          timeout_s=300)
                if not out.ok or out.data is None:
                    raise StudyError(f"preflight failed for {binary.name} / {backend}: {out.error}")
                if out.data.get("status") != "ok":
                    raise StudyError(f"preflight graph unexpectedly {out.data.get('status')}")
                bad = [r["algorithm"] for r in out.data["runs"] if r.get("status") != "ok"]
                if bad or len(out.data["runs"]) != len(self.cfg["algorithms"]):
                    raise StudyError(f"preflight: invalid or missing results from {binary.name}: {bad}")
        self.log(f"preflight: all {len(self.cfg['algorithms'])} algorithms returned valid CDSs on "
                 f"backend(s) {config_mod.backends(self.cfg)}")

    # -------------------------------------------------------------------- run
    def run(self, *, datasets_only: bool = False, skip_preflight: bool = False) -> dict[str, Any]:
        progress_mod.announce(f"=== study {self.study_id} ===", enabled=self.show_progress)
        self._init_dir()
        if not datasets_only and not skip_preflight:
            progress_mod.announce("phase: preflight", enabled=self.show_progress)
            self.preflight()
        progress_mod.announce("phase: datasets", enabled=self.show_progress)
        records = self.prepare_datasets()
        if not datasets_only:
            progress_mod.announce("phase: executions", enabled=self.show_progress)
            self.run_graphs(records)
        progress_mod.announce("phase: assemble + fairness", enabled=self.show_progress)
        tables = self.assemble(records)
        self.write_outputs(tables)
        report = fairness.check(tables, self.cfg)
        _atomic_json(self.out / "fairness_report.json", report)
        self.log(f"fairness: {'PASS' if report['passed'] else 'FAIL'} "
                 f"({len(report['violations'])} violation(s), {len(report['warnings'])} warning(s))")
        return {"out": str(self.out), "fairness": report, "rows": len(tables["raw_runs"])}

    def rebuild(self) -> dict[str, Any]:
        """Re-assemble CSVs and re-check fairness from stored artifacts only."""
        records = [_read_json(p) for p in sorted((self.out / "state" / "datasets").glob("*.json"))]
        self.env = _read_json(self.out / "environment.json")
        tables = self.assemble(records)
        self.write_outputs(tables)
        report = fairness.check(tables, self.cfg)
        _atomic_json(self.out / "fairness_report.json", report)
        return {"out": str(self.out), "fairness": report, "rows": len(tables["raw_runs"])}
