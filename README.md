# MCDS on Implicit Unit Disk Graphs

An experimental-algorithms project comparing heuristics for the **Minimum
Connected Dominating Set** problem on **Unit Disk Graphs**, with the constraint
that the graph is never built.

**Status: Milestone 1, phases 1-3 complete.** Point loading, the spatial-query
layer, and its verification against brute force are done and tested. No MCDS
algorithm is implemented yet. See [Current status](#current-status) for the
detail.

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
uniform grid  (today)  /  CGAL range search  (a possible second backend)
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
datasets/             generated CSVs (gitignored; reproducible from the CLI)
results/              run outputs (gitignored)
```

`BruteForce.hpp` deliberately lives under `cpp/tests/`, which is on the include
path of the test targets only. Production code physically cannot include it.

---

## Building

Requires a C++17 compiler and CMake 3.16+. **No third-party library is needed.**

```bash
cmake -S cpp -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --parallel
```

Verified with GCC 15.2 and MSVC 19.44, both warning-free at `-Wall -Wextra
-Wpedantic` / `/W4`.

On Windows without CMake on `PATH`, the copy bundled with Visual Studio Build
Tools works:

```powershell
$cmake = "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe"
& $cmake -S cpp -B build -G "MinGW Makefiles" -DCMAKE_BUILD_TYPE=Release
& $cmake --build build --parallel
```

### On CGAL

The project brief suggests CGAL for spatial searching. **CGAL is not used yet,
and is not currently a dependency**, for two reasons: it is not installed in
this development environment (nor is Boost, which it needs), and a uniform grid
is both simpler to explain and asymptotically appropriate for fixed-radius
queries on bounded-density point sets. Because algorithms only ever see the
`SpatialIndex` interface, a `CgalSpatialIndex` can be added later as a second
backend and compared against the grid on identical datasets without touching a
line of algorithm code — which makes backend choice an experimental variable
rather than an architectural commitment.

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
| `clustered` | Gaussian blobs | dense cliques, weak or absent links between them |
| `perturbed_grid` | jittered lattice | very regular, reliably connected; easiest case |
| `corridor` | long narrow strip | forces the CDS into a long path, near worst-case size |
| `cluster_bridge` | blobs joined by thin chains | a correct CDS must include the bridges; coverage-only greed may miss them |

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
    --no-show --show-cds-edges
```

### GUI

```bash
python python/gui.py
```

### Experiments

```bash
python python/experiment_runner.py --config experiments/smoke.json
python python/experiment_runner.py --config experiments/smoke.json --summary
python python/plots.py --experiments-csv results/experiments.csv --save-dir results/plots
```

Datasets are generated **once** per `(distribution, n, seed, params)` key and
reused across algorithms. With `require_connected`, the runner retries
`effective_seed = base_seed + attempt` up to a configured limit and records
failures instead of dropping them.

Peak memory is measured on the **C++ child process** (Windows: peak working
set via `GetProcessMemoryInfo`; POSIX: `RUSAGE_CHILDREN` max RSS).

---

## Running tests

```bash
ctest --test-dir cpp/build --output-on-failure
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

### Experiment laboratory

```bash
# Preview size (no execution)
py -3 python/run_study.py --config experiments/pilot.json --dry-run

# Full study with progress bar, resume, plots, summary
py -3 python/run_study.py --config experiments/smoke.json

# Resume after Ctrl+C: run the same command again
```

Permanent demo dataset: `datasets/demo/cluster_bridge_300.csv`.

Recommended sequence: smoke → correctness → pilot → density → geometry →
scaling → final (do not launch final until pilot looks sane).

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
- [x] Unified CLI with staged timing and JSON results
- [x] Python visualization (CDS highlight, optional CDS edges, PNG export)
- [x] Tkinter GUI orchestration layer
- [x] Experiment runner with connected-input retries, resume, peak memory
- [x] Basic experimental plots across distributions

Not started (next milestones):

- [ ] Larger scaling campaign
- [ ] Additional algorithms (Wan, Funke, Li) — source-first, after this baseline stays green
