"""Statistical summaries for MCDS studies (standard library only).

Unit of analysis = one graph instance. Timed repetitions on a graph are
*technical* replicates of one measurement, so they are summarised by their
median per (graph, backend, algorithm) before any between-graph statistic is
computed. Treating repetitions as independent observations would understate
uncertainty (pseudo-replication).

Every grouping includes the spatial backend. A primary study has exactly one
backend (cgal); comparisons ACROSS backends appear only in
`backend_paired.csv`, never in the algorithm comparison `paired.csv`.

Methods (also written to analysis_notes.md next to the outputs):
  * descriptive: count, mean, median, SD, Q1, Q3, IQR, min, max
  * 95% percentile-bootstrap CIs for mean and median (seeded, B resamples)
  * validity: proportion of executions returning a valid CDS + Wilson 95% CI
  * paired algorithm comparisons on identical graphs, per metric:
    difference A - B (mean, median, SD, bootstrap CI of the mean, Cohen's d_z,
    wins / ties / losses with "lower is better"); for runtime additionally the
    ratio A / B as a geometric mean with bootstrap CI (log scale)
  * precision table (pilot planning aid): CI half-widths now and the number of
    graphs a normal approximation projects for target precisions
  * no null-hypothesis significance tests are run
"""

from __future__ import annotations

import csv
import math
import statistics
from collections import defaultdict
from itertools import combinations
from pathlib import Path
from typing import Any, Iterable

from .schema import PHASE_COUNTERS, PHASE_MEMORY, PHASE_TIMED
from .seeds import seeded_rng

BOOTSTRAP_B = 2000
SUMMARY_METRICS = (
    "t_algorithm_ms", "cds_size", "cds_fraction", "cds_diameter", "core_count", "connector_count",
    "neighbor_queries", "neighbors_returned", "grid_candidates_examined", "grid_distance_computations",
    "cgal_box_candidates", "cgal_exact_distance_evaluations",
    "heap_peak_additional_bytes", "t_spatial_index_ms", "t_index_plus_algorithm_ms", "index_bytes",
    "index_heap_peak_bytes", "empirical_ratio",
)
# Paired metrics: lower is better for all of them.
PAIRED_METRICS = ("t_algorithm_ms", "cds_size", "cds_fraction", "cds_diameter")
PRECISION_METRICS = ("t_algorithm_ms", "cds_size", "cds_fraction")
PRECISION_TARGETS = (0.01, 0.02, 0.05)  # relative CI half-width targets
Z95 = 1.959963984540054


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _f(v: Any) -> float | None:
    if v in (None, ""):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def quantile(sorted_xs: list[float], q: float) -> float:
    """Linear interpolation between order statistics (type 7, as in R/numpy default)."""
    if not sorted_xs:
        return float("nan")
    pos = (len(sorted_xs) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    return sorted_xs[lo] + (sorted_xs[hi] - sorted_xs[lo]) * (pos - lo)


def bootstrap_ci(xs: list[float], stat, rng, b: int = BOOTSTRAP_B, level: float = 0.95) -> tuple[float, float]:
    if len(xs) < 2:
        return (float("nan"), float("nan"))
    n = len(xs)
    reps = sorted(stat([xs[rng.randrange(n)] for _ in range(n)]) for _ in range(b))
    alpha = (1 - level) / 2
    return quantile(reps, alpha), quantile(reps, 1 - alpha)


def describe(xs: list[float], seed_parts: tuple) -> dict[str, Any]:
    xs = [x for x in xs if x is not None]
    if not xs:
        return {"count": 0}
    s = sorted(xs)
    rng = seeded_rng("bootstrap", *seed_parts)
    mean_lo, mean_hi = bootstrap_ci(xs, statistics.fmean, rng)
    med_lo, med_hi = bootstrap_ci(xs, statistics.median, rng)
    q1, q3 = quantile(s, 0.25), quantile(s, 0.75)
    return {
        "count": len(xs), "mean": statistics.fmean(xs), "median": statistics.median(xs),
        "sd": statistics.stdev(xs) if len(xs) > 1 else float("nan"),
        "q1": q1, "q3": q3, "iqr": q3 - q1, "min": s[0], "max": s[-1],
        "mean_ci_low": mean_lo, "mean_ci_high": mean_hi,
        "median_ci_low": med_lo, "median_ci_high": med_hi,
    }


def wilson(k: int, n: int, z: float = Z95) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return centre - half, centre + half


# --------------------------------------------------------------------------
def graph_level(raw: list[dict[str, str]], datasets: list[dict[str, str]]) -> list[dict[str, Any]]:
    """One row per (graph, backend, algorithm): the unit of analysis."""
    ds = {d["graph_id"]: d for d in datasets}
    groups: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    for r in raw:
        groups[(r["graph_id"], r.get("spatial_backend", ""), r["algorithm"])].append(r)

    out = []
    for (gid, backend, algo), rows in sorted(groups.items()):
        timed = [r for r in rows if r["phase"] == PHASE_TIMED]
        if not timed:
            continue
        mem = [r for r in rows if r["phase"] == PHASE_MEMORY]
        cnt = [r for r in rows if r["phase"] == PHASE_COUNTERS]
        times = [t for t in (_f(r["t_algorithm_ms"]) for r in timed) if t is not None]
        sizes = {r["cds_size"] for r in timed if r["cds_size"] != ""}
        validated = [r for r in timed if r["validated"] == "true"]
        diam = [x for x in (_f(r.get("cds_diameter")) for r in timed) if x is not None]
        d = ds.get(gid, {})
        first = timed[0]
        out.append({
            "graph_id": gid, "spatial_backend": backend, "algorithm": algo, "cell_id": first["cell_id"],
            "geometry": first["geometry"], "n": int(first["n"]), "density_target": first["density_target"],
            "radius": first["radius"], "source_type": first["source_type"], "replicate": first["replicate"],
            "mean_degree": _f(d.get("mean_degree")), "max_degree": _f(d.get("max_degree")),
            "timed_repetitions": len(timed),
            "t_algorithm_ms": statistics.median(times) if times else None,
            "t_algorithm_ms_min": min(times) if times else None,
            "t_algorithm_ms_max": max(times) if times else None,
            "t_spatial_index_ms": _f(first.get("t_spatial_index_ms")),
            # Representation ablation: build cost of the adjacency representation
            # (CGAL index, or CGAL index + materialised CSR) plus T_algorithm.
            "t_index_plus_algorithm_ms": ((_f(first.get("t_spatial_index_ms")) or 0.0) + statistics.median(times))
            if times and _f(first.get("t_spatial_index_ms")) is not None else None,
            "index_bytes": _f(first.get("index_bytes")),
            "index_heap_peak_bytes": _f(mem[0].get("index_heap_peak_bytes")) if mem else None,
            "cds_size": _f(first["cds_size"]) if len(sizes) == 1 else None,
            "cds_size_consistent": len(sizes) == 1,
            "cds_fraction": _f(first["cds_fraction"]) if len(sizes) == 1 else None,
            "cds_diameter": diam[0] if diam else None,
            "core_count": _f(first["core_count"]), "connector_count": _f(first["connector_count"]),
            "neighbor_queries": _f(first["neighbor_queries"]),
            "neighbors_returned": _f(first.get("neighbors_returned")),
            "grid_candidates_examined": _f(first.get("grid_candidates_examined")),
            "grid_distance_computations": _f(first.get("grid_distance_computations")),
            "cgal_box_candidates": _f(first.get("cgal_box_candidates")),
            "cgal_exact_distance_evaluations": _f(first.get("cgal_exact_distance_evaluations")),
            "all_valid": bool(validated) and all(r["valid_solution"] == "true" for r in validated),
            "opt_size": _f(first["opt_size"]), "empirical_ratio": _f(first["empirical_ratio"]),
            "heap_peak_additional_bytes": _f(mem[0]["heap_peak_additional_bytes"]) if mem else None,
            "grid_cells_examined": _f(cnt[0].get("grid_cells_examined")) if cnt else None,
            "max_neighbors_per_query": _f(cnt[0].get("max_neighbors_per_query")) if cnt else None,
        })
    return out


def summarize(gl: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in gl:
        groups[(r["cell_id"], r["spatial_backend"], r["algorithm"])].append(r)
    out = []
    for (cell, backend, algo), rows in sorted(groups.items()):
        for metric in SUMMARY_METRICS:
            xs = [r[metric] for r in rows if r.get(metric) is not None]
            if not xs:
                continue
            out.append({"cell_id": cell, "spatial_backend": backend, "algorithm": algo, "metric": metric,
                        "geometry": rows[0]["geometry"], "n": rows[0]["n"],
                        "density_target": rows[0]["density_target"], "radius": rows[0]["radius"],
                        **describe(xs, (cell, backend, algo, metric))})
    return out


def validity(raw: list[dict[str, str]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    for r in raw:
        if r["validated"] == "true" or r["status"] == "algorithm_error":
            groups[(r["cell_id"], r.get("spatial_backend", ""), r["algorithm"])].append(r)
    out = []
    for (cell, backend, algo), rows in sorted(groups.items()):
        k = sum(1 for r in rows if r["valid_solution"] == "true")
        lo, hi = wilson(k, len(rows))
        reasons: dict[str, int] = defaultdict(int)
        for r in rows:
            if r["valid_solution"] != "true":
                reasons[r["failure_reason"] or r["status"]] += 1
        out.append({"cell_id": cell, "spatial_backend": backend, "algorithm": algo, "executions": len(rows),
                    "valid": k, "valid_rate": k / len(rows) if rows else float("nan"), "wilson_low": lo,
                    "wilson_high": hi,
                    "failure_reasons": ";".join(f"{a}={b}" for a, b in sorted(reasons.items()))})
    return out


def _paired_stats(pairs: list[tuple[float, float]], metric: str, seed_parts: tuple) -> dict[str, Any]:
    diffs = [a - b for a, b in pairs]
    rng = seeded_rng("paired", *seed_parts, metric)
    lo, hi = bootstrap_ci(diffs, statistics.fmean, rng)
    sd = statistics.stdev(diffs) if len(diffs) > 1 else float("nan")
    mean_d = statistics.fmean(diffs)
    row = {
        "metric": metric, "n_pairs": len(pairs), "diff_mean": mean_d, "diff_median": statistics.median(diffs),
        "diff_sd": sd, "diff_mean_ci_low": lo, "diff_mean_ci_high": hi,
        "cohens_dz": (mean_d / sd) if sd and sd > 0 else float("nan"),
        "a_lower": sum(1 for d in diffs if d < 0), "ties": sum(1 for d in diffs if d == 0),
        "b_lower": sum(1 for d in diffs if d > 0),
        "ratio_geomean": float("nan"), "ratio_ci_low": float("nan"), "ratio_ci_high": float("nan"),
        "ratio_median": float("nan"),
    }
    if metric == "t_algorithm_ms":
        logs = [math.log(a / b) for a, b in pairs if a > 0 and b > 0]
        if logs:
            rlo, rhi = bootstrap_ci(logs, statistics.fmean, rng)
            row.update({"ratio_geomean": math.exp(statistics.fmean(logs)), "ratio_ci_low": math.exp(rlo),
                        "ratio_ci_high": math.exp(rhi), "ratio_median": math.exp(statistics.median(logs))})
    return row


def paired(gl: list[dict[str, Any]], algorithms: Iterable[str]) -> list[dict[str, Any]]:
    """Algorithm vs algorithm on identical graphs, within one backend."""
    by: dict[tuple[str, str], dict[str, dict[str, dict[str, Any]]]] = defaultdict(lambda: defaultdict(dict))
    for r in gl:
        by[(r["cell_id"], r["spatial_backend"])][r["graph_id"]][r["algorithm"]] = r
    out = []
    for (cell, backend), graphs in sorted(by.items()):
        for a, b in combinations(list(algorithms), 2):
            for metric in PAIRED_METRICS:
                pairs = [(g[a][metric], g[b][metric]) for g in graphs.values()
                         if a in g and b in g and g[a].get(metric) is not None and g[b].get(metric) is not None]
                if pairs:
                    out.append({"cell_id": cell, "spatial_backend": backend, "algorithm_a": a, "algorithm_b": b,
                                **_paired_stats(pairs, metric, (cell, backend, a, b))})
    return out


def backend_paired(gl: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Backend vs backend for the same algorithm on identical graphs (sensitivity studies only)."""
    by: dict[tuple[str, str], dict[str, dict[str, dict[str, Any]]]] = defaultdict(lambda: defaultdict(dict))
    for r in gl:
        by[(r["cell_id"], r["algorithm"])][r["graph_id"]][r["spatial_backend"]] = r
    out = []
    for (cell, algo), graphs in sorted(by.items()):
        backends = sorted({b for g in graphs.values() for b in g})
        for a, b in combinations(backends, 2):
            for metric in ("t_algorithm_ms", "cds_size", "t_spatial_index_ms", "t_index_plus_algorithm_ms",
                           "index_heap_peak_bytes", "heap_peak_additional_bytes"):
                pairs = [(g[a][metric], g[b][metric]) for g in graphs.values()
                         if a in g and b in g and g[a].get(metric) is not None and g[b].get(metric) is not None]
                if pairs:
                    out.append({"cell_id": cell, "algorithm": algo, "backend_a": a, "backend_b": b,
                                **_paired_stats(pairs, metric, (cell, algo, a, b))})
    return out


def precision(gl: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Planning aid for the replicate count (pilot): current precision and the
    number of graphs a normal approximation projects for target precisions.
    Projections assume the pilot SD is representative; they are not a guarantee."""
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in gl:
        groups[(r["cell_id"], r["spatial_backend"], r["algorithm"])].append(r)
    out = []
    for (cell, backend, algo), rows in sorted(groups.items()):
        for metric in PRECISION_METRICS:
            xs = [r[metric] for r in rows if r.get(metric) is not None]
            if len(xs) < 2:
                continue
            mean = statistics.fmean(xs)
            sd = statistics.stdev(xs)
            half = Z95 * sd / math.sqrt(len(xs))
            row = {"cell_id": cell, "spatial_backend": backend, "algorithm": algo, "metric": metric,
                   "graphs": len(xs), "mean": mean, "sd": sd, "ci95_half_width": half,
                   "relative_half_width": (half / abs(mean)) if mean else float("nan")}
            for t in PRECISION_TARGETS:
                row[f"graphs_needed_rel_{t}"] = (math.ceil((Z95 * sd / (t * abs(mean))) ** 2)
                                                 if mean and sd > 0 else (2 if mean else float("nan")))
            out.append(row)
    return out


PRECISION_CURVE_K = (5, 10, 15, 20, 25, 30, 40, 50, 75, 100)


def precision_curve(gl: list[dict[str, Any]], algorithms: Iterable[str]) -> list[dict[str, Any]]:
    """Replicate-count justification (precision pilot).

    For each paired difference (A - B on identical graphs, within one backend)
    and each k, the mean difference and 95% CI half-width using only the first
    k replicates (graphs ordered by replicate number, i.e. the order a study
    with k replicates would have collected them). Reported both as a normal
    approximation (1.96 sd / sqrt(k)) and as a percentile bootstrap.
    """
    by: dict[tuple[str, str], dict[str, dict[str, dict[str, Any]]]] = defaultdict(lambda: defaultdict(dict))
    for r in gl:
        by[(r["cell_id"], r["spatial_backend"])][r["graph_id"]][r["algorithm"]] = r
    out = []
    for (cell, backend), graphs in sorted(by.items()):
        for a, b in combinations(list(algorithms), 2):
            for metric in ("cds_size", "t_algorithm_ms"):
                pts = sorted(
                    (int(float(g[a]["replicate"])), g[a][metric] - g[b][metric])
                    for g in graphs.values()
                    if a in g and b in g and g[a].get(metric) is not None and g[b].get(metric) is not None)
                diffs = [d for _, d in pts]
                for k in PRECISION_CURVE_K:
                    if k > len(diffs):
                        break
                    xs = diffs[:k]
                    sd = statistics.stdev(xs)
                    rng = seeded_rng("precision-curve", cell, backend, a, b, metric, k)
                    lo, hi = bootstrap_ci(xs, statistics.fmean, rng, b=1000)
                    out.append({"cell_id": cell, "spatial_backend": backend, "algorithm_a": a, "algorithm_b": b,
                                "metric": metric, "k_graphs": k, "available_graphs": len(diffs),
                                "diff_mean": statistics.fmean(xs), "diff_sd": sd,
                                "ci95_half_width_normal": Z95 * sd / math.sqrt(k),
                                "ci95_half_width_bootstrap": (hi - lo) / 2.0})
    return out


NOTES = """# Analysis notes (generated)

* Unit of analysis: one graph instance. Runtime per (graph, backend,
  algorithm) = median of that graph's timed repetitions (warmups, memory
  probes and counter passes are excluded from runtime). All repetitions remain
  in `raw_runs.csv`.
* Every table is grouped by `spatial_backend`. The primary algorithm
  comparison uses one backend (cgal). Backend-vs-backend comparisons appear
  only in `backend_paired.csv` (sensitivity / ablation studies).
* CDS size, CDS diameter and query counts are deterministic per (graph,
  algorithm); `cds_size_consistent` in `graph_level.csv` verifies this.
* Confidence intervals: 95% percentile bootstrap, {b} resamples, seeded from
  the grouping keys so numbers are reproducible. Approximate for few graphs;
  read them together with `count` / `n_pairs`.
* Validity: Wilson 95% interval on validated executions.
* `paired.csv`: algorithm A vs B on identical graphs (graphs where either
  algorithm has no value are excluded and listed by the fairness report).
  Difference = A - B; "lower is better" for every paired metric
  (`a_lower` / `ties` / `b_lower`). Runtime also as ratio A / B (geometric mean
  of per-graph ratios, bootstrap CI); < 1 means A faster.
* `precision.csv` (pilot planning aid): current 95% CI half-width and the
  number of graphs a normal approximation projects for relative half-widths
  of 1%, 2%, 5%. Assumes the pilot SD carries over.
* `precision_curve.csv` (replicate-count justification): for each paired
  difference, the mean and 95% CI half-width using the first k replicates,
  k = 5, 10, 15, ... up to the number collected.
* `empirical_ratio` = CDS size / OPT on exact-solved graphs only: an EMPIRICAL
  APPROXIMATION RATIO for these instances, never a theoretical ratio.
* Backend-specific diagnostics carry their backend in the name (`grid_*`,
  `cgal_*`) and are empty for every other backend; they are never compared
  across backends. `index_bytes` is likewise backend-specific.
* No hypothesis tests or multiplicity corrections are applied. Cells are not
  pooled.
"""


def write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    cols = list(rows[0].keys())
    for r in rows[1:]:
        for k in r:
            if k not in cols:
                cols.append(k)
    with path.open("w", encoding="utf-8", newline="") as handle:
        w = csv.DictWriter(handle, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in cols})


def analyze(study_dir: Path, algorithms: list[str]) -> dict[str, Any]:
    raw = read_csv(study_dir / "raw_runs.csv")
    datasets = read_csv(study_dir / "datasets.csv")
    gl = graph_level(raw, datasets)
    tables = {
        "graph_level": gl,
        "summary": summarize(gl),
        "validity": validity(raw),
        "paired": paired(gl, algorithms),
        "backend_paired": backend_paired(gl),
        "precision": precision(gl),
        "precision_curve": precision_curve(gl, algorithms),
    }
    for name, rows in tables.items():
        write_rows(study_dir / f"{name}.csv", rows)
    (study_dir / "analysis_notes.md").write_text(NOTES.format(b=BOOTSTRAP_B), encoding="utf-8")
    return {name: len(rows) for name, rows in tables.items()}
