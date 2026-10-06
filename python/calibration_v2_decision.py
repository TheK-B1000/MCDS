"""Mechanical decision for generator_definitions_v2 (locked rules only).

    py -3 python/calibration_v2_decision.py

Reads the three v2 calibration files, the locked gates (gates_v1.json), the
locked requirements (primary_geometry_requirements_v1.json) and definitions
(generator_definitions_v2.json), and reports for every candidate:

* the per-cell table (acceptance, clustering share, avg/median/min/max degree),
* G1 (>= 18/24 connected), G2/G3 (clustered vs uniform), R1 (density
  response), R2 (scale stability), R3 (dumbbell bottleneck character),
* the locked D3 selection and the dumbbell pass / stress-test-fallback verdict,
* sparse density-5 admission under the same 18/24 rule.

No threshold here is chosen after seeing results: every number is read from
the locked JSON files.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_PY = Path(__file__).resolve().parent
_ROOT = _PY.parent
if str(_PY) not in sys.path:
    sys.path.insert(0, str(_PY))

from calibration_gates import evaluate  # noqa: E402

CAL = _ROOT / "experiments" / "calibration"
SIZES = (500, 1000, 2000, 5000, 10000)
PRIMARY_DENSITIES = (8.0, 12.0)


def load(name: str) -> dict:
    return json.loads((CAL / name).read_text(encoding="utf-8"))


def cells_of(doc: dict, geometry: str) -> dict:
    return {(int(c["n"]), float(c["density"])): c for c in doc["cells"] if c["geometry"] == geometry}


def requirements(cells: dict, req: dict, geometry: str, neck: tuple[float, float] | None = None) -> dict:
    r1 = req["requirements"]["R1_density_response"]["min_ratio"]
    r2 = req["requirements"]["R2_scale_stability"]["max_spread"]
    out = {"R1": [], "R2": [], "R3": None}
    for n in SIZES:
        a, b = cells.get((n, 12.0)), cells.get((n, 8.0))
        if a and b:
            ratio = a["mean_degree"]["median"] / b["mean_degree"]["median"]
            out["R1"].append((n, ratio, ratio >= r1))
    for d in PRIMARY_DENSITIES:
        degs = [cells[(n, d)]["mean_degree"]["median"] for n in SIZES if (n, d) in cells]
        spread = max(degs) / min(degs)
        out["R2"].append((d, spread, spread <= r2))
    if neck is not None:
        w, length = neck
        r3 = req["requirements"]["R3_bottleneck_character"]
        worst_share = max(w * length * d / n for n in SIZES for d in PRIMARY_DENSITIES)
        out["R3"] = (w, worst_share, w <= r3["max_corridor_width"] and worst_share < r3["max_corridor_point_share"])
    out["pass"] = (all(x[2] for x in out["R1"]) and all(x[2] for x in out["R2"])
                   and (out["R3"] is None or out["R3"][2]))
    return out


def table(cells: dict, geometry: str) -> None:
    for n in SIZES:
        for d in (5.0, 8.0, 12.0):
            c = cells.get((n, d))
            if not c:
                continue
            print(f"  {geometry:10} n={n:<6} d={d:<5} {c['connected']:2d}/{c['graphs']} "
                  f"({c['acceptance_wilson_low']:.2f}-{c['acceptance_wilson_high']:.2f})  "
                  f"clust {c['clustering_share']['median']:.3f}  deg avg {c['mean_degree']['median']:6.1f} "
                  f"med {c['median_degree']['median']:6.1f} min {c['min_degree']['median']:5.1f} "
                  f"max {c['max_degree']['median']:6.1f}{'  [sparse]' if d == 5.0 else ''}")


def main() -> int:
    gates = load("gates_v1.json")
    req = load("primary_geometry_requirements_v1.json")
    defs = load("generator_definitions_v2.json")
    base = load("generator_calibration_v2_cal_v2_uniform_dumbbell_s0025.json")
    files = {0.025: base, 0.035: load("generator_calibration_v2_cal_v2_s0035.json"),
             0.05: load("generator_calibration_v2_cal_v2_s005.json")}
    uniform = [c for c in base["cells"] if c["geometry"] == "uniform"]
    g1 = gates["gates"]["G1_connectivity"]["min_connected"]

    print("== Reference: uniform (same new seeds)")
    table(cells_of(base, "uniform"), "uniform")
    print("   requirements:", requirements(cells_of(base, "uniform"), req, "uniform"))

    print("\n== D3 v2 ladder")
    passing = []
    for s, doc in files.items():
        cl = [c for c in doc["cells"] if c["geometry"] == "clustered"]
        g = dict(gates)
        g["primary_cells"] = {"geometries": ["uniform", "clustered"], "sizes": list(SIZES),
                              "densities": list(PRIMARY_DENSITIES)}
        res = evaluate({"cells": uniform + cl}, g)
        reqs = requirements(cells_of(doc, "clustered"), req, "clustered")
        g1_ok = all(r["G1"] for r in res["rows"] if r["geometry"] == "clustered")
        min_g2 = min(r["median_ratio"] for r in res["g2"] if "median_ratio" in r)
        ok = g1_ok and res["G2_pass"] and res["G3_pass"] and reqs["pass"]
        print(f"\n-- s = {s}: G1 {'PASS' if g1_ok else 'FAIL'}  G2 {'PASS' if res['G2_pass'] else 'FAIL'} "
              f"(min ratio {min_g2:.2f})  G3 {'PASS' if res['G3_pass'] else 'FAIL'}  "
              f"R1/R2 {'PASS' if reqs['pass'] else 'FAIL'}  ->  {'PASSES' if ok else 'fails'}")
        table(cells_of(doc, "clustered"), "clustered")
        for r in res["g3"]:
            if "R" in r:
                print(f"     G3 n={r['n']:<6} d={r['density']:<5} R={r['R']:.2f}")
            else:
                print(f"     G3 density {r['density']}: spread {r['spread']:.2f}")
        print(f"     R1 {[(n, round(x, 2)) for n, x, _ in reqs['R1']]}  R2 {[(d, round(x, 2)) for d, x, _ in reqs['R2']]}")
        if ok:
            passing.append((min_g2, s))
    chosen = max(passing)[1] if passing else None
    print(f"\nD3 selection (locked rule: highest minimum G2 ratio among passing): "
          f"{chosen if chosen is not None else 'NONE PASSES'}")

    print("\n== Dumbbell (one fixed calibration)")
    db = cells_of(base, "dumbbell")
    table(db, "dumbbell")
    fixed = defs["bottleneck_dumbbell_v2"]["fixed"]
    reqs = requirements(db, req, "dumbbell", neck=(fixed["neck_width"], fixed["neck_length"]))
    g1_ok = all(db[(n, d)]["connected"] >= g1 for n in SIZES for d in PRIMARY_DENSITIES)
    print(f"   G1 {'PASS' if g1_ok else 'FAIL'}  R1 {[(n, round(x, 2)) for n, x, _ in reqs['R1']]}  "
          f"R2 {[(d, round(x, 2)) for d, x, _ in reqs['R2']]}  R3 width {reqs['R3'][0]} worst share "
          f"{reqs['R3'][1]:.3f} -> {'PASS' if reqs['R3'][2] else 'FAIL'}")
    db_ok = g1_ok and reqs["pass"]
    print(f"   verdict: {'dumbbell replaces cluster_bridge in the primary factorial' if db_ok else 'FALLBACK: cluster_bridge becomes a separate bottleneck stress-test study'}")

    print("\n== Sparse density-5 admission (>= 18/24) for v2 geometries")
    for geometry, doc in [("uniform", base), ("dumbbell", base)] + (
            [("clustered", files[chosen])] if chosen is not None else []):
        for n in SIZES:
            c = cells_of(doc, geometry).get((n, 5.0))
            if c:
                print(f"   {geometry:10} n={n:<6} {c['connected']:2d}/24  {'ADMIT' if c['connected'] >= g1 else 'exclude'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
