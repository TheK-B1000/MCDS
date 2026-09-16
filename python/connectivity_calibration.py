"""Connectivity-only calibration for choosing study densities.

Measures how often each generator produces a connected UDG at a given
density — one fresh sample per seed, no connectivity retries. Use this to
pick a common low-density level that keeps the primary study matrix complete.

Example:

    py -3 python/connectivity_calibration.py \\
        --distributions clustered,corridor \\
        --n 2000 --densities 3,3.5,4,4.5,5 --seeds 20
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_PYTHON_DIR = Path(__file__).resolve().parent
for path in (_REPO_ROOT, _PYTHON_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from experiment_runner import check_connected  # noqa: E402
from generators import generate, write_csv  # noqa: E402
from gui_support import find_mcds_executable, find_repo_root  # noqa: E402

DEFAULT_PARAMS = {
    "clustered": {"clusters": 4, "spread": 0.8},
    "corridor": {"corridor_width": 3.0},
    "cluster_bridge": {"clusters": 3, "spread": 0.45, "bridge_fraction": 0.2, "bridge_width": 0.6},
    "perturbed_grid": {"jitter": 0.15},
    "uniform": {},
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--distributions", default="clustered,corridor")
    parser.add_argument("--n", type=int, default=2000)
    parser.add_argument("--densities", default="3,3.5,4,4.5,5")
    parser.add_argument("--seeds", type=int, default=20, help="Number of independent seeds (1..N)")
    parser.add_argument("--radius", type=float, default=1.0)
    parser.add_argument(
        "--out-dir",
        default="results/studies/connectivity_calibration",
        help="Directory for CSV + summary JSON",
    )
    args = parser.parse_args()

    distributions = [x.strip() for x in args.distributions.split(",") if x.strip()]
    densities = [float(x) for x in args.densities.split(",") if x.strip()]
    seeds = list(range(1, int(args.seeds) + 1))
    n = int(args.n)

    repo = find_repo_root()
    exe = find_mcds_executable(repo)
    out_dir = (repo / args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "connectivity_rates.csv"
    json_path = out_dir / "connectivity_rates.json"

    rows: list[dict[str, object]] = []
    counts: dict[tuple[str, float], list[bool]] = defaultdict(list)

    with tempfile.TemporaryDirectory(prefix="mcds_conn_cal_") as tmp:
        tmp_dir = Path(tmp)
        conn_json = tmp_dir / "conn.json"
        total = len(distributions) * len(densities) * len(seeds)
        done = 0
        for dist in distributions:
            extra = dict(DEFAULT_PARAMS.get(dist, {}))
            for density in densities:
                for seed in seeds:
                    done += 1
                    gen = generate(dist, n, seed, density=density, **extra)
                    points_path = tmp_dir / f"{dist}_d{density}_s{seed}.csv"
                    write_csv(str(points_path), gen.points)
                    connected, result, error = check_connected(exe, points_path, conn_json, args.radius)
                    comps = None if result is None else result.get("component_count")
                    row = {
                        "distribution": dist,
                        "n": n,
                        "density": density,
                        "seed": seed,
                        "connected": connected,
                        "component_count": comps,
                        "error": error or "",
                    }
                    rows.append(row)
                    counts[(dist, density)].append(bool(connected))
                    flag = "Y" if connected else "N"
                    print(
                        f"[{done}/{total}] {dist:15} dens={density:<4} seed={seed:2} "
                        f"connected={flag} comps={comps}",
                        flush=True,
                    )

    fieldnames = ["distribution", "n", "density", "seed", "connected", "component_count", "error"]
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    summary: dict[str, dict[str, dict[str, float | int]]] = {}
    print("\nConnectivity rate (connected / seeds):\n")
    header = f"{'distribution':16}" + "".join(f"{d:>8}" for d in densities)
    print(header)
    print("-" * len(header))
    for dist in distributions:
        summary[dist] = {}
        line = f"{dist:16}"
        for density in densities:
            samples = counts[(dist, density)]
            rate = sum(samples) / len(samples) if samples else 0.0
            summary[dist][str(density)] = {
                "connected": sum(samples),
                "trials": len(samples),
                "rate": round(rate, 4),
            }
            line += f"{100.0 * rate:7.1f}%"
        print(line)

    payload = {
        "n": n,
        "seeds": seeds,
        "densities": densities,
        "distributions": distributions,
        "radius": args.radius,
        "note": "One generation per seed; no connectivity retries.",
        "rates": summary,
        "csv": str(csv_path),
    }
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"\nwrote {csv_path}")
    print(f"wrote {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
