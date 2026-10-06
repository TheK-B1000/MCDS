"""Mechanical replicate-count decision (experiments/precision/replicate_rule_v1.json).

    py -3 python/replicate_decision.py --study results/studies/precision_pilot

Reads the pilot's graph_level.csv and applies the locked rule (narrowness only;
see the rule's amendment record): for every ladder value k, every
(geometry, density) stratum and every algorithm pair,
the Student-t 95% CI half-width of the paired CDS-fraction difference (in
percentage points) and of the paired log runtime ratio (as a multiplicative
half-width exp(h) - 1), using replicates 1..k only. The smallest k narrow
enough in every stratum is selected; if none (52 included), no count is
selected and the exit status is 2: stop for a protocol decision. Trajectory
plots (--plots) are a non-binding diagnostic. Every threshold is read from the
rule file.
"""

from __future__ import annotations

import argparse
import csv
import functools
import json
import math
import statistics
import sys
from collections import defaultdict
from itertools import combinations
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
RULE = _ROOT / "experiments" / "precision" / "replicate_rule_v1.json"
ALGORITHMS = ("marathe", "wan", "funke", "li")


@functools.lru_cache(maxsize=None)
def t975(df: int) -> float:
    """Student-t 0.975 quantile (Simpson integration of the density + bisection;
    matches tables to 6 decimals). The standard library has no t distribution."""
    c = math.exp(math.lgamma((df + 1) / 2) - math.lgamma(df / 2)) / math.sqrt(df * math.pi)

    def pdf(x: float) -> float:
        return c * (1 + x * x / df) ** (-(df + 1) / 2)

    def cdf(x: float, m: int = 4000) -> float:
        h = x / m
        s = pdf(0.0) + pdf(x) + sum((4 if i % 2 else 2) * pdf(i * h) for i in range(1, m))
        return 0.5 + s * h / 3

    lo, hi = 0.0, 50.0
    for _ in range(80):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if cdf(mid) < 0.975 else (lo, mid)
    return (lo + hi) / 2


def half_width(xs: list[float]) -> float:
    return t975(len(xs) - 1) * statistics.stdev(xs) / math.sqrt(len(xs))


def comparisons(rows: list[dict[str, str]], ladder: list[int]) -> list[dict]:
    """One record per (stratum, cell, pair, k) with both precision values."""
    by: dict[tuple, dict[int, dict[str, dict[str, str]]]] = defaultdict(lambda: defaultdict(dict))
    for r in rows:
        if r.get("spatial_backend", "cgal") != "cgal":
            continue
        key = (r["geometry"], float(r["density_target"]), int(r["n"]))
        by[key][int(float(r["replicate"]))][r["algorithm"]] = r
    out = []
    for (geometry, density, n), reps in sorted(by.items()):
        for a, b in combinations(ALGORITHMS, 2):
            order = sorted(rep for rep, g in reps.items() if a in g and b in g)
            if order != list(range(1, len(order) + 1)):
                raise ValueError(f"{geometry} d={density} n={n} {a}-{b}: replicates are not 1..m "
                                 f"(missing graphs would break the prefix rule): {order[:10]}...")
            d_cds, l_t = [], []
            for rep in order:
                ga, gb = reps[rep][a], reps[rep][b]
                d_cds.append(float(ga["cds_fraction"]) - float(gb["cds_fraction"]))
                l_t.append(math.log(float(ga["t_algorithm_ms"]) / float(gb["t_algorithm_ms"])))
            for k in ladder:
                if k > len(order):
                    raise ValueError(f"{geometry} d={density} n={n}: only {len(order)} graphs, ladder needs {k}")
                out.append({"geometry": geometry, "density": density, "n": n, "pair": f"{a}-{b}", "k": k,
                            "cds_hw_pp": 100.0 * half_width(d_cds[:k]),
                            "cds_diff_pp": 100.0 * statistics.fmean(d_cds[:k]),
                            "rt_hw_mult": math.exp(half_width(l_t[:k])) - 1.0,
                            "rt_ratio_geomean": math.exp(statistics.fmean(l_t[:k]))})
    return out


def decide(comps: list[dict], rule: dict) -> dict:
    """Narrowness in every (geometry, density) stratum; smallest passing k.
    If no k passes (52 included), the result is an explicit failure: no count
    is selected and the protocol needs a decision."""
    ladder = rule["ladder"]
    nar = rule["narrowness"]
    strata = sorted({(c["geometry"], c["density"]) for c in comps})
    by = defaultdict(list)
    for c in comps:
        by[(c["geometry"], c["density"], c["k"])].append(c)
    table = []
    for s in strata:
        for k in ladder:
            cs = by[(s[0], s[1], k)]
            cds = [c["cds_hw_pp"] for c in cs]
            rt = [c["rt_hw_mult"] for c in cs]
            share_cds = sum(x <= nar["cds_fraction"]["share_threshold_pp"] for x in cds) / len(cds)
            share_rt = sum(x <= nar["runtime_ratio"]["share_threshold"] for x in rt) / len(rt)
            narrow = (share_cds >= nar["cds_fraction"]["min_share"] and max(cds) <= nar["cds_fraction"]["max_pp"]
                      and share_rt >= nar["runtime_ratio"]["min_share"] and max(rt) <= nar["runtime_ratio"]["max"])
            table.append({"geometry": s[0], "density": s[1], "k": k, "comparisons": len(cs),
                          "cds_share_ok": share_cds, "cds_max_pp": max(cds), "cds_median_pp": statistics.median(cds),
                          "rt_share_ok": share_rt, "rt_max": max(rt), "rt_median": statistics.median(rt),
                          "narrow": narrow})
    passing = [k for k in ladder if all(r["narrow"] for r in table if r["k"] == k)]
    cap = ladder[-1]
    failing_at_cap = [] if passing else [
        c for c in comps if c["k"] == cap
        and (c["cds_hw_pp"] > nar["cds_fraction"]["share_threshold_pp"]
             or c["rt_hw_mult"] > nar["runtime_ratio"]["share_threshold"])]
    return {"table": table, "passing_k": passing,
            "status": "selected" if passing else "precision_target_not_met",
            "chosen_k": passing[0] if passing else None,
            "failing_strata_at_cap": [] if passing else sorted(
                {(r["geometry"], r["density"]) for r in table if r["k"] == cap and not r["narrow"]}),
            "comparisons_missing_targets_at_cap": failing_at_cap}


def plot_trajectories(comps: list[dict], out_dir: Path) -> list[Path]:
    """Non-binding diagnostic: point estimates and 95% CIs across k, one column
    per (n, pair) and one figure per stratum; never used for the selection."""
    import matplotlib  # noqa: PLC0415

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt  # noqa: PLC0415

    out_dir.mkdir(parents=True, exist_ok=True)
    by = defaultdict(list)
    for c in comps:
        by[(c["geometry"], c["density"])].append(c)
    written = []
    for (geometry, density), cs in sorted(by.items()):
        panels = sorted({(c["n"], c["pair"]) for c in cs})
        fig, axes = plt.subplots(2, len(panels), figsize=(2.2 * len(panels), 5.2), squeeze=False, sharex=True)
        for j, (n, pair) in enumerate(panels):
            pts = sorted((c for c in cs if c["n"] == n and c["pair"] == pair), key=lambda c: c["k"])
            ks = [c["k"] for c in pts]
            axes[0][j].errorbar(ks, [c["cds_diff_pp"] for c in pts], yerr=[c["cds_hw_pp"] for c in pts],
                                marker="o", ms=3, lw=1, capsize=2)
            axes[0][j].axhline(0, color="0.6", lw=0.6)
            ratio = [c["rt_ratio_geomean"] for c in pts]
            lo = [r - r / (1 + c["rt_hw_mult"]) for r, c in zip(ratio, pts)]
            hi = [r * c["rt_hw_mult"] for r, c in zip(ratio, pts)]
            axes[1][j].errorbar(ks, ratio, yerr=[lo, hi], marker="o", ms=3, lw=1, capsize=2)
            axes[1][j].axhline(1, color="0.6", lw=0.6)
            axes[1][j].set_yscale("log")
            axes[0][j].set_title(f"n={n}\n{pair}", fontsize=7)
            axes[1][j].set_xlabel("k graphs", fontsize=7)
            for ax in (axes[0][j], axes[1][j]):
                ax.tick_params(labelsize=6)
        axes[0][0].set_ylabel("CDS fraction diff (pp)", fontsize=7)
        axes[1][0].set_ylabel("runtime ratio A/B", fontsize=7)
        fig.suptitle(f"{geometry}, density {density:g}: estimates across k (non-binding diagnostic)", fontsize=9)
        fig.tight_layout()
        path = out_dir / f"trajectory_{geometry}_d{density:g}.png"
        fig.savefig(path, dpi=110)
        plt.close(fig)
        written.append(path)
    return written


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--study", required=True, help="precision-pilot study directory (contains graph_level.csv)")
    ap.add_argument("--rule", default=str(RULE))
    ap.add_argument("--json", default=None, help="write the full decision as JSON")
    ap.add_argument("--plots", default=None, help="directory for the non-binding trajectory plots")
    args = ap.parse_args(argv)
    rule = json.loads(Path(args.rule).read_text(encoding="utf-8"))
    with open(Path(args.study) / "graph_level.csv", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    comps = comparisons(rows, rule["ladder"])
    res = decide(comps, rule)
    print("geometry        dens   k   CDS ok-share  max pp  med pp  | RT ok-share  max    med    | narrow")
    for r in res["table"]:
        print(f"{r['geometry']:15} {r['density']:<5} {r['k']:<3} {r['cds_share_ok']:6.2f}      "
              f"{r['cds_max_pp']:5.2f}  {r['cds_median_pp']:5.2f}  | {r['rt_share_ok']:6.2f}     "
              f"{r['rt_max']:.3f}  {r['rt_median']:.3f}  | {'yes' if r['narrow'] else 'NO'}")
    print(f"\nk narrow enough in every stratum: {res['passing_k'] or 'none'}")
    if res["status"] == "selected":
        print(f"SELECTED REPLICATE COUNT: {res['chosen_k']}")
    else:
        print(f"PRECISION TARGET NOT MET at k = {rule['ladder'][-1]}: failing strata {res['failing_strata_at_cap']}; "
              f"{len(res['comparisons_missing_targets_at_cap'])} comparison(s) miss the thresholds (see JSON). "
              "No replicate count is selected; STOP for a protocol decision before the final experiment.")
    if args.plots:
        n = len(plot_trajectories(comps, Path(args.plots)))
        print(f"{n} non-binding trajectory plot(s) written to {args.plots}")
    if args.json:
        Path(args.json).write_text(json.dumps({"rule": str(args.rule), **res, "comparisons": comps}, indent=2) + "\n",
                                   encoding="utf-8")
    return 0 if res["status"] == "selected" else 2


if __name__ == "__main__":
    sys.exit(main())
