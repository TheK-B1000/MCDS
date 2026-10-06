"""Apply the preregistered generator-freeze gates to a calibration file.

    py -3 python/calibration_gates.py \\
        --calibration experiments/calibration/generator_calibration_v1.json \\
        --gates experiments/calibration/gates_v1.json

Prints, for every primary cell, geometry, n, density, acceptance rate (Wilson
95% CI), clustering share, mean / median / min / max degree, and the G1 / G2 /
G3 verdicts; then the sparse-admission verdict for density-5 cells and an
overall freeze verdict. Gates are applied mechanically as recorded.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def evaluate(calibration: dict, gates: dict) -> dict:
    cells = {(c["geometry"], int(c["n"]), float(c["density"])): c for c in calibration["cells"]}
    g = gates["gates"]
    prim = gates["primary_cells"]
    rows = []
    g1_min = g["G1_connectivity"]["min_connected"]
    for geometry in prim["geometries"]:
        for n in prim["sizes"]:
            for d in prim["densities"]:
                c = cells.get((geometry, int(n), float(d)))
                if c is None:
                    rows.append({"geometry": geometry, "n": n, "density": d, "missing": True, "G1": False})
                    continue
                rows.append({
                    "geometry": geometry, "n": n, "density": d,
                    "connected": c["connected"], "graphs": c["graphs"], "acceptance_rate": c["acceptance_rate"],
                    "wilson_low": c["acceptance_wilson_low"], "wilson_high": c["acceptance_wilson_high"],
                    "clustering_share": c["clustering_share"]["median"],
                    "avg_degree": c["mean_degree"]["median"], "median_degree": c["median_degree"]["median"],
                    "min_degree": c["min_degree"]["median"], "max_degree": c["max_degree"]["median"],
                    "G1": c["connected"] >= g1_min,
                })

    g2 = g["G2_clustering_identity"]
    g3 = g["G3_degree_regime"]
    g2_rows, g3_rows = [], []
    for d in prim["densities"]:
        ratios = {}
        for n in prim["sizes"]:
            cl = cells.get(("clustered", int(n), float(d)))
            un = cells.get(("uniform", int(n), float(d)))
            if cl is None or un is None:
                g2_rows.append({"n": n, "density": d, "pass": False, "reason": "missing cell"})
                continue
            med_ratio = cl["clustering_share"]["median"] / un["clustering_share"]["median"]
            separated = cl["clustering_share"]["q1"] > un["clustering_share"]["q3"]
            g2_rows.append({"n": n, "density": d, "median_ratio": med_ratio, "d3_q1": cl["clustering_share"]["q1"],
                            "uniform_q3": un["clustering_share"]["q3"], "separated": separated,
                            "pass": med_ratio >= g2["min_median_ratio"] and separated})
            ratios[n] = cl["mean_degree"]["median"] / un["mean_degree"]["median"]
        spread = (max(ratios.values()) / min(ratios.values())) if ratios else float("inf")
        for n, r in ratios.items():
            g3_rows.append({"n": n, "density": d, "R": r, "R_ok": r <= g3["max_ratio"]})
        g3_rows.append({"density": d, "spread": spread, "spread_ok": spread <= g3["max_ratio_spread"]})

    sparse = []
    s_min = g["sparse_admission"]["min_connected"]
    for c in calibration["cells"]:
        if float(c["density"]) == 5.0:
            sparse.append({"geometry": c["geometry"], "n": c["n"], "connected": c["connected"],
                           "graphs": c["graphs"], "admitted": c["connected"] >= s_min})

    g1_pass = all(r["G1"] for r in rows)
    g2_pass = all(r["pass"] for r in g2_rows)
    g3_pass = all(r.get("R_ok", True) and r.get("spread_ok", True) for r in g3_rows)
    return {"rows": rows, "g2": g2_rows, "g3": g3_rows, "sparse": sparse,
            "G1_pass": g1_pass, "G2_pass": g2_pass, "G3_pass": g3_pass,
            "freeze": g1_pass and g2_pass and g3_pass}


def _print(res: dict) -> None:
    print("geometry        n      dens  accept (Wilson 95%)        clust  avg_deg  med_deg  min_deg  max_deg  G1")
    for r in res["rows"]:
        if r.get("missing"):
            print(f"{r['geometry']:15} {r['n']:<6} {r['density']:<5} MISSING")
            continue
        print(f"{r['geometry']:15} {r['n']:<6} {r['density']:<5} {r['connected']:2d}/{r['graphs']} "
              f"{r['acceptance_rate']:.2f} ({r['wilson_low']:.2f}-{r['wilson_high']:.2f})  "
              f"{r['clustering_share']:.3f}  {r['avg_degree']:7.1f}  {r['median_degree']:7.1f}  "
              f"{r['min_degree']:7.1f}  {r['max_degree']:7.1f}  {'PASS' if r['G1'] else 'FAIL'}")
    print("\nG2 clustering identity (D3 vs uniform):")
    for r in res["g2"]:
        if "median_ratio" in r:
            print(f"  n={r['n']:<6} d={r['density']:<5} median ratio {r['median_ratio']:.2f}  "
                  f"D3 Q1 {r['d3_q1']:.3f} vs uniform Q3 {r['uniform_q3']:.3f}  {'PASS' if r['pass'] else 'FAIL'}")
        else:
            print(f"  n={r['n']} d={r['density']} FAIL ({r['reason']})")
    print("\nG3 degree regime (R = D3 mean degree / uniform mean degree):")
    for r in res["g3"]:
        if "R" in r:
            print(f"  n={r['n']:<6} d={r['density']:<5} R = {r['R']:.2f}  {'ok' if r['R_ok'] else 'FAIL (> 4)'}")
        else:
            print(f"  density {r['density']}: max R / min R = {r['spread']:.2f}  {'ok' if r['spread_ok'] else 'FAIL (> 2)'}")
    print("\nSparse density-5 admission (>= 18/24):")
    for r in res["sparse"]:
        print(f"  {r['geometry']:15} n={r['n']:<6} {r['connected']:2d}/{r['graphs']}  "
              f"{'ADMIT' if r['admitted'] else 'exclude'}")
    print(f"\nG1 {'PASS' if res['G1_pass'] else 'FAIL'}  G2 {'PASS' if res['G2_pass'] else 'FAIL'}  "
          f"G3 {'PASS' if res['G3_pass'] else 'FAIL'}  ->  "
          f"{'D3 parameters accepted and frozen' if res['freeze'] else 'D3 needs a preregistered redesign'}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--calibration", required=True)
    ap.add_argument("--gates", required=True)
    ap.add_argument("--json", default=None, help="also write the evaluation as JSON")
    args = ap.parse_args(argv)
    res = evaluate(json.loads(Path(args.calibration).read_text(encoding="utf-8")),
                   json.loads(Path(args.gates).read_text(encoding="utf-8")))
    _print(res)
    if args.json:
        Path(args.json).write_text(json.dumps(res, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
