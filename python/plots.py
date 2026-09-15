"""Plot experimental results from results/experiments.csv."""

from __future__ import annotations

import argparse
import csv
import math
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib

# Headless-safe default when saving without an interactive backend request.
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


def aggregate(rows: list[dict[str, str]], y_key: str) -> dict[str, dict[int, list[float]]]:
    """distribution -> n -> list of y values."""
    data: dict[str, dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        y = _float(row, y_key)
        if y is None:
            continue
        dist = row.get("distribution", "?")
        n = int(float(row["n"]))
        data[dist][n].append(y)
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
    grouped = aggregate(rows, y_key)
    fig, ax = plt.subplots(figsize=(8, 5))
    for dist in sorted(grouped):
        xs = sorted(grouped[dist])
        ys = [sum(grouped[dist][n]) / len(grouped[dist][n]) for n in xs]
        ax.plot(xs, ys, marker="o", label=dist)
    ax.set_xlabel("n")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    if log_y:
        ax.set_yscale("log")
    ax.legend(frameon=False)
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return out_path


def generate_plots(experiments_csv: Path, save_dir: Path) -> list[Path]:
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
    return outputs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Plot MCDS experiment CSV metrics.")
    parser.add_argument(
        "--experiments-csv",
        default="results/experiments.csv",
        help="consolidated experiment table",
    )
    parser.add_argument(
        "--save-dir",
        default="results/plots",
        help="directory for PNG outputs",
    )
    args = parser.parse_args(argv)
    paths = generate_plots(Path(args.experiments_csv), Path(args.save_dir))
    for path in paths:
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
