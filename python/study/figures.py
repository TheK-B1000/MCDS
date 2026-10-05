"""Paper figures for MCDS studies (matplotlib, static).

Design rules applied (see analysis_notes.md for statistics):
  * each point = median across graphs of a cell; whiskers = interquartile range
    across graphs (not a CI) — stated on every axis label/title;
  * the number of graphs per point is printed on every figure;
  * algorithms keep a fixed colour AND a fixed marker (identity is never colour
    alone; palette validated for colour-vision deficiency);
  * one y-axis per chart; geometries are small multiples, never overlaid scales;
  * log scales are used only for quantities spanning orders of magnitude and are
    labelled as such.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from pathlib import Path

from .analysis import _f, quantile, read_csv

# Categorical slots 1-4 of the validated reference palette (light mode).
COLORS = {"marathe": "#2a78d6", "wan": "#eb6834", "funke": "#1baf7a", "li": "#eda100"}
MARKERS = {"marathe": "o", "wan": "s", "funke": "^", "li": "D"}
LABELS = {"marathe": "Marathe", "wan": "Wan", "funke": "Funke", "li": "Li S-MIS"}
INK = "#2b2b2b"
MUTED = "#6b6b6b"
GRID = "#e6e6e3"

METRICS_VS = [
    ("t_algorithm_ms", "T_algorithm (ms, log scale)", True),
    ("cds_size", "CDS size |D|", False),
    ("cds_fraction", "CDS fraction |D| / |V|", False),
    ("neighbor_queries", "Range-neighbour queries (log scale)", True),
    ("candidates_examined", "Candidate points examined (log scale)", True),
    ("distance_computations", "Exact distance computations (log scale)", True),
    ("heap_peak_additional_bytes", "Algorithm heap peak (bytes, log scale)", True),
    ("empirical_ratio", "Empirical ratio |D| / OPT", False),
]


def _plt():
    import matplotlib  # noqa: PLC0415

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt  # noqa: PLC0415

    plt.rcParams.update({
        "axes.edgecolor": MUTED, "axes.labelcolor": INK, "xtick.color": MUTED, "ytick.color": MUTED,
        "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "axes.spines.top": False,
        "axes.spines.right": False, "font.size": 9, "axes.titlesize": 10, "legend.frameon": False,
        "lines.linewidth": 2, "savefig.dpi": 200,
    })
    return plt


def _stats(xs: list[float]) -> tuple[float, float, float]:
    s = sorted(xs)
    return statistics.median(s), quantile(s, 0.25), quantile(s, 0.75)


def _algos(gl: list[dict[str, str]]) -> list[str]:
    present = {r["algorithm"] for r in gl}
    return [a for a in COLORS if a in present]


def _save(fig, out: Path, name: str, written: list[str]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{name}.png"
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    fig.savefig(out / f"{name}.svg", bbox_inches="tight", facecolor="white")
    written.append(str(path))


def _sample_note(counts: list[int]) -> str:
    if not counts:
        return ""
    lo, hi = min(counts), max(counts)
    return f"graphs per point: {lo}" if lo == hi else f"graphs per point: {lo}–{hi}"


def line_by_factor(gl, metric, ylabel, logy, xkey, xlabel, fixed_key, out, written, plt) -> None:
    algos = _algos(gl)
    geoms = sorted({r["geometry"] for r in gl})
    fixed_vals = sorted({r[fixed_key] for r in gl}, key=lambda v: float(v) if v else 0)
    for fv in fixed_vals:
        rows = [r for r in gl if r[fixed_key] == fv and _f(r.get(metric)) is not None]
        if not rows or len({r[xkey] for r in rows}) < 2:
            continue
        fig, axes = plt.subplots(1, len(geoms), figsize=(3.2 * len(geoms), 3.0), squeeze=False, sharey=True)
        counts: list[int] = []
        for ax, geom in zip(axes[0], geoms):
            for a in algos:
                pts = defaultdict(list)
                for r in rows:
                    if r["geometry"] == geom and r["algorithm"] == a:
                        pts[float(r[xkey])].append(_f(r[metric]))
                if not pts:
                    continue
                xs = sorted(pts)
                med, lo, hi = zip(*(_stats(pts[x]) for x in xs))
                counts += [len(pts[x]) for x in xs]
                ax.errorbar(xs, med, yerr=[[max(0.0, m - l) for m, l in zip(med, lo)], [max(0.0, h - m) for m, h in zip(med, hi)]],
                            color=COLORS[a], marker=MARKERS[a], markersize=5, capsize=0, elinewidth=1,
                            label=LABELS[a])
            ax.set_title(geom.replace("_", " "), color=INK)
            ax.set_xlabel(xlabel)
            if xkey == "n":
                ax.set_xscale("log")
            if logy:
                ax.set_yscale("log")
        axes[0][0].set_ylabel(ylabel)
        handles, labels = axes[0][0].get_legend_handles_labels()
        fig.legend(handles, labels, loc="upper center", ncol=len(algos), bbox_to_anchor=(0.5, 1.08))
        fig.suptitle(f"{ylabel} vs {xlabel} — {fixed_key}={fv}; median and IQR across graphs; "
                     f"{_sample_note(counts)}", y=1.16, fontsize=9, color=MUTED)
        _save(fig, out, f"{metric}_vs_{xkey}__{fixed_key}_{fv}", written)
        plt.close(fig)


def scatter(gl, xmetric, xlabel, ymetric, ylabel, out, written, plt, logx=True, logy=True) -> None:
    algos = _algos(gl)
    fig, ax = plt.subplots(figsize=(4.6, 3.4))
    k = 0
    for a in algos:
        pts = [(_f(r[xmetric]), _f(r[ymetric])) for r in gl if r["algorithm"] == a]
        pts = [(x, y) for x, y in pts if x is not None and y is not None and (not logx or x > 0) and (not logy or y > 0)]
        k += len(pts)
        if pts:
            ax.scatter(*zip(*pts), s=14, color=COLORS[a], marker=MARKERS[a], alpha=0.75, label=LABELS[a],
                       edgecolors="white", linewidths=0.4)
    if logx:
        ax.set_xscale("log")
    if logy:
        ax.set_yscale("log")
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.legend()
    ax.set_title(f"one point per (graph, algorithm); {k} points", color=MUTED, fontsize=9)
    _save(fig, out, f"{ymetric}_vs_{xmetric}", written)
    plt.close(fig)


def by_geometry(gl, metric, ylabel, logy, out, written, plt) -> None:
    algos = _algos(gl)
    geoms = sorted({r["geometry"] for r in gl})
    for (n, d) in sorted({(r["n"], r["density_target"]) for r in gl}, key=lambda t: (int(t[0]), t[1])):
        rows = [r for r in gl if r["n"] == n and r["density_target"] == d and _f(r.get(metric)) is not None]
        if not rows:
            continue
        fig, ax = plt.subplots(figsize=(1.4 * len(geoms) + 2, 3.0))
        width = 0.8 / max(1, len(algos))
        counts = []
        for i, a in enumerate(algos):
            for j, g in enumerate(geoms):
                xs = [_f(r[metric]) for r in rows if r["geometry"] == g and r["algorithm"] == a]
                if not xs:
                    continue
                counts.append(len(xs))
                med, lo, hi = _stats(xs)
                x = j - 0.4 + width * (i + 0.5)
                ax.errorbar([x], [med], yerr=[[max(0.0, med - lo)], [max(0.0, hi - med)]], color=COLORS[a], marker=MARKERS[a],
                            markersize=6, elinewidth=1, label=LABELS[a] if j == 0 else None)
        ax.set_xticks(range(len(geoms)))
        ax.set_xticklabels([g.replace("_", "\n") for g in geoms])
        if logy:
            ax.set_yscale("log")
        ax.set_ylabel(ylabel)
        ax.legend(ncol=len(algos), loc="upper center", bbox_to_anchor=(0.5, 1.22))
        ax.set_title(f"n={n}, density={d}; median and IQR; {_sample_note(counts)}", color=MUTED, fontsize=9, y=1.2)
        _save(fig, out, f"{metric}_by_geometry__n{n}_density{d}", written)
        plt.close(fig)


def validity_plot(valid_rows, out, written, plt) -> None:
    algos = [a for a in COLORS if any(v["algorithm"] == a for v in valid_rows)]
    if not algos:
        return
    fig, ax = plt.subplots(figsize=(4.6, 0.5 * len(algos) + 1.2))
    for i, a in enumerate(algos):
        rows = [v for v in valid_rows if v["algorithm"] == a]
        k = sum(int(v["valid"]) for v in rows)
        n = sum(int(v["executions"]) for v in rows)
        from .analysis import wilson  # noqa: PLC0415

        lo, hi = wilson(k, n)
        ax.errorbar([k / n], [i], xerr=[[max(0.0, k / n - lo)], [max(0.0, hi - k / n)]], color=COLORS[a], marker=MARKERS[a],
                    markersize=7, elinewidth=1)
        ax.annotate(f"{k}/{n}", (k / n, i), textcoords="offset points", xytext=(8, 4), color=INK, fontsize=8)
    ax.set_yticks(range(len(algos)))
    ax.set_yticklabels([LABELS[a] for a in algos])
    ax.set_xlim(min(0.9, ax.get_xlim()[0]), 1.01)
    ax.set_xlabel("Valid-CDS rate over validated executions (Wilson 95% CI)")
    _save(fig, out, "valid_solution_rate", written)
    plt.close(fig)


def pareto(gl, out, written, plt) -> None:
    """Runtime vs CDS fraction per cell (median over graphs); Pareto-optimal algorithms ringed."""
    cells = sorted({r["cell_id"] for r in gl})
    for cell in cells:
        rows = [r for r in gl if r["cell_id"] == cell]
        pts = {}
        k = 0
        for a in _algos(rows):
            ts = [_f(r["t_algorithm_ms"]) for r in rows if r["algorithm"] == a and _f(r["t_algorithm_ms"])]
            cs = [_f(r["cds_fraction"]) for r in rows if r["algorithm"] == a and _f(r["cds_fraction"]) is not None]
            if ts and cs:
                pts[a] = (statistics.median(ts), statistics.median(cs))
                k = max(k, len(ts))
        if len(pts) < 2:
            continue
        frontier = {a for a, (t, c) in pts.items()
                    if not any((t2 <= t and c2 <= c) and (t2 < t or c2 < c) for b, (t2, c2) in pts.items() if b != a)}
        fig, ax = plt.subplots(figsize=(4.2, 3.2))
        for a, (t, c) in pts.items():
            ax.scatter([t], [c], color=COLORS[a], marker=MARKERS[a], s=50, label=LABELS[a], zorder=3,
                       edgecolors="white", linewidths=1.5)
            if a in frontier:
                ax.scatter([t], [c], s=170, facecolors="none", edgecolors=INK, linewidths=1, zorder=2)
        ax.set_xscale("log")
        ax.set_xlabel("Median T_algorithm (ms, log scale)")
        ax.set_ylabel("Median CDS fraction")
        ax.legend(fontsize=8)
        ax.set_title(f"{cell}\nringed = Pareto-optimal; graphs: {k}", color=MUTED, fontsize=8)
        safe = "".join(ch if ch.isalnum() else "_" for ch in cell)
        _save(fig, out / "pareto", f"pareto__{safe}", written)
        plt.close(fig)


def make_all(study_dir: Path) -> list[str]:
    plt = _plt()
    gl = read_csv(study_dir / "graph_level.csv")
    out = study_dir / "figures"
    written: list[str] = []
    if not gl:
        return written
    for metric, label, logy in METRICS_VS:
        if any(_f(r.get(metric)) is not None for r in gl):
            line_by_factor(gl, metric, label, logy, "n", "n (log scale)", "density_target", out, written, plt)
            line_by_factor(gl, metric, label, logy, "density_target", "density target (points / unit area)",
                           "n", out, written, plt)
    for metric, label, logy in METRICS_VS[:3]:
        by_geometry(gl, metric, label, logy, out, written, plt)
    scatter(gl, "mean_degree", "Observed mean degree (log scale)", "t_algorithm_ms", "T_algorithm (ms, log)",
            out, written, plt)
    scatter(gl, "mean_degree", "Observed mean degree", "cds_fraction", "CDS fraction", out, written, plt,
            logx=False, logy=False)
    scatter(gl, "neighbor_queries", "Range-neighbour queries (log)", "t_algorithm_ms", "T_algorithm (ms, log)",
            out, written, plt)
    scatter(gl, "distance_computations", "Distance computations (log)", "t_algorithm_ms",
            "T_algorithm (ms, log)", out, written, plt)
    scatter(gl, "t_algorithm_ms", "T_algorithm (ms, log)", "cds_fraction", "CDS fraction", out, written, plt,
            logx=True, logy=False)
    vpath = study_dir / "validity.csv"
    if vpath.is_file() and vpath.stat().st_size:
        validity_plot(read_csv(vpath), out, written, plt)
    pareto(gl, out, written, plt)
    return written


__all__ = ["make_all"]
