"""Safe explicit-vs-implicit UDG baseline (small/medium n only).

TEST / ANALYSIS ONLY. Never used by production algorithms.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

_PYTHON_DIR = Path(__file__).resolve().parent
if str(_PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(_PYTHON_DIR))

from generators import generate, write_csv  # noqa: E402
from gui_support import find_mcds_executable, find_repo_root  # noqa: E402


def _estimate_explicit_bytes(n: int, edge_count: int) -> int:
    # Rough CSR-like: 2 * edges * 4-byte indices + n * 8-byte offsets + points 16n
    return int(2 * edge_count * 4 + n * 8 + n * 16)


def build_explicit_udg(points: list[tuple[float, float]], radius: float) -> tuple[int, float, int]:
    """Return (edge_count, construction_ms, estimated_bytes). O(n^2) — call only for small n."""
    n = len(points)
    r2 = radius * radius
    t0 = time.perf_counter()
    edges = 0
    for i in range(n):
        xi, yi = points[i]
        for j in range(i + 1, n):
            dx = xi - points[j][0]
            dy = yi - points[j][1]
            if dx * dx + dy * dy <= r2:
                edges += 1
    ms = (time.perf_counter() - t0) * 1000.0
    return edges, ms, _estimate_explicit_bytes(n, edges)


def measure_implicit(executable: Path, csv_path: Path, out_json: Path, radius: float) -> dict:
    import subprocess

    completed = subprocess.run(
        [
            str(executable),
            "--input",
            str(csv_path),
            "--check-connectivity",
            "--radius",
            str(radius),
            "--output",
            str(out_json),
            "--pretty",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0 or not out_json.is_file():
        return {"status": "solver_error", "error": completed.stderr or completed.stdout}
    data = json.loads(out_json.read_text(encoding="utf-8"))
    return {
        "status": "ok",
        "index_build_ms": data.get("index_build_ms"),
        "connectivity_ms": data.get("connectivity_ms"),
        "peak_memory_mb": None,  # connectivity path may omit; filled by runner when available
        "n": data.get("n"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Explicit vs implicit UDG baseline.")
    parser.add_argument("--sizes", default="100,300,1000,3000")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--density", type=float, default=5.0)
    parser.add_argument("--radius", type=float, default=1.0)
    parser.add_argument("--max-n", type=int, default=10000)
    parser.add_argument("--max-memory-mb", type=float, default=1024.0)
    parser.add_argument("--out", default="results/explicit_vs_implicit.csv")
    args = parser.parse_args(argv)

    repo = find_repo_root()
    exe = find_mcds_executable(repo)
    sizes = [int(x) for x in args.sizes.split(",") if x.strip()]
    out_csv = repo / args.out
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    work = repo / "datasets" / "explicit_baseline"
    work.mkdir(parents=True, exist_ok=True)

    fields = [
        "n",
        "seed",
        "density",
        "radius",
        "status",
        "edge_count",
        "explicit_build_ms",
        "explicit_est_memory_mb",
        "implicit_index_build_ms",
        "implicit_connectivity_ms",
        "error",
    ]
    rows: list[dict] = []

    for n in sizes:
        row = {
            "n": n,
            "seed": args.seed,
            "density": args.density,
            "radius": args.radius,
            "status": "ok",
            "edge_count": "",
            "explicit_build_ms": "",
            "explicit_est_memory_mb": "",
            "implicit_index_build_ms": "",
            "implicit_connectivity_ms": "",
            "error": "",
        }
        if n > args.max_n:
            row["status"] = "safety_skip"
            row["error"] = f"n>{args.max_n}"
            rows.append(row)
            continue

        # Rough safety: complete graph memory estimate
        worst_edges = n * (n - 1) // 2
        worst_mb = _estimate_explicit_bytes(n, worst_edges) / (1024.0 * 1024.0)
        if worst_mb > args.max_memory_mb:
            row["status"] = "safety_skip"
            row["error"] = f"estimated explicit memory {worst_mb:.1f}MB > {args.max_memory_mb}"
            rows.append(row)
            continue

        gen = generate("uniform", n, args.seed, density=args.density)
        csv_path = work / f"uniform_n{n}_seed{args.seed}.csv"
        write_csv(str(csv_path), gen.points)
        coords = [(float(p[0]), float(p[1])) for p in gen.points]

        edges, build_ms, est_bytes = build_explicit_udg(coords, args.radius)
        est_mb = est_bytes / (1024.0 * 1024.0)
        row["edge_count"] = edges
        row["explicit_build_ms"] = f"{build_ms:.4f}"
        row["explicit_est_memory_mb"] = f"{est_mb:.4f}"

        if est_mb > args.max_memory_mb:
            row["status"] = "safety_skip"
            row["error"] = "post-build memory estimate exceeded"
            rows.append(row)
            continue

        impl = measure_implicit(exe, csv_path, work / f"_impl_n{n}.json", args.radius)
        if impl.get("status") != "ok":
            row["status"] = "solver_error"
            row["error"] = impl.get("error", "")
        else:
            row["implicit_index_build_ms"] = impl.get("index_build_ms", "")
            row["implicit_connectivity_ms"] = impl.get("connectivity_ms", "")
        rows.append(row)
        print(
            f"n={n} edges={edges} explicit_ms={build_ms:.2f} "
            f"explicit_mb~={est_mb:.3f} implicit_index_ms={row['implicit_index_build_ms']}"
        )

    with out_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {out_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
