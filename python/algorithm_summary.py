"""Emit a presentation-friendly algorithm summary table from experiment CSVs."""

from __future__ import annotations

import argparse
import csv
import statistics
import sys
from pathlib import Path

_PYTHON_DIR = Path(__file__).resolve().parent
if str(_PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(_PYTHON_DIR))


PAPER_META = {
    "marathe": {
        "paper": "Marathe et al., Networks",
        "year": "1995",
        "strategy": "BFS CDOM (level MIS + parents)",
        "theory": "classic CDOM analyses (UDG heuristics)",
    },
    "wan": {
        "paper": "Wan–Alzoubi–Frieder, INFOCOM",
        "year": "2002",
        "strategy": "rank MIS + tree-parent connectors",
        "theory": "<= 8",
    },
    "funke": {
        "paper": "Funke–Kesselman–Meyer–Segal, TOSN",
        "year": "2006",
        "strategy": "red-frontier MIS + recruiter connectors",
        "theory": "<= 6.91",
    },
    "li": {
        "paper": "Li–Thai–Wang–Yi–Wan–Du, WCMC",
        "year": "2005",
        "strategy": "Wan/Cheng MIS + Steiner Algorithm A",
        "theory": "4.8 + ln(5)  (~6.409) + 1.2",
    },
}


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else float("nan")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Algorithm summary table.")
    parser.add_argument("--experiments-csv", default="results/four_algorithm_smoke.csv")
    parser.add_argument("--exact-csv", default="results/exact_small_study.csv")
    parser.add_argument("--out", default="results/algorithm_summary.csv")
    args = parser.parse_args(argv)

    exp = Path(args.experiments_csv)
    exact = Path(args.exact_csv)
    if not exp.is_file():
        raise SystemExit(f"missing {exp}")

    with exp.open("r", encoding="utf-8", newline="") as handle:
        rows = [r for r in csv.DictReader(handle) if r.get("status") == "ok"]

    by_algo: dict[str, list[dict[str, str]]] = {}
    for r in rows:
        by_algo.setdefault(r["algorithm"], []).append(r)

    exact_means: dict[str, float] = {}
    if exact.is_file():
        with exact.open("r", encoding="utf-8", newline="") as handle:
            erows = [r for r in csv.DictReader(handle) if r.get("status") == "ok"]
        for algo in PAPER_META:
            key = f"{algo}_over_opt"
            vals = [float(r[key]) for r in erows if r.get(key) not in ("", None)]
            if vals:
                exact_means[algo] = _mean(vals)

    out_rows = []
    for algo, meta in PAPER_META.items():
        rs = by_algo.get(algo, [])
        out_rows.append(
            {
                "Algorithm": algo,
                "Paper": meta["paper"],
                "Year": meta["year"],
                "Core_strategy": meta["strategy"],
                "Theoretical_bound": meta["theory"],
                "Mean_observed_CDS_over_OPT": f"{exact_means.get(algo, float('nan')):.4f}"
                if algo in exact_means
                else "",
                "Mean_CDS_ratio": f"{_mean([float(r['cds_ratio']) for r in rs]):.4f}" if rs else "",
                "Median_algorithm_ms": f"{statistics.median([float(r['algorithm_ms']) for r in rs]):.4f}"
                if rs
                else "",
                "Mean_neighbor_queries": f"{_mean([float(r['algorithm_neighbor_queries']) for r in rs]):.1f}"
                if rs
                else "",
                "Mean_peak_memory_mb": f"{_mean([float(r['peak_memory_mb']) for r in rs]):.3f}"
                if rs
                else "",
            }
        )

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fields = list(out_rows[0].keys())
    with out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(out_rows)

    # Also print markdown-ish table
    print(f"wrote {out}")
    print("| " + " | ".join(fields) + " |")
    print("| " + " | ".join("---" for _ in fields) + " |")
    for r in out_rows:
        print("| " + " | ".join(str(r[f]) for f in fields) + " |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
