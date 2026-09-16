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

ALGO_STYLE = {
    "marathe": {"color": "#1f77b4", "marker": "o", "linestyle": "-"},
    "wan": {"color": "#ff7f0e", "marker": "s", "linestyle": "--"},
    "funke": {"color": "#2ca02c", "marker": "^", "linestyle": "-."},
    "li": {"color": "#d62728", "marker": "D", "linestyle": ":"},
}


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


def aggregate_by_algo_n(rows: list[dict[str, str]], y_key: str) -> dict[str, dict[int, list[float]]]:
    data: dict[str, dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        y = _float(row, y_key)
        if y is None:
            continue
        algo = row.get("algorithm", "?")
        n = int(float(row["n"]))
        data[algo][n].append(y)
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
    grouped = aggregate_by_algo_n(rows, y_key)
    fig, ax = plt.subplots(figsize=(8.0, 5.0))
    for algo in sorted(grouped):
        style = ALGO_STYLE.get(algo, {"color": None, "marker": "o", "linestyle": "-"})
        xs = sorted(grouped[algo])
        ys = [sum(grouped[algo][n]) / len(grouped[algo][n]) for n in xs]
        ax.plot(
            xs,
            ys,
            label=algo,
            color=style.get("color"),
            marker=style.get("marker"),
            linestyle=style.get("linestyle"),
            linewidth=1.8,
            markersize=7,
        )
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


def plot_approx_ratios(exact_csv: Path, out_path: Path) -> Path | None:
    if not exact_csv.is_file():
        return None
    with exact_csv.open("r", encoding="utf-8", newline="") as handle:
        rows = [r for r in csv.DictReader(handle) if r.get("status") == "ok"]
    if not rows:
        return None
    algos = ("marathe", "wan", "funke", "li")
    by_n: dict[int, dict[str, list[float]]] = defaultdict(lambda: {a: [] for a in algos})
    for r in rows:
        n = int(r["n"])
        for algo in algos:
            key = f"{algo}_over_opt"
            if r.get(key) not in ("", None):
                by_n[n][algo].append(float(r[key]))
    fig, ax = plt.subplots(figsize=(7.5, 4.8))
    xs = sorted(by_n)
    for algo in algos:
        style = ALGO_STYLE[algo]
        use_xs: list[int] = []
        ys: list[float] = []
        for n in xs:
            vals = by_n[n][algo]
            if vals:
                use_xs.append(n)
                ys.append(sum(vals) / len(vals))
        if use_xs:
            ax.plot(
                use_xs,
                ys,
                label=f"{algo} CDS/OPT",
                color=style["color"],
                marker=style["marker"],
                linestyle=style["linestyle"],
            )
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


def plot_quality_vs_query_cost(rows: list[dict[str, str]], out_path: Path) -> Path | None:
    """Scatter mean delta CDS vs query multiplier relative to Marathe (paired by dataset)."""
    by_ds: dict[str, dict[str, dict[str, str]]] = {}
    for row in rows:
        ds = row.get("dataset_csv", "")
        algo = row.get("algorithm", "")
        if ds and algo:
            by_ds.setdefault(ds, {})[algo] = row
    fig, ax = plt.subplots(figsize=(7.5, 5.0))
    plotted = False
    for algo in ("wan", "funke", "li"):
        xs: list[float] = []
        ys: list[float] = []
        for algos in by_ds.values():
            if "marathe" not in algos or algo not in algos:
                continue
            m_cds = float(algos["marathe"]["cds_size"])
            a_cds = float(algos[algo]["cds_size"])
            m_q = float(algos["marathe"]["algorithm_neighbor_queries"])
            a_q = float(algos[algo]["algorithm_neighbor_queries"])
            if m_q <= 0:
                continue
            xs.append(a_q / m_q)
            ys.append(a_cds - m_cds)
        if not xs:
            continue
        style = ALGO_STYLE[algo]
        ax.scatter(xs, ys, label=algo, color=style["color"], marker=style["marker"], s=36, alpha=0.85)
        plotted = True
    if not plotted:
        plt.close(fig)
        return None
    ax.axhline(0.0, color="#888", linestyle="--", linewidth=1)
    ax.axvline(1.0, color="#888", linestyle="--", linewidth=1)
    ax.set_xlabel("neighbor-query multiplier vs Marathe")
    ax.set_ylabel("CDS size − Marathe CDS size")
    ax.set_title("Quality vs query cost (paired datasets)")
    ax.legend(frameon=False)
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return out_path


def plot_explicit_vs_implicit(baseline_csv: Path, save_dir: Path) -> list[Path]:
    if not baseline_csv.is_file():
        return []
    with baseline_csv.open("r", encoding="utf-8", newline="") as handle:
        rows = [r for r in csv.DictReader(handle) if r.get("status") == "ok"]
    if not rows:
        return []
    xs = [int(r["n"]) for r in rows]
    mem_e = [float(r["explicit_est_memory_mb"]) for r in rows]
    build_e = [float(r["explicit_build_ms"]) for r in rows]
    build_i = [
        float(r["implicit_index_build_ms"])
        for r in rows
        if r.get("implicit_index_build_ms") not in ("", None)
    ]
    outputs: list[Path] = []

    fig, ax = plt.subplots(figsize=(7.5, 4.8))
    ax.plot(xs, mem_e, marker="o", label="explicit (estimated bytes)")
    ax.set_xlabel("n")
    ax.set_ylabel("estimated memory (MB)")
    ax.set_title("Explicit vs implicit memory (estimated explicit storage)")
    ax.legend(frameon=False)
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    out1 = save_dir / "explicit_vs_implicit_memory.png"
    save_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(out1, dpi=140, bbox_inches="tight")
    plt.close(fig)
    outputs.append(out1)

    fig, ax = plt.subplots(figsize=(7.5, 4.8))
    ax.plot(xs, build_e, marker="o", label="explicit construction (measured)")
    if len(build_i) == len(xs):
        ax.plot(xs, build_i, marker="s", label="implicit index build (measured)")
    ax.set_xlabel("n")
    ax.set_ylabel("ms")
    ax.set_title("Explicit vs implicit build time")
    ax.legend(frameon=False)
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    out2 = save_dir / "explicit_vs_implicit_build_time.png"
    fig.savefig(out2, dpi=140, bbox_inches="tight")
    plt.close(fig)
    outputs.append(out2)
    return outputs


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
    qpath = plot_quality_vs_query_cost(rows, save_dir / "quality_vs_query_cost.png")
    if qpath is not None:
        outputs.append(qpath)
    if exact_csv is not None:
        path = plot_approx_ratios(exact_csv, save_dir / "observed_approx_vs_n.png")
        if path is not None:
            outputs.append(path)
    baseline = Path("results/explicit_vs_implicit.csv")
    if baseline.is_file():
        outputs.extend(plot_explicit_vs_implicit(baseline, save_dir))
    return outputs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Plot MCDS experiment CSV metrics.")
    parser.add_argument("--experiments-csv", default="results/four_algorithm_smoke.csv")
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
