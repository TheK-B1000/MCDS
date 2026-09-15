"""Plot experimental results from results/*.csv."""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib

if "--save-dir" in sys.argv and "MPLBACKEND" not in __import__("os").environ:
    matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402


def load_ok_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return [r for r in rows if r.get("status") == "ok"]


def _float(row: dict[str, str], key: str) -> float | None:
    val = row.get(key, "")
    if val is None or val == "":
        return None
    try:
        return float(val)
    except ValueError:
        return None


def aggregate_by_algo(
    rows: list[dict[str, str]], y_key: str
) -> dict[str, dict[str, dict[int, list[float]]]]:
    """algorithm -> distribution -> n -> values."""
    data: dict[str, dict[str, dict[int, list[float]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(list))
    )
    for row in rows:
        y = _float(row, y_key)
        if y is None:
            continue
        algo = row.get("algorithm", "?")
        dist = row.get("distribution", "?")
        n = int(float(row["n"]))
        data[algo][dist][n].append(y)
    return data


def plot_metric(
    rows: list[dict[str, str]],
    y_key: str,
    ylabel: str,
    title: str,
    out_path: Path,
    *,
    log_y: bool = False,
) -> Path:
    grouped = aggregate_by_algo(rows, y_key)
    fig, ax = plt.subplots(figsize=(8.5, 5.2))
    for algo in sorted(grouped):
        for dist in sorted(grouped[algo]):
            xs = sorted(grouped[algo][dist])
            ys = [
                sum(grouped[algo][dist][n]) / len(grouped[algo][dist][n]) for n in xs
            ]
            ax.plot(xs, ys, marker="o", label=f"{algo}/{dist}")
    ax.set_xlabel("n")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    if log_y:
        ax.set_yscale("log")
    ax.legend(frameon=False, fontsize=8, ncol=2)
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return out_path


def plot_approx_ratios(exact_csv: Path, out_path: Path) -> Path | None:
    if not exact_csv.is_file():
        return None
    with exact_csv.open("r", encoding="utf-8", newline="") as handle:
        rows = [r for r in csv.DictReader(handle) if r.get("status") == "ok"]
    if not rows:
        return None
    by_n: dict[int, dict[str, list[float]]] = defaultdict(lambda: {"marathe": [], "wan": []})
    for r in rows:
        n = int(r["n"])
        by_n[n]["marathe"].append(float(r["marathe_over_opt"]))
        by_n[n]["wan"].append(float(r["wan_over_opt"]))
    fig, ax = plt.subplots(figsize=(7.5, 4.8))
    xs = sorted(by_n)
    for algo in ("marathe", "wan"):
        ys = [sum(by_n[n][algo]) / len(by_n[n][algo]) for n in xs]
        ax.plot(xs, ys, marker="o", label=f"{algo} CDS/OPT")
    ax.axhline(1.0, color="#888", linestyle="--", linewidth=1, label="OPT")
    ax.set_xlabel("n")
    ax.set_ylabel("Observed CDS / OPT")
    ax.set_title("Observed approximation ratio (exact-small study)")
    ax.legend(frameon=False)
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return out_path


def generate_plots(experiments_csv: Path, save_dir: Path, exact_csv: Path | None = None) -> list[Path]:
    rows = load_ok_rows(experiments_csv)
    if not rows:
        raise SystemExit(f"no successful rows in {experiments_csv}")

    outputs = [
        plot_metric(rows, "cds_ratio", "mean CDS ratio", "CDS ratio vs n", save_dir / "cds_ratio_vs_n.png"),
        plot_metric(
            rows,
            "algorithm_ms",
            "mean algorithm_ms",
            "algorithm_ms vs n",
            save_dir / "algorithm_ms_vs_n.png",
            log_y=True,
        ),
        plot_metric(
            rows,
            "peak_memory_mb",
            "mean peak_memory_mb",
            "peak process memory vs n",
            save_dir / "peak_memory_vs_n.png",
        ),
        plot_metric(
            rows,
            "algorithm_neighbor_queries",
            "mean neighbor queries",
            "algorithm neighbor queries vs n",
            save_dir / "neighbor_queries_vs_n.png",
        ),
        plot_metric(
            rows,
            "algorithm_candidates_examined",
            "mean candidates examined",
            "algorithm candidates examined vs n",
            save_dir / "candidates_vs_n.png",
        ),
    ]
    if exact_csv is not None:
        path = plot_approx_ratios(exact_csv, save_dir / "observed_approx_vs_n.png")
        if path is not None:
            outputs.append(path)
    return outputs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Plot MCDS experiment CSV metrics.")
    parser.add_argument("--experiments-csv", default="results/two_algorithm_smoke.csv")
    parser.add_argument("--save-dir", default="results/plots")
    parser.add_argument("--exact-csv", default="results/exact_small_study.csv")
    args = parser.parse_args(argv)
    exact = Path(args.exact_csv)
    paths = generate_plots(Path(args.experiments_csv), Path(args.save_dir), exact if exact.is_file() else None)
    for path in paths:
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
