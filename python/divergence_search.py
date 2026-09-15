"""Search for datasets where Marathe / Wan / Funke CDS sizes diverge.

Diagnostic only — not a benchmark. Does not tune generation to favor Funke.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path

_PYTHON_DIR = Path(__file__).resolve().parent
if str(_PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(_PYTHON_DIR))

from generators import generate, write_csv  # noqa: E402
from gui_support import build_solver_command, find_mcds_executable, find_repo_root, run_solver  # noqa: E402


ALGORITHMS = ("marathe", "wan", "funke")


def _gen_kwargs(dist: str, density: float) -> dict:
    kwargs: dict = {"density": density}
    if dist == "corridor":
        kwargs["corridor_width"] = 2.5
    if dist == "perturbed_grid":
        kwargs["jitter"] = 0.15
    if dist == "clustered":
        kwargs["clusters"] = 4
        kwargs["spread"] = 0.7
    if dist == "cluster_bridge":
        kwargs["clusters"] = 3
        kwargs["spread"] = 0.5
        kwargs["bridge_fraction"] = 0.25
        kwargs["bridge_width"] = 0.6
    return kwargs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Find CDS-size divergence among heuristics.")
    parser.add_argument("--max-cases", type=int, default=8)
    parser.add_argument("--max-trials", type=int, default=200)
    parser.add_argument("--sizes", default="20,30,40,50")
    parser.add_argument("--densities", default="3.0,4.0,5.0,6.0")
    parser.add_argument(
        "--distributions",
        default="uniform,clustered,perturbed_grid,corridor,cluster_bridge",
    )
    parser.add_argument("--out-dir", default="results/divergence_cases")
    args = parser.parse_args(argv)

    repo = find_repo_root()
    exe = find_mcds_executable(repo)
    out_root = repo / args.out_dir
    out_root.mkdir(parents=True, exist_ok=True)

    sizes = [int(x) for x in args.sizes.split(",") if x.strip()]
    densities = [float(x) for x in args.densities.split(",") if x.strip()]
    distributions = [x.strip() for x in args.distributions.split(",") if x.strip()]

    index_rows: list[dict] = []
    searched = 0
    divergent = 0
    seed = 1

    while searched < args.max_trials and divergent < args.max_cases:
        for dist in distributions:
            for n in sizes:
                for density in densities:
                    if searched >= args.max_trials or divergent >= args.max_cases:
                        break
                    searched += 1
                    seed += 1
                    case_id = f"{dist}_n{n}_d{density}_seed{seed}"
                    work = out_root / case_id
                    work.mkdir(parents=True, exist_ok=True)
                    csv_path = work / "points.csv"
                    meta = {
                        "distribution": dist,
                        "n": n,
                        "seed": seed,
                        "density": density,
                        "radius": 1.0,
                        **_gen_kwargs(dist, density),
                    }
                    result = generate(dist, n, seed, **_gen_kwargs(dist, density))
                    write_csv(str(csv_path), result.points)
                    (work / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

                    conn = run_solver(
                        build_solver_command(
                            exe, csv_path, work / "conn.json", check_connectivity_only=True
                        )
                    )
                    if not conn.result or not conn.result.get("connected_input"):
                        continue

                    sizes_found: dict[str, int] = {}
                    ok = True
                    for algo in ALGORITHMS:
                        outcome = run_solver(
                            build_solver_command(
                                exe, csv_path, work / f"{algo}.json", algorithm=algo
                            )
                        )
                        if outcome.exit_code != 0 or not outcome.result:
                            ok = False
                            break
                        sizes_found[algo] = int(outcome.result["cds_size"])
                    if not ok:
                        continue

                    unique_sizes = set(sizes_found.values())
                    if len(unique_sizes) == 1:
                        continue

                    divergent += 1
                    opt_size = ""
                    if n <= 16:
                        opt_json = work / "opt.json"
                        completed = subprocess.run(
                            [
                                str(exe),
                                "--input",
                                str(csv_path),
                                "--exact-small",
                                "--output",
                                str(opt_json),
                            ],
                            capture_output=True,
                            text=True,
                            check=False,
                        )
                        if completed.returncode == 0 and opt_json.is_file():
                            opt_size = json.loads(opt_json.read_text(encoding="utf-8"))["cds_size"]

                    try:
                        from visualization import render

                        for algo in ALGORITHMS:
                            render(
                                csv_path,
                                work / f"{algo}.json",
                                save=work / f"{algo}.png",
                                show=False,
                            )
                    except Exception:
                        pass

                    relation = (
                        "all_differ"
                        if len(unique_sizes) == 3
                        else "two_agree_one_differs"
                    )
                    row = {
                        "case_id": case_id,
                        "distribution": dist,
                        "n": n,
                        "seed": seed,
                        "density": density,
                        "marathe_size": sizes_found["marathe"],
                        "wan_size": sizes_found["wan"],
                        "funke_size": sizes_found["funke"],
                        "opt": opt_size,
                        "relation": relation,
                        "funke_vs_wan": (
                            "smaller"
                            if sizes_found["funke"] < sizes_found["wan"]
                            else "larger"
                            if sizes_found["funke"] > sizes_found["wan"]
                            else "same"
                        ),
                        "funke_vs_marathe": (
                            "smaller"
                            if sizes_found["funke"] < sizes_found["marathe"]
                            else "larger"
                            if sizes_found["funke"] > sizes_found["marathe"]
                            else "same"
                        ),
                    }
                    index_rows.append(row)
                    print(
                        f"divergent {case_id}: "
                        f"m={sizes_found['marathe']} w={sizes_found['wan']} "
                        f"f={sizes_found['funke']}"
                    )

    index_csv = out_root / "index.csv"
    fields = [
        "case_id",
        "distribution",
        "n",
        "seed",
        "density",
        "marathe_size",
        "wan_size",
        "funke_size",
        "opt",
        "relation",
        "funke_vs_wan",
        "funke_vs_marathe",
    ]
    with index_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(index_rows)

    print(f"searched,{searched}")
    print(f"divergent,{divergent}")
    print(f"wrote {index_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
