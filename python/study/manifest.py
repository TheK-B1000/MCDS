"""Methodology manifest: a single JSON describing exactly what a study measures."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import METHODOLOGY_VERSION
from .config import config_sha256
from .fingerprint import sha256_file
from .schema import METRIC_TAXONOMY
from .schema import RAW_RUN_COLUMNS, SCHEMA_VERSION

# Verification status is NOT hard-coded here: it lives in docs/source_audit.md
# and the per-algorithm audits, which the manifest records by SHA-256 so the
# frozen methodology captures exactly the verification state at freeze time.
SOURCE_DOCS = {
    "_summary": "docs/source_audit.md",
    "marathe": "docs/algorithms/marathe.md",
    "wan": "docs/algorithms/wan.md",
    "funke": "docs/algorithms/funke.md",
    "li": "docs/algorithms/li_smis.md",
}


def _verified_line(text: str) -> str | None:
    for line in text.splitlines():
        if "IMPLEMENTATION VERIFIED:" in line:
            return line.replace("`", "").replace("*", "").strip()
    return None


def source_records(repo_root: Path, algorithms: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in ["_summary", *algorithms]:
        rel = SOURCE_DOCS.get(key)
        path = repo_root / rel if rel else None
        if path is None or not path.is_file():
            out[key] = {"doc": rel, "present": False}
            continue
        text = path.read_text(encoding="utf-8")
        out[key] = {"doc": rel, "present": True, "sha256": sha256_file(path),
                    "status_line": _verified_line(text)}
    return out


TIMING_METHODOLOGY = [
    "Clock: std::chrono::steady_clock (monotonic); resolution reported per build.",
    "Timed region: algorithm->solve(points, index, radius) only. Excluded: CSV load (T_dataset), "
    "index build (T_spatial_index), graph statistics (T_graph_stats), exact OPT, validation, hashing, JSON/CSV I/O.",
    "Shared preprocessing is performed once per graph (shared mode) and is identical for every algorithm.",
    "Execution order per graph from a seeded Williams design; repetitions interleaved across algorithms.",
    "Warmup executions are recorded with phase=warmup and excluded from runtime statistics.",
    "Runtime per (graph, algorithm) = median of timed repetitions; every repetition is kept raw.",
    "Primary runtime comparisons use instrumentation=none; counter passes (basic/detailed) are never timed for comparison.",
    "Memory is measured in separate untimed probe processes (mcds_bench_mem, heap-tracking allocator).",
    "Input connectivity is verified once per graph, untimed, for all algorithms; no algorithm repeats it "
    "inside solve() (Funke's private check was removed; see docs/methodology_audit.md F1).",
]

STATISTICAL_PLAN = [
    "Unit of analysis = graph; repetitions are technical replicates (median per graph).",
    "Descriptives per cell x algorithm: count, mean, median, SD, IQR, min, max; 95% bootstrap CIs (B=2000, seeded).",
    "Validity: proportion valid with Wilson 95% CI.",
    "Paired comparisons on identical graphs: CDS-size difference (mean, median, bootstrap CI, Cohen's d_z, "
    "wins/ties/losses); runtime ratio as geometric mean with bootstrap CI.",
    "Graphs where any algorithm failed/timed out are excluded from paired analysis and reported.",
    "No NHST by default; no pooling across cells.",
    "Empirical approximation ratio = |D| / OPT for exact-solved small instances only; never presented as a "
    "theoretical ratio.",
]


def build(study_dir: Path, repo_root: Path | None = None) -> dict[str, Any]:
    cfg_doc = json.loads((study_dir / "config.json").read_text(encoding="utf-8"))
    cfg = cfg_doc["config"]
    env = json.loads((study_dir / "environment.json").read_text(encoding="utf-8"))
    return {
        "methodology_version": METHODOLOGY_VERSION,
        "schema_version": SCHEMA_VERSION,
        "study_id": cfg["study_id"],
        "config_sha256": config_sha256(cfg),
        "final": cfg["final"],
        "algorithms": cfg["algorithms"],
        "source_verification": source_records(repo_root or Path(__file__).resolve().parents[2], cfg["algorithms"]),
        "algorithm_source_sha256": env.get("sources", {}).get("algorithms"),
        "shared_source_sha256": env.get("sources", {}).get("shared"),
        "design": {k: cfg[k] for k in ("synthetic", "external") if k in cfg},
        "study_seed": cfg["study_seed"],
        "seed_derivation": "sha256('graph', study_seed, geometry, n, density, radius, replicate, attempt)[:63 bits]",
        "connectivity_rule": cfg["connectivity_rule"],
        "spatial_backend": cfg["spatial_backend"],
        "spatial_backend_details": {
            "primary": "cgal: CGAL::Kd_tree + CGAL::Fuzzy_iso_box (dD Spatial Searching); adjacency decided by "
                       "the exact predicate distanceSquared(p,q) <= r^2",
            "reference": "uniform-grid GridSpatialIndex (independent implementation; validation, CDS diameter and a "
                         "full per-graph neighbour-set cross-check)",
            "oracle": "brute force O(n^2) in tests only",
            "cgal": env.get("cgal"),
            "index_lifecycle": "one index per graph per process, built before any algorithm, reused read-only by "
                               "all algorithms (counters reset per execution)",
        },
        "metric_taxonomy": METRIC_TAXONOMY,
        "validation_rules": [
            "Domination: every vertex is selected or adjacent (distance <= r) to a selected vertex.",
            "Connectivity: the subgraph induced by the selected set is connected (BFS over selected vertices only).",
            "Validator is independent of algorithm internals (sees points, index, ids, radius only).",
        ],
        "timing": cfg["timing"],
        "timing_methodology": TIMING_METHODOLOGY,
        "memory_probe": cfg["memory_probe"],
        "counter_pass": cfg["counter_pass"],
        "exact": cfg["exact"],
        "metrics_raw_columns": RAW_RUN_COLUMNS,
        "statistical_plan": STATISTICAL_PLAN,
        "hardware": {"cpu": env["cpu"], "memory": env["memory"], "os": env["os"], "machine_id": env["machine_id"],
                     "power_plan": env.get("power_plan")},
        "software": {"solver_build": env.get("solver_build"), "python": env["python"],
                     "python_packages": env["python_packages"], "solvers": env["solvers"], "git": env["git"],
                     "cgal": env.get("cgal")},
    }


def write(study_dir: Path) -> Path:
    path = study_dir / "methodology_manifest.json"
    path.write_text(json.dumps(build(study_dir), indent=2) + "\n", encoding="utf-8")
    return path
