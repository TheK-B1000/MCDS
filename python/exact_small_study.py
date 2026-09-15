"""Tiny exact-vs-heuristic study (n <= 16). Analysis only."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

_PYTHON_DIR = Path(__file__).resolve().parent
if str(_PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(_PYTHON_DIR))

from generators import generate, write_csv  # noqa: E402
from gui_support import build_solver_command, find_mcds_executable, find_repo_root, run_solver  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Exact-small OPT vs Marathe/Wan.")
    parser.add_argument("--sizes", default="8,10,12,14,16")
    parser.add_argument("--seeds", default="1,2,3")
    parser.add_argument("--distributions", default="uniform,perturbed_grid,corridor")
    parser.add_argument("--density", type=float, default=6.0)
    parser.add_argument("--out", default="results/exact_small_study.csv")
    args = parser.parse_args(argv)

    repo = find_repo_root()
    exe = find_mcds_executable(repo)
    sizes = [int(x) for x in args.sizes.split(",") if x.strip()]
    seeds = [int(x) for x in args.seeds.split(",") if x.strip()]
    distributions = [x.strip() for x in args.distributions.split(",") if x.strip()]

    out_dir = repo / "datasets" / "exact_small"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_csv = repo / args.out
    out_csv.parent.mkdir(parents=True, exist_ok=True)

    fields = [
        "distribution",
        "n",
        "seed",
        "opt",
        "marathe_size",
        "wan_size",
        "marathe_over_opt",
        "wan_over_opt",
        "status",
        "error",
    ]
    rows: list[dict] = []

    for dist in distributions:
        for n in sizes:
            for seed in seeds:
                csv_path = out_dir / f"{dist}_n{n}_seed{seed}.csv"
                # Dense enough to usually connect at tiny n.
                gen_kwargs = {"density": args.density}
                if dist == "corridor":
                    gen_kwargs["corridor_width"] = 2.5
                if dist == "perturbed_grid":
                    gen_kwargs["jitter"] = 0.1
                result = generate(dist, n, seed, **gen_kwargs)
                write_csv(str(csv_path), result.points)

                row = {
                    "distribution": dist,
                    "n": n,
                    "seed": seed,
                    "opt": "",
                    "marathe_size": "",
                    "wan_size": "",
                    "marathe_over_opt": "",
                    "wan_over_opt": "",
                    "status": "ok",
                    "error": "",
                }

                # Connectivity gate via exact path: refuse disconnected.
                conn_json = out_dir / f"_conn_{dist}_n{n}_seed{seed}.json"
                conn = run_solver(
                    build_solver_command(exe, csv_path, conn_json, check_connectivity_only=True)
                )
                if not conn.result or not conn.result.get("connected_input"):
                    row["status"] = "disconnected"
                    row["error"] = "input not connected"
                    rows.append(row)
                    continue

                opt_json = out_dir / f"_opt_{dist}_n{n}_seed{seed}.json"
                opt_out = run_solver(
                    build_solver_command(exe, csv_path, opt_json, algorithm="marathe")
                )
                # Override: call exact-small directly
                import subprocess

                completed = subprocess.run(
                    [str(exe), "--input", str(csv_path), "--exact-small", "--output", str(opt_json), "--pretty"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if completed.returncode != 0 or not opt_json.is_file():
                    row["status"] = "exact_error"
                    row["error"] = (completed.stderr or completed.stdout or "exact failed").strip()
                    rows.append(row)
                    continue
                opt = json.loads(opt_json.read_text(encoding="utf-8"))
                opt_size = int(opt["cds_size"])
                row["opt"] = opt_size

                sizes_found = {}
                for algo in ("marathe", "wan"):
                    rj = out_dir / f"_{algo}_{dist}_n{n}_seed{seed}.json"
                    outcome = run_solver(
                        build_solver_command(exe, csv_path, rj, algorithm=algo)
                    )
                    if outcome.exit_code != 0 or not outcome.result:
                        row["status"] = "solver_error"
                        row["error"] = outcome.error or f"{algo} failed"
                        break
                    sizes_found[algo] = int(outcome.result["cds_size"])
                else:
                    row["marathe_size"] = sizes_found["marathe"]
                    row["wan_size"] = sizes_found["wan"]
                    row["marathe_over_opt"] = sizes_found["marathe"] / opt_size
                    row["wan_over_opt"] = sizes_found["wan"] / opt_size

                rows.append(row)
                _ = opt_out

    with out_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    ok = [r for r in rows if r["status"] == "ok"]
    if ok:
        m_ratios = [float(r["marathe_over_opt"]) for r in ok]
        w_ratios = [float(r["wan_over_opt"]) for r in ok]
        print(f"wrote {out_csv}")
        print(f"ok_rows,{len(ok)}")
        print(f"mean_marathe_over_opt,{sum(m_ratios)/len(m_ratios):.4f}")
        print(f"mean_wan_over_opt,{sum(w_ratios)/len(w_ratios):.4f}")
        print(f"worst_marathe_over_opt,{max(m_ratios):.4f}")
        print(f"worst_wan_over_opt,{max(w_ratios):.4f}")
    else:
        print(f"wrote {out_csv} but no successful rows")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
