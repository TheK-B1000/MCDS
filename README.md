# MCDS on Implicit Unit Disk Graphs

An experimental-algorithms project comparing heuristics for the **Minimum
Connected Dominating Set** problem on **Unit Disk Graphs**, with the constraint
that the graph is never built.

**Status: implementation complete.** Point generation, the implicit spatial-query
layer, four MCDS heuristics, visualization, GUI, and the experiment pipeline are
in place. Remaining work is collecting experimental data. See
[Current status](#current-status) for the detail.

---

## The problem in one page

A **dominating set** of a graph is a subset `D` of the vertices such that every
vertex is either in `D` or adjacent to something in `D`. A **connected
dominating set** additionally requires that `D` induces a connected subgraph.
The minimum such set (MCDS) is the smallest one. Finding it is NP-hard, so this
project compares heuristics.

A **Unit Disk Graph (UDG)** is a graph defined by geometry rather than by a list
of edges. The vertices are points in the plane, and two vertices are adjacent
exactly when their Euclidean distance is at most a fixed radius `R`. This
project uses `R = 1.0`. The name comes from picturing a disk of radius `R/2`
around each point: two vertices are adjacent when their disks touch.

The motivation is wireless networking: transceivers with equal broadcast range
form a UDG, and a connected dominating set is a **virtual backbone**, a small
set of nodes that can reach everyone and can talk among themselves.

### Why the full graph is never stored

A UDG on `n` points is completely determined by the `n` points. Materialising
its edges throws away that structure and pays dearly for it:

* An `n x n` adjacency matrix on one million points is `10^12` entries. Even at
  one bit each that is 125 GB.
* An adjacency list is proportional to the edge count, and the edge count of a
  UDG is not bounded by `n`. A cluster of 10,000 mutually-reachable points is a
  clique with 50 million edges. Density is a free parameter in these
  experiments, so edge count is exactly the thing that blows up.

The geometry is `2n` doubles regardless. So this project keeps the points and
recovers adjacency on demand:

```
neighbors(p, radius = 1.0)
```

Measured on this machine: **1,000,000 uniform points, 3.13 million implied UDG
edges, 38.5 MB peak process memory**, with all one million radius queries
answered in 869 ms.

The research question is what this costs and what it buys:

> How do different MCDS algorithms compare in solution quality, runtime, memory,
> scalability, and geometric-query cost when the UDG is represented implicitly
> by points rather than explicitly by stored edges?

---

## How neighbor queries work

Everything funnels through one abstract class, `SpatialIndex`:

```
MCDS algorithm
      |
      v
SpatialIndex          <-- the only adjacency API that exists
      |
      v
CGAL kd-tree (primary)  /  uniform grid (independent secondary)
```

An algorithm asks for `index.radiusQuery(pointId, 1.0)` and receives the ids of
the neighbors. It cannot see cells, coordinates, or any library underneath.
Replacing the backend requires no algorithm changes.

### The query contract

`radiusQuery(pointId, radius)` returns the ids of all points `q` with
`distance(p, q) <= radius`, where:

* **The query point is excluded.** Graph algorithms want the open neighborhood
  `N(p)`. A caller that needs the closed neighborhood `N[p]` adds `p` itself,
  which is cheaper and harder to get wrong than making every caller remember to
  filter `p` out.
* **The boundary is inclusive.** A point at distance exactly `radius` is a
  neighbor. For `R = 1.0` the test is the exact comparison
  `distanceSquared <= 1.0`, so no `sqrt` is involved and no tolerance is
  invented. Given `A=(0,0)`, `B=(0.5,0)`, `C=(1,0)`, `D=(1.01,0)`, the neighbors
  of `A` are exactly `B` and `C`.
* **Coincident points are neighbors.** Only `p` itself is filtered, not
  everything at distance zero. Two points sharing coordinates are adjacent.
* **Order is unspecified.** Callers that need a specific order must sort.

### The uniform-grid backend

Points are bucketed into square cells of side equal to the query radius, so a
query only scans the 3x3 block of cells around the query point. Buckets are held
in CSR form: one offset array plus one array of point indices grouped by cell.
Storage is `4n + 4 * cells` bytes and is **independent of the edge count** —
that dense 10,000-point clique still occupies only its 10,000 slots.

Cells are enlarged when a bounding box would demand too many of them. Without
that guard, two points ten million units apart would ask for `10^14` cells.
Doubling the cell size instead keeps index memory `O(n)` and stays exactly
correct, at the cost of scanning more points per query in dense regions.

### Instrumentation

The index counts, per run:

| Counter | Meaning |
| --- | --- |
| `neighborQueries` | calls to `radiusQuery` |
| `candidatesExamined` | points whose distance was actually computed, i.e. everything in a scanned cell |
| `neighborsReturned` | neighbors handed back, summed over all queries |

`candidatesExamined / neighborsReturned` is the index's waste factor and comes
out near 3.0 on uniform input. These counters are the experimental payload:
because no graph exists, the price an algorithm pays for adjacency information
is exactly what is recorded here.

---

## Repository layout

```
cpp/
  include/            Point, PointSet, SpatialIndex, GridSpatialIndex, Metrics, CsvIO
  src/                implementations + the CLI driver
  tests/              test harness, brute-force reference, test suites
python/
  generators.py       five point distributions, deterministic per seed
  import_dataset.py   real-world CSV / GeoJSON → canonical PointSet CSV
  real_dataset.py     projection, sampling, metadata, LCC / tiles helpers
  prepare_real_dataset.py  explicit LCC, nested prefixes, rectangular tiles
  run_study.py        the experiment runner (package study/)
  study/              config, seeds, schedule, datasets, runner, fairness,
                      analysis, figures, manifest
datasets/             generated / imported CSVs (gitignored; demo + real/ kept)
results/              run outputs (gitignored)
experiments/          study configurations
docs/                 methodology, protocol, audits, algorithms/, real_world_data.md
```

`BruteForce.hpp` deliberately lives under `cpp/tests/`, which is on the include
path of the test targets only. Production code physically cannot include it.

---

## Building

Requires a C++17 compiler, CMake 3.16+ and **CGAL ≥ 6.0** (header-only, with
Boost headers). CGAL is the primary spatial backend of the final study, so a
default configure **fails** if CGAL is not found. Verified setup (Windows,
MSVC 19.44, Visual Studio 2022 generator):

```powershell
conda create -n mcds-cgal -c conda-forge cgal-cpp=6.1.2 libboost-headers=1.88
$cmake = "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe"
& $cmake -S cpp -B cpp/build-msvc -DCMAKE_PREFIX_PATH="$env:USERPROFILE/miniconda3/envs/mcds-cgal/Library"
& $cmake --build cpp/build-msvc --config Release --parallel
```

(conda 24.7 on this machine could not solve CGAL 6.2.x because of a `__win`
virtual-package check; 6.1.2 with Boost 1.88 solves cleanly.)

A grid-only development build is possible only on explicit request:
`-DMCDS_WITH_CGAL=OFF`. Such a binary refuses `--spatial-backend cgal` — there
is never a silent fallback.

Compiled at `-Wall -Wextra -Wpedantic` / `/W4`; MSVC reports C4244
conversion warnings from standard-library instantiations in `mcds_core`.

Targets: `mcds` (interactive CLI used by the GUI), `mcds_bench` (experiment
measurement driver), `mcds_bench_mem` (memory probes), and the test suites
(including `test_spatial_backends`, the CGAL / grid / brute-force
differential suite).

### Hard invariant

The input is a set of n points and the unit disk graph is **never constructed
or stored explicitly** anywhere (algorithms, preprocessing, validation, CDS
diameter, exact OPT, studies); neighbours are queried on demand. Enforced by
`python/tests/test_implicit_graph_guard.py` (on a 2.78 M-edge graph the whole
solver process peaks below 0.6 MB, versus 22 MB for an explicit CSR).

### Spatial backends

All algorithms see only the `SpatialIndex` interface.

* **CGAL (primary):** `CGAL::Kd_tree` + `CGAL::Fuzzy_sphere` radial search (dD Spatial
  Searching) retrieve candidates; adjacency is decided by the same exact
  predicate `distanceSquared(p, q) <= r²` as every other backend.
* **Uniform grid (secondary):** independent implementation; reference for
  validation, CDS diameter and a full per-graph neighbour cross-check.
* **Brute force:** correctness oracle in tests.

CGAL = grid = brute force on 258,886 differential neighbour queries, and all
four algorithms return identical CDSs through CGAL and the grid. Details:
[docs/experimental_methodology.md](docs/experimental_methodology.md) §3.

---

## Generating datasets

`python/generators.py` needs only the standard library. Output is deterministic:
a given `(type, n, seed, parameters)` always produces a byte-identical file,
which is what makes cross-algorithm comparison meaningful.

```bash
python python/generators.py --type uniform --n 1000 --seed 42 \
    --output datasets/uniform_1000.csv
```

| `--type` | Shape | Why it is interesting |
| --- | --- | --- |
| `uniform` | uniform over a square | the baseline case |
| `clustered` | 4 Gaussian hotspots holding 50% of the points on a 50% uniform background; studies use D3-v2 (`--spread-relative 0.05`: σ = 0.05 · window side, hotspots kept inside the window) | dense hotspots in a sparse but connectable field (hotspot-plus-background model) |
| `perturbed_grid` | jittered lattice | very regular, reliably connected; easiest case |
| `corridor` | long narrow strip | forces the CDS into a long path, near worst-case size |
| `dumbbell` | two squares joined by a narrow neck (`--neck-width 1 --neck-length 3`), area n / density | a controlled bottleneck: every connected dominating set must cross the neck |
| `cluster_bridge` | blobs joined by thin chains (legacy v1; not used by the study configs) | a correct CDS must include the bridges; coverage-only greed may miss them |

`--density` (points per unit area) is the main knob: the expected degree of an
interior point is about `density * pi * R^2`, so density controls how dense the
implicit graph is independently of `n`. The default of `2.0` gives a mean degree
near 6.3.

CSV format, shared by every part of the project:

```csv
id,x,y
0,1.250000,4.700000
1,1.800000,4.320000
```

The loader also accepts a missing header, blank lines, `#` comments, CRLF
endings, and padded fields. It rejects, naming the offending line, a wrong field
count, a non-numeric field, a non-finite coordinate, a negative id, a duplicate
id, and a file with no points.

---

## Running

```bash
# Generate a connected instance
python python/generators.py --type perturbed_grid --n 200 --seed 42 \
    --output datasets/e2e_grid_200.csv

# Check connectivity without running an algorithm
./build/mcds --input datasets/e2e_grid_200.csv --check-connectivity

# Run Marathe CDOM and write JSON
./build/mcds \
    --input datasets/e2e_grid_200.csv \
    --algorithm marathe \
    --radius 1.0 \
    --output results/e2e_grid_200.json \
    --pretty
```

The JSON result separates timing and neighbour-query counters by stage
(`load_ms`, `index_build_ms`, `connectivity_ms`, `algorithm_ms`,
`validation_ms`) so algorithm cost is not confused with I/O or validation.

### Visualize

```bash
python python/visualization.py \
    --points datasets/e2e_bridge_300.csv \
    --result results/e2e_bridge_300.json \
    --save results/e2e_bridge_300.png \
    --no-show
```

GUI color modes (visualization only; algorithms unchanged):

- **Final CDS** — ordinary points vs selected CDS nodes (default).
- **Algorithm roles** — when the result JSON includes optional `roles`,
  distinguishes core vs connector selected vertices. For Li S-MIS:
  black/MIS = core, blue/Steiner = connector, grey = ordinary.
  If roles are missing, the plot falls back to a single selected color.

### GUI

```bash
python python/gui.py
```

### Experiments

One runner, `python/run_study.py`, drives every study (synthetic and real).
See [docs/experimental_methodology.md](docs/experimental_methodology.md).

```bash
py -3 python/run_study.py plan      --config experiments/pilot.json   # design only, runs nothing
py -3 python/run_study.py reproduce --config experiments/smoke.json   # run + analyze + figures + manifest
```

`reproduce` is resumable (re-run the same command after Ctrl+C) and exits
non-zero if the automatic fairness check fails. Outputs land in
`results/studies/<study_id>/`: `raw_runs.csv` (one row per algorithm
execution), `datasets.csv`, `generation_attempts.csv`, `failures.csv`,
`summary.csv`, `paired.csv`, `validity.csv`, `figures/`,
`environment.json`, `methodology_manifest.json`.

Configs in `experiments/`: `smoke`, `pilot`, `precision_pilot` (replicate
count), `exact_small` (|D|/OPT for n ≤ 16), `spatial_backend` (optional
CGAL-vs-grid sensitivity), `representation_ablation` (optional implicit memory vs
count-only explicit-size estimate; no graph is built), `real_world_scaling` (template), `final` (primary study;
CGAL only; reopened after the pre-final audit, replicate count pending the precision-pilot re-run; final tag `v1.0-final-experiment` once locked). Every config states its `spatial_backend`.

### Real-world / external datasets

Synthetic studies and imported real datasets share the same canonical CSV and
solver path. See [docs/real_world_data.md](docs/real_world_data.md).

```bash
# Import planar CSV
py -3 python/import_dataset.py \
    --type csv \
    --input data/raw/points.csv \
    --x-column x \
    --y-column y \
    --coordinates planar \
    --output datasets/real/points.csv

# Import geographic CSV (projects lon/lat → meters)
py -3 python/import_dataset.py \
    --type csv \
    --input data/raw/locations.csv \
    --x-column longitude \
    --y-column latitude \
    --coordinates geographic \
    --output datasets/real/locations_projected.csv

# Import building GeoJSON
py -3 python/import_dataset.py \
    --type geojson \
    --input data/raw/buildings.geojson \
    --feature-point centroid \
    --coordinates geographic \
    --limit 1000000 \
    --output datasets/real/buildings_1m.csv

# Preview a real-data study (replace placeholder paths first)
py -3 python/run_study.py plan --config experiments/real_world_scaling.json
```

Each graph is generated or loaded **once**; all four algorithms run on the same
in-memory point set inside one `mcds_bench` process, and the solver's points
fingerprint is checked against Python's. Graph seeds are SHA-256-derived from
every factor, so replicates never share a dataset; every connectivity
resampling attempt is logged. Real datasets declare their own radius (or radius
sweep) and are never resampled or silently repaired.

Memory: per-algorithm heap peak from a separate heap-tracking probe binary
(`mcds_bench_mem`), never mixed with timing runs.

---

## Running tests

```bash
ctest --test-dir cpp/build --output-on-failure            # single-config generators
ctest --test-dir cpp/build-msvc -C Release                # Visual Studio generator
```

### Python environment (required for plots / GUI / visualization / studies)

Use **one** CPython interpreter (3.10+) for all Python work. On Windows, prefer
the `py -3` launcher (or a venv) over MSYS Python:

```bash
py -3 -m pip install -r python/requirements.txt
py -3 python/check_env.py
py -3 -m unittest discover -s python/tests -v
```

`python/check_env.py` verifies `matplotlib` and `tqdm`.

### Study workflow

Permanent demo dataset: `datasets/demo/cluster_bridge_300.csv`.

Recommended sequence: smoke → precision_pilot → exact_small → (optional
studies, real data) → lock protocol → final.
Do not launch `final` until the protocol in
[docs/final_experiment_protocol.md](docs/final_experiment_protocol.md) is
approved; `final: true` refuses a dirty git tree or a non-Release build.

---

## Methodology status

v1 methodology is under development; final data collection has not started.
It will be locked with a git tag (e.g. `v1.0-final-experiment`) and the
generated `methodology_manifest.json`. The older tag `v1.0-experiments` is a
snapshot of the pre-upgrade pipeline only.

- Paper verification: [docs/source_audit.md](docs/source_audit.md) and
  [docs/algorithms/](docs/algorithms/)
- Methodology: [docs/experimental_methodology.md](docs/experimental_methodology.md)
- Audit trail: [docs/methodology_audit.md](docs/methodology_audit.md)
- Pre-registration draft: [docs/final_experiment_protocol.md](docs/final_experiment_protocol.md)

---

## Design decisions

**Ids versus indices.** Two addressing schemes coexist. An *index* in
`[0, n)` is the position in input order and is what internal structures use; an
*id* is the value from the CSV and is what the query API and output speak in, so
results can be sent back to Python unchanged. When ids happen to be `0..n-1` in
order — true for every generator here — the two coincide and `PointSet` skips
its lookup table entirely, which keeps the large-`n` case free of a per-point
hash map.

**Squared distances everywhere.** `sqrt` never appears on a query path.
Comparing `distanceSquared <= radius * radius` is faster and, for `R = 1.0`,
exact.

**The virtual is protected, not public.** `SpatialIndex::radiusQuery` is a
non-virtual public overload pair forwarding to a protected virtual
`radiusQueryImpl`. Had backends overridden `radiusQuery` directly, the derived
declaration would hide the two-argument convenience overload for any caller
holding a derived-class reference. This was not hypothetical — it broke the
first build. Splitting the virtual out means the public API is identical no
matter which backend is in use, and the `out.clear()` guarantee lives in one
place.

**The index borrows the point set.** `GridSpatialIndex` holds a pointer to the
`PointSet` rather than a copy, so coordinates are stored exactly once. The
point set must outlive the index.

---

## Current status

Done and tested through visualization, GUI, and the smoke experiment pipeline:

- [x] Deterministic Python point generation (five distributions)
- [x] C++ CSV loading + spatial index + brute-force differential tests
- [x] Implicit connectivity / connected components
- [x] Independent CDS validator (domination + selected-only connectivity)
- [x] Marathe CDOM documented from arXiv:math/9409226 and implemented
- [x] Wan–Alzoubi–Frieder documented and implemented
- [x] Funke–Kesselman–Meyer–Segal documented and implemented
- [x] Li–Thai–Wang–Yi–Wan–Du S-MIS documented and implemented
- [x] Unified CLI with staged timing and JSON results
- [x] Python visualization (CDS highlight, optional CDS edges, PNG export)
- [x] Tkinter GUI orchestration layer
- [x] Experiment runner: shared in-memory graph per process, balanced
      execution order, raw per-repetition rows, fairness checker, resume
- [x] Graph statistics, spatial-work counters, per-algorithm heap probes
- [x] Statistical summaries (bootstrap / Wilson CIs, paired comparisons) and figures
- [x] Primary-paper audits for all four algorithms; Wan §VI.A pruning implemented
- [x] CGAL primary spatial backend with differential validation against grid and brute force
- [x] CDS diameter, exact-OPT in its own process, precision-pilot analysis, representation ablation
- [x] Real-world dataset import (CSV / GeoJSON / lat-lon projection) and external study mode

Remaining:

- [ ] Choose the replicate count from the precision pilot; review final cells;
      lock the v1 methodology (tag + manifest)
- [ ] Collect final data (pilot → exact_small → final; optional real-world study)
