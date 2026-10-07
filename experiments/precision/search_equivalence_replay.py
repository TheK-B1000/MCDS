"""Replay every precision-pilot graph through the v1.1 bench and compare each
algorithm's CDS with the selected_ids recorded by the frozen v1.0 build."""
import glob
import json
import os
import subprocess
import sys
import time

ROOT = r"B:\repo\MCDS"
PILOT = os.path.join(ROOT, "results", "studies", "precision_pilot")
BENCH = os.path.join(ROOT, "cpp", "build-msvc", "Release", "mcds_bench.exe")
OUT = os.path.join(os.path.dirname(__file__), "replay")
os.makedirs(OUT, exist_ok=True)

files = sorted(glob.glob(os.path.join(PILOT, "graphs", "*", "timing__cgal.json")))
same = diff = 0
mismatches = []
t_old = {}
t_new = {}
start = time.time()
for k, f in enumerate(files):
    old = json.load(open(f))
    csv_path = old["input"]["path"]
    if not os.path.isabs(csv_path):
        csv_path = os.path.join(ROOT, csv_path)
    n = old["input"]["n"]
    out = os.path.join(OUT, f"{k}.json")
    subprocess.run([BENCH, "--input", csv_path, "--output", out, "--radius", "1.0",
                    "--algorithms", "marathe,wan,funke,li", "--repetitions", "1", "--warmups", "0",
                    "--validate", "all", "--emit-solution", "--spatial-backend", "cgal"],
                   check=True, capture_output=True)
    new = json.load(open(out))
    old_sel = {r["algorithm"]: r["selected_ids"] for r in old["runs"] if "selected_ids" in r}
    for r in new["runs"]:
        a = r["algorithm"]
        assert r["valid_solution"], (f, a)
        if r["selected_ids"] == old_sel[a]:
            same += 1
        else:
            diff += 1
            mismatches.append((f, a))
        t_new.setdefault((a, n), []).append(r["t_algorithm_ms"])
    for r in old["runs"]:
        if r["phase"] == "timed":
            t_old.setdefault((r["algorithm"], n), []).append(r["t_algorithm_ms"])
    os.remove(out)
    if (k + 1) % 156 == 0:
        print(f"{k + 1}/{len(files)} graphs, identical {same}, different {diff}, {time.time() - start:.0f}s", flush=True)

print(f"DONE graphs {len(files)} comparisons {same + diff} identical {same} different {diff}")
for m in mismatches[:20]:
    print("MISMATCH", m)
import statistics as st
print("median t_algorithm_ms (v1.0 pilot, quiet machine) vs (v1.1 replay, NOT a controlled timing):")
for (a, n) in sorted(t_new):
    print(f"  {a:8} n={n:6} v1.0 {st.median(t_old[(a, n)]):9.2f}  v1.1 {st.median(t_new[(a, n)]):9.2f}")
sys.exit(1 if diff else 0)
