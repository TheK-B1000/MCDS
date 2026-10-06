"""Generator calibration: connectivity acceptance, clustering and degree per cell.

Preregistered evidence for the generator parameters and for which cells a
study may contain. For every (geometry, n, density) cell it draws graphs on
INDEPENDENT validation seeds (SHA-256 namespace "calibration", disjoint from
every study's graph seeds), probes each with the solver's implicit graph-only
mode (no graph is ever stored), and records:

* connectivity acceptance rate (+ Wilson 95% CI),
* clustering share distribution (fraction of points in the densest 10% of the
  r-sized grid cells covering the bounding box; higher = more clustered),
* observed degree statistics (mean / median / min / max / SD per graph),
* median nearest-neighbour distance (grid search over the points; nothing stored
  but O(n) buckets),

and compares each geometry's clustering share with uniform at the same
(n, density).

    py -3 python/connectivity_calibration.py --from-config experiments/final.json \\
        --densities 5,8,12 --seeds 24 --output experiments/calibration/generator_calibration_v1.json
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_PYTHON_DIR = Path(__file__).resolve().parent
if str(_PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(_PYTHON_DIR))

from generators import generate, write_csv  # noqa: E402
from study import config as config_mod  # noqa: E402
from study.analysis import quantile, wilson  # noqa: E402
from study.bench import find_binary, run_bench  # noqa: E402
from study.seeds import derive_seed  # noqa: E402

CLUSTER_TOP_FRACTION = 0.10


def clustering_share(points: list[tuple[float, float]], cell: float) -> float:
    """Share of points in the densest 10% of the cell-size grid over the bbox."""
    counts: dict[tuple[int, int], int] = {}
    for x, y in points:
        key = (math.floor(x / cell), math.floor(y / cell))
        counts[key] = counts.get(key, 0) + 1
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    nx = math.floor(max(xs) / cell) - math.floor(min(xs) / cell) + 1
    ny = math.floor(max(ys) / cell) - math.floor(min(ys) / cell) + 1
    top = max(1, int(CLUSTER_TOP_FRACTION * nx * ny))
    return sum(sorted(counts.values(), reverse=True)[:top]) / len(points)


def median_nearest_neighbour_distance(points: list[tuple[float, float]], cell: float) -> float:
    """Median over points of the distance to the nearest other point (grid search)."""
    buckets: dict[tuple[int, int], list[int]] = {}
    for i, (x, y) in enumerate(points):
        buckets.setdefault((math.floor(x / cell), math.floor(y / cell)), []).append(i)
    dists = []
    for i, (x, y) in enumerate(points):
        gx, gy = math.floor(x / cell), math.floor(y / cell)
        best = math.inf
        ring = 1
        while True:
            for dx in range(-ring, ring + 1):
                for dy in range(-ring, ring + 1):
                    for j in buckets.get((gx + dx, gy + dy), ()):
                        if j != i:
                            d2 = (points[j][0] - x) ** 2 + (points[j][1] - y) ** 2
                            if d2 < best:
                                best = d2
            # Any point outside the scanned rings is farther than ring * cell.
            if best <= (ring * cell) ** 2 or ring > 64:
                break
            ring += 1
        dists.append(math.sqrt(best))
    return statistics.median(dists)


def _summary(xs: list[float]) -> dict[str, float]:
    s = sorted(xs)
    return {"median": statistics.median(s), "q1": quantile(s, 0.25), "q3": quantile(s, 0.75),
            "min": s[0], "max": s[-1], "mean": statistics.fmean(s)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from-config", required=True, help="study config providing geometries, sizes, radius, parameters")
    ap.add_argument("--densities", default=None, help="override densities (comma list)")
    ap.add_argument("--sizes", default=None, help="override sizes (comma list)")
    ap.add_argument("--seeds", type=int, default=24, help="validation graphs per cell")
    ap.add_argument("--calibration-seed", type=int, default=20261006)
    ap.add_argument("--spatial-backend", default="cgal", choices=["cgal", "grid"])
    ap.add_argument("--output", required=True)
    args = ap.parse_args(argv)

    cfg = config_mod.load(Path(args.from_config))
    syn = cfg["synthetic"]
    densities = [float(x) for x in args.densities.split(",")] if args.densities else [float(d) for d in syn["densities"]]
    sizes = [int(x) for x in args.sizes.split(",")] if args.sizes else [int(n) for n in syn["sizes"]]
    radius = float(syn["radius"])
    geometries = list(syn["geometries"])
    exe = find_binary(_REPO_ROOT, "mcds_bench")

    per_graph: list[dict] = []
    cells: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="mcds_calib_") as tmp:
        csv_path = Path(tmp) / "g.csv"
        for geometry in geometries:
            params = dict(syn["geometry_parameters"].get(geometry, {}))
            for n in sizes:
                for density in densities:
                    rows = []
                    for k in range(args.seeds):
                        seed = derive_seed("calibration", args.calibration_seed, geometry, n, density, radius, k)
                        pts = generate(geometry, n, seed, density=density, **params).points
                        write_csv(str(csv_path), pts)
                        probe = run_bench(exe, csv_path, radius, spatial_backend=args.spatial_backend,
                                          graph_only=True, timeout_s=3600)
                        if not probe.ok or probe.data is None:
                            raise RuntimeError(f"probe failed: {geometry} n={n} d={density} k={k}: {probe.error}")
                        g = probe.data["graph"]
                        row = {"geometry": geometry, "n": n, "density": density, "replicate": k, "seed": seed,
                               "connected": bool(g["connected"]), "components": g["component_count"],
                               "mean_degree": g["mean_degree"], "median_degree": g["median_degree"],
                               "min_degree": g["min_degree"], "max_degree": g["max_degree"],
                               "degree_std": g["degree_std"],
                               "clustering_share": clustering_share(pts, radius),
                               "median_nn_distance": median_nearest_neighbour_distance(pts, radius / 4.0),
                               "backend_crosscheck": probe.data["backend_crosscheck"]["status"]}
                        rows.append(row)
                        per_graph.append(row)
                    ok = sum(r["connected"] for r in rows)
                    lo, hi = wilson(ok, len(rows))
                    cell = {"geometry": geometry, "n": n, "density": density, "radius": radius,
                            "graphs": len(rows), "connected": ok, "acceptance_rate": ok / len(rows),
                            "acceptance_wilson_low": lo, "acceptance_wilson_high": hi,
                            "clustering_share": _summary([r["clustering_share"] for r in rows]),
                            "mean_degree": _summary([r["mean_degree"] for r in rows]),
                            "median_degree": _summary([r["median_degree"] for r in rows]),
                            "min_degree": _summary([r["min_degree"] for r in rows]),
                            "max_degree": _summary([r["max_degree"] for r in rows]),
                            "degree_std": _summary([r["degree_std"] for r in rows]),
                            "median_nn_distance": _summary([r["median_nn_distance"] for r in rows])}
                    cells.append(cell)
                    print(f"{geometry:15} n={n:<6} d={density:<5} connected {ok:2d}/{len(rows)} "
                          f"clustering median {cell['clustering_share']['median']:.3f} "
                          f"mean degree {cell['mean_degree']['median']:.1f} "
                          f"NN dist {cell['median_nn_distance']['median']:.3f}", flush=True)

    uniform = {(c["n"], c["density"]): c["clustering_share"]["median"] for c in cells if c["geometry"] == "uniform"}
    for c in cells:
        ref = uniform.get((c["n"], c["density"]))
        c["clustering_vs_uniform_ratio"] = (c["clustering_share"]["median"] / ref) if ref else None

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    doc = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source_config": args.from_config,
        "source_config_sha256": config_mod.config_sha256(cfg),
        "generator_sha256": hashlib.sha256((_PYTHON_DIR / "generators.py").read_bytes()).hexdigest(),
        "calibration_seed": args.calibration_seed,
        "seed_namespace": "sha256('calibration', calibration_seed, geometry, n, density, radius, k); "
                          "disjoint from study seeds",
        "spatial_backend": args.spatial_backend,
        "clustering_share_definition": "fraction of points in the densest 10% of r-sized grid cells over the bounding box",
        "cells": cells,
    }
    out.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    with out.with_suffix(".graphs.csv").open("w", encoding="utf-8", newline="") as h:
        w = csv.DictWriter(h, fieldnames=list(per_graph[0].keys()))
        w.writeheader()
        w.writerows(per_graph)
    print(f"wrote {out} ({len(cells)} cells, {len(per_graph)} graphs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
