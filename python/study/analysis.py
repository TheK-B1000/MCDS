"""Statistical summaries for MCDS studies (standard library only).

Unit of analysis = one graph. Timed repetitions on a graph are *technical*
replicates of one measurement, so they are summarised by their median per
(graph, algorithm) before any between-graph statistic is computed. Treating
repetitions as independent observations would understate uncertainty
(pseudo-replication).

Methods (documented in analysis_notes.md, written next to the outputs):
  * descriptive: count, mean, median, SD, Q1, Q3, IQR, min, max
  * 95% percentile-bootstrap CIs for mean and median (seeded, B resamples)
  * validity: proportion of executions returning a valid CDS + Wilson 95% CI
  * paired comparisons (same graphs, per cell): CDS-size difference A - B
    (mean, median, bootstrap CI of the mean, Cohen's d_z, wins/ties/losses);
    runtime ratio A / B as a geometric mean with bootstrap CI (runtime is
    right-skewed and multiplicative, so ratios are summarised on the log scale)
  * no null-hypothesis significance tests are run by default
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
    "t_algorithm_ms", "cds_size", "cds_fraction", "core_count", "connector_count",
    "neighbor_queries", "candidates_examined", "distance_computations",
    "heap_peak_additional_bytes", "empirical_ratio",
)


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


def wilson(k: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return centre - half, centre + half


# --------------------------------------------------------------------------
def graph_level(raw: list[dict[str, str]], datasets: list[dict[str, str]]) -> list[dict[str, Any]]:
    """One row per (graph, algorithm): the unit of analysis."""
    ds = {d["graph_id"]: d for d in datasets}
    groups: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for r in raw:
        groups[(r["graph_id"], r["algorithm"])].append(r)

    out = []
    for (gid, algo), rows in sorted(groups.items()):
        timed = [r for r in rows if r["phase"] == PHASE_TIMED]
        if not timed:
            continue
        mem = [r for r in rows if r["phase"] == PHASE_MEMORY]
        cnt = [r for r in rows if r["phase"] == PHASE_COUNTERS]
        times = [_f(r["t_algorithm_ms"]) for r in timed]
        times = [t for t in times if t is not None]
        sizes = {r["cds_size"] for r in timed if r["cds_size"] != ""}
        validated = [r for r in timed if r["validated"] == "true"]
        d = ds.get(gid, {})
        first = timed[0]
        row = {
            "graph_id": gid, "algorithm": algo, "cell_id": first["cell_id"], "geometry": first["geometry"],
            "n": int(first["n"]), "density_target": first["density_target"], "radius": first["radius"],
            "source_type": first["source_type"], "replicate": first["replicate"],
            "mean_degree": _f(d.get("mean_degree")), "max_degree": _f(d.get("max_degree")),
            "timed_repetitions": len(timed),
            "t_algorithm_ms": statistics.median(times) if times else None,
            "t_algorithm_ms_min": min(times) if times else None,
            "t_algorithm_ms_max": max(times) if times else None,
            "cds_size": _f(first["cds_size"]) if len(sizes) == 1 else None,
            "cds_size_consistent": len(sizes) == 1,
            "cds_fraction": _f(first["cds_fraction"]) if len(sizes) == 1 else None,
            "core_count": _f(first["core_count"]), "connector_count": _f(first["connector_count"]),
            "neighbor_queries": _f(first["neighbor_queries"]),
            "candidates_examined": _f(first["candidates_examined"]),
            "distance_computations": _f(first["distance_computations"]),
            "all_valid": bool(validated) and all(r["valid_solution"] == "true" for r in validated),
            "opt_size": _f(first["opt_size"]), "empirical_ratio": _f(first["empirical_ratio"]),
            "heap_peak_additional_bytes": _f(mem[0]["heap_peak_additional_bytes"]) if mem else None,
            "cells_examined": _f(cnt[0]["cells_examined"]) if cnt else None,
            "max_candidates_per_query": _f(cnt[0]["max_candidates_per_query"]) if cnt else None,
            "max_neighbors_per_query": _f(cnt[0]["max_neighbors_per_query"]) if cnt else None,
        }
        out.append(row)
    return out


def summarize(gl: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in gl:
        groups[(r["cell_id"], r["algorithm"])].append(r)
    out = []
    for (cell, algo), rows in sorted(groups.items()):
        for metric in SUMMARY_METRICS:
            xs = [r[metric] for r in rows if r.get(metric) is not None]
            if not xs:
                continue
            out.append({"cell_id": cell, "algorithm": algo, "metric": metric,
                        "geometry": rows[0]["geometry"], "n": rows[0]["n"],
                        "density_target": rows[0]["density_target"], "radius": rows[0]["radius"],
                        **describe(xs, (cell, algo, metric))})
    return out


def validity(raw: list[dict[str, str]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for r in raw:
        if r["validated"] == "true" or r["status"] == "algorithm_error":
            groups[(r["cell_id"], r["algorithm"])].append(r)
    out = []
    for (cell, algo), rows in sorted(groups.items()):
        k = sum(1 for r in rows if r["valid_solution"] == "true")
        lo, hi = wilson(k, len(rows))
        reasons = defaultdict(int)
        for r in rows:
            if r["valid_solution"] != "true":
                reasons[r["failure_reason"] or r["status"]] += 1
        out.append({"cell_id": cell, "algorithm": algo, "executions": len(rows), "valid": k,
                    "valid_rate": k / len(rows) if rows else float("nan"), "wilson_low": lo, "wilson_high": hi,
                    "failure_reasons": ";".join(f"{a}={b}" for a, b in sorted(reasons.items()))})
    return out


def paired(gl: list[dict[str, Any]], algorithms: Iterable[str]) -> list[dict[str, Any]]:
    by_cell: dict[str, dict[str, dict[str, dict[str, Any]]]] = defaultdict(lambda: defaultdict(dict))
    for r in gl:
        by_cell[r["cell_id"]][r["graph_id"]][r["algorithm"]] = r
    out = []
    for cell, graphs in sorted(by_cell.items()):
        for a, b in combinations(list(algorithms), 2):
            pairs = [(g[a], g[b]) for g in graphs.values() if a in g and b in g
                     and g[a]["cds_size"] is not None and g[b]["cds_size"] is not None]
            if not pairs:
                continue
            diffs = [x["cds_size"] - y["cds_size"] for x, y in pairs]
            rng = seeded_rng("paired", cell, a, b)
            lo, hi = bootstrap_ci(diffs, statistics.fmean, rng)
            sd = statistics.stdev(diffs) if len(diffs) > 1 else float("nan")
            mean_d = statistics.fmean(diffs)
            logs = [math.log(x["t_algorithm_ms"] / y["t_algorithm_ms"]) for x, y in pairs
                    if x["t_algorithm_ms"] and y["t_algorithm_ms"]]
            if logs:
                rlo, rhi = bootstrap_ci(logs, statistics.fmean, rng)
                gm, gm_lo, gm_hi = math.exp(statistics.fmean(logs)), math.exp(rlo), math.exp(rhi)
                med_ratio = math.exp(statistics.median(logs))
            else:
                gm = gm_lo = gm_hi = med_ratio = float("nan")
            out.append({
                "cell_id": cell, "algorithm_a": a, "algorithm_b": b, "n_pairs": len(pairs),
                "cds_diff_mean": mean_d, "cds_diff_median": statistics.median(diffs), "cds_diff_sd": sd,
                "cds_diff_mean_ci_low": lo, "cds_diff_mean_ci_high": hi,
                "cohens_dz": (mean_d / sd) if sd and sd > 0 else float("nan"),
                "a_smaller": sum(1 for d in diffs if d < 0), "ties": sum(1 for d in diffs if d == 0),
                "b_smaller": sum(1 for d in diffs if d > 0),
                "runtime_ratio_geomean": gm, "runtime_ratio_ci_low": gm_lo, "runtime_ratio_ci_high": gm_hi,
                "runtime_ratio_median": med_ratio,
            })
    return out


NOTES = """# Analysis notes (generated)

* Unit of analysis: one graph. Runtime per (graph, algorithm) = median of that
  graph's timed repetitions (warmups, memory probes and counter passes are
  excluded from runtime). All repetitions remain in `raw_runs.csv`.
* CDS size and work counters are deterministic per (graph, algorithm); the
  `cds_size_consistent` column in `graph_level.csv` verifies this.
* Confidence intervals: 95% percentile bootstrap, {b} resamples, seeded from
  (cell, algorithm, metric) so the numbers are reproducible. Bootstrap CIs are
  approximate for small numbers of graphs; read them together with `count`.
* Validity: Wilson 95% interval on the proportion of validated executions that
  returned a valid CDS.
* Paired comparisons use only graphs on which both algorithms completed. CDS
  difference is A - B (negative = A smaller). Runtime ratio is A / B,
  summarised by the geometric mean of per-graph ratios (log-scale mean) and its
  bootstrap CI; ratios < 1 mean A was faster.
* Cohen's d_z = mean(diff) / sd(diff); undefined when every pair is tied.
* `empirical_ratio` = CDS size / OPT on graphs where exact OPT was computed. It
  is an EMPIRICAL APPROXIMATION RATIO for these instances only and is not the
  theoretical approximation ratio of any paper.
* No hypothesis tests or multiplicity corrections are applied. Cells are not
  pooled: pooling across n / density / geometry would mix different populations.
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
    summary = summarize(gl)
    valid = validity(raw)
    pairs = paired(gl, algorithms)
    write_rows(study_dir / "graph_level.csv", gl)
    write_rows(study_dir / "summary.csv", summary)
    write_rows(study_dir / "validity.csv", valid)
    write_rows(study_dir / "paired.csv", pairs)
    (study_dir / "analysis_notes.md").write_text(NOTES.format(b=BOOTSTRAP_B), encoding="utf-8")
    return {"graph_level": len(gl), "summary": len(summary), "validity": len(valid), "paired": len(pairs)}
