# Experimental methodology

How the project measures the four MCDS algorithms. One experiment runner,
`python/run_study.py` (package `python/study/`), drives every study through
the C++ measurement driver `mcds_bench` (memory probes: `mcds_bench_mem`). It
changes no algorithm, generator, validator or spatial-index semantics; it
controls *how they are measured*.

This document describes the v1 methodology. It will be locked with the final
protocol (label and tag `v1.0-final-experiment`; it is currently `v1.0-dev`,
reopened after the pre-final audit; earlier pilot and calibration results carry
`v1-dev`). It is locked together with the final protocol
([final_experiment_protocol.md](final_experiment_protocol.md)). Audit trail:
[methodology_audit.md](methodology_audit.md). Paper verification:
[source_audit.md](source_audit.md).

## 0. Hard invariant: points in, graph never stored

The input is a set of n points (canonical `id,x,y`). The unit disk graph is
**never constructed or stored explicitly** — no adjacency lists, matrices,
edge lists or CSR — in any production or experimental path: generation,
preprocessing (including the real-data largest-component filter), graph
statistics, the four algorithms, validation, CDS diameter, exact OPT and every
study. Adjacency is only ever obtained on demand by radius queries:

```
n points ─► SpatialIndex (CGAL kd-tree / uniform grid: point-index structures, O(n))
         ─► neighbours queried only when needed ─► Marathe / Wan / Funke / Li
```

Enforced by `python/tests/test_implicit_graph_guard.py`:

* behavioural: the memory-probe solver runs every phase (graph statistics,
  cross-check, four algorithms, validation, CDS diameter) on a graph with
  2,779,178 edges whose explicit CSR would need 22.3 MB; its whole-process
  heap peak was 592 KB (CGAL) / 419 KB (grid) and must stay below 10% of the
  CSR size. The real-data largest-component filter (union-find over the grid
  scan, O(n)) is checked the same way with `tracemalloc`;
* static tripwire: no C++ or Python source in the repository — production,
  experiment tooling, visualisation/GUI, tests and test oracles — may contain
  adjacency-building or edge-drawing constructs (adjacency lists, neighbour
  maps, edge containers, CSR arrays, bit matrices, sparse/pair queries, graph
  libraries, segment drawing). Justified allowlist: Marathe's per-BFS-level
  vertex lists (O(n), no edges) and two negative assertions in the
  visualisation test. Verified to flag every pre-fix violation, including the
  removed `cds_edges` drawing and a test oracle that had stored Li's
  distance-2 graph H (now evaluated on demand).

There are no exceptions: the visualisation draws points only (the former
`--show-cds-edges` option, which drew segments between adjacent CDS vertices,
was removed with its `cds_edges` helper and GUI toggle), and the static
tripwire also covers the visualisation and GUI sources.

## 1. Scope and positioning

The study is a controlled empirical comparison of four established,
theory-lineage MCDS approximation algorithms — Marathe CDOM,
Wan–Alzoubi–Frieder, Funke–Kesselman–Meyer–Segal, and the S-MIS connector
phase with a centralized Wan-level MIS (Li et al.) — on **implicit** unit disk
graphs. Working statement (from `related_work_matrix.md`):

> We conduct a controlled empirical study of classical approximation
> heuristics for MCDS on implicit Unit Disk Graphs, evaluating solution
> quality and computational cost under matched spatial instances across graph
> size, density, and geometric structure.

None of the ingredients is claimed to be new on its own: MCDS experiments, UDG
experiments, implicit geometric adjacency, repeated random trials and exact
MCDS benchmarks all exist in the literature. The possible contribution is the
**combination**: faithful classic algorithms (audited against their primary
papers) on one common implicit spatial substrate; identical paired graph
instances; five spatial geometries with controlled density; runtime, memory
and neighbour-query instrumentation; exact OPT on small UDGs; real spatial
datasets; and a reproducible framework. No "first" claim is made until the
literature search in `related_work_matrix.md` is complete. No new algorithms
are added.

## 2. Pipeline

```
config (experiments/*.json) ─► plan: cells × replicates; seed = SHA-256 of every factor
        │
generators.py ─► CSV ─► SHA-256 + FNV points fingerprint (checked again inside the solver)
        │
mcds_bench --graph-only  (untimed probe: connectivity rule, graph statistics,
        │                 CGAL↔grid neighbour cross-check; EVERY attempt logged)
        ▼  accepted graph; Williams-design algorithm order, e.g. wan>li>marathe>funke
mcds_bench  (one process per graph and backend)
   load once ................................... T_dataset
   independent grid (reference) ................ T_validation_index
   selected backend (CGAL kd-tree) ............. T_spatial_index
   full neighbour cross-check vs grid .......... T_backend_crosscheck   (untimed for algorithms)
   graph statistics: degree pass, components ... T_degree_pass, T_connectivity
   warmup: A B C D;  timed 1..R: A B C D  ...... T_algorithm  ◄── solve() only
   after each execution: validation, CDS diameter (independent grid)
mcds_bench_mem  (one process per algorithm)  ── heap-tracked memory probes (never timed)
mcds_bench --instrumentation basic           ── untimed counter pass
mcds_bench --graph-only --exact-max-n K      ── exact OPT, own process + own timeout
        │
graphs/<graph_id>/*.json ──► raw_runs.csv, datasets.csv, generation_attempts.csv, failures.csv
        │
fairness check (fails the study on any violation)
        │
analysis: graph_level, summary, validity, paired, backend_paired, precision, precision_curve
figures/<backend>/   methodology_manifest.json
```

## 3. Spatial backends

All algorithms access adjacency only through the `SpatialIndex` interface;
none knows which backend is active.

| Backend | Role | Implementation |
| --- | --- | --- |
| `cgal` | **Primary** backend of the final study | `CgalSpatialIndex` |
| `grid` | Independent secondary backend; reference for validation and cross-checks; backend-sensitivity study | `GridSpatialIndex` (uniform grid, CSR buckets) |
| brute force | Correctness oracle in tests only (O(n²)) | `cpp/tests/BruteForce.hpp` |

**CGAL.** Package *dD Spatial Searching*, CGAL 6.1.2 (header-only; Boost 1.88
headers), installed from conda-forge (`cgal-cpp=6.1.2`). Data structure:
`CGAL::Kd_tree` over point indices via `CGAL::Search_traits_adapter` with a
`CGAL::Pointer_property_map` onto `CGAL::Search_traits_2<CGAL::Simple_cartesian<double>>`
(default `Sliding_midpoint` splitter, bucket size 10). The tree is built
eagerly (`Kd_tree::build()`) in the constructor, so construction lands in
`T_spatial_index` and never in the first algorithm's `T_algorithm`. Query:
CGAL **radial range search**, `Kd_tree::search(out, CGAL::Fuzzy_sphere(p, r', 0.0))`.

**CGAL is used for spatial candidate retrieval; final UDG adjacency is
determined by the same exact squared-distance predicate used by the grid and
brute-force reference implementations:**

```
q ∈ N(p)  ⇔  q ≠ p  and  distanceSquared(p, q) <= r * r
```

The search radius is `r' = r·(1 + 1e-9) + 8·ε·(|p.x| + |p.y| + r)`
(ε = machine epsilon). Why CGAL's sphere is not itself the adjacency test: in
the installed CGAL 6.1.2, `Fuzzy_sphere::contains()` is inclusive
(`distance <= r'²`) but `contains_point_given_as_coordinates()` is exclusive
(`distance < r'²`), and which one runs depends on the kd-tree's internal search
path — a point at exactly distance r would be reported or not depending on tree
layout. Why the widening cannot change the graph: the exact predicate accepts q
only if `dx² + dy² <= r²` in floating point; such a point's squared distance is
at most r² up to rounding, strictly below r'², so CGAL reports it on either
path. Widening can only add *false-positive candidates*, which the exact
predicate then rejects — never false-positive edges, and never a missed edge.
(The radial query replaced an equivalent axis-aligned `Fuzzy_iso_box` candidate
query before any reportable data was collected; a circle covers π/4 of the
box's area, so fewer candidates reach the exact test.)

**Shared contract (all backends):** query point excluded; distinct coincident
points included; boundary inclusive; no tolerance; result order unspecified;
point ids preserved (CGAL works on internal indices mapped back to ids).

**Index lifecycle (identical for every algorithm):** one index per graph per
process, built before any algorithm runs, reused read-only by all algorithms
in that process; counters are reset before each execution.

**No fallback.** CMake fails if CGAL is missing (unless a grid-only build is
requested explicitly with `-DMCDS_WITH_CGAL=OFF`); a grid-only binary exits
with an error when asked for `cgal`; the runner refuses a study that requests
`cgal` if the solver lacks CGAL; the runner rejects any bench output whose
reported backend differs from the requested one; a `final: true` config must
use `spatial_backend = "cgal"` only.

### Differential validation (evidence that the backends build the same UDG)

| Check | Scope | Result |
| --- | --- | --- |
| `test_spatial_backends`: CGAL = grid = brute force per query | 1,821 point sets, 258,886 neighbour queries: five geometries, sizes 1–600, densities 0.5–40, radii 0.5–3, offsets to ±1e7 and UTM scale, non-identity ids; plus boundary (exact R and one ulp beyond, all axes), coincident points (also r = 0), single/empty sets | 0 discrepancies |
| All four algorithms through CGAL vs grid | 839 connected graphs × 4 algorithms | identical selected sets, roles, validity, neighbour-query and neighbours-returned counts |
| Neighbour-order independence | 3 random shuffles of every query result, 4 algorithms | identical outputs (so backend query order cannot leak into tie-breaking) |
| Per-graph production cross-check | every graph of every study: all n neighbour sets, CGAL vs grid | must be `identical`, else the graph is not run (fairness V8) |
| Python end-to-end | CGAL vs grid study on generator output and a UTM-scale real fixture (r = 100 m) | identical CDS hashes and query counts per algorithm (fairness V9) |

## 4. Timing boundaries

| Stage | Where recorded | Notes |
| --- | --- | --- |
| T_dataset | `datasets.csv t_dataset_ms` | CSV load |
| T_spatial_index | `raw_runs.csv t_spatial_index_ms` | selected backend build (per process) |
| T_validation_index | bench JSON | independent grid build (0 when grid is the backend) |
| T_backend_crosscheck | bench JSON | untimed for algorithms |
| T_connectivity, degree pass | `datasets.csv t_connectivity_ms`, `t_graph_stats_ms` | |
| **T_algorithm** | `raw_runs.csv t_algorithm_ms` | **`solve()` only — primary runtime metric** |
| T_validation | `raw_runs.csv t_validation_ms` | per execution, after the timer |
| CDS diameter | bench JSON `t_cds_diameter_ms` | after the timer, once per distinct CDS |
| T_exact | `datasets.csv t_exact_ms` | separate process |
| T_output / T_total | bench `t_total_ms_before_output`; runner `wall_s` per step (`*.meta.json`) | process level; JSON writing is the remainder |

Clock: `std::chrono::steady_clock` (QPC on Windows; observed resolution
recorded). Warmups are logged as `phase = warmup` and never used in any
statistic. Repetitions are interleaved across algorithms (A B C D, A B C D…).

Execution order: a seeded **Williams design** (balanced Latin square). Each
algorithm occupies each position equally often and immediately follows each
other algorithm equally often; within a cell, replicate r uses row
(r − 1 + seeded cell offset) mod 4, so cells are exactly balanced when the
replicate count is a multiple of 4. Rows record `execution_order`,
`execution_position`, `schedule_row`; the fairness report tabulates balance.

## 5. Metric taxonomy

| Class | Metrics | Comparable across algorithms | Across backends |
| --- | --- | --- | --- |
| **Primary** | `valid_solution`, `t_algorithm_ms`, `cds_size`, `cds_fraction` | yes | — (primary study has one backend) |
| **Secondary** | `algorithm_incremental_peak_bytes`, `final_representation_bytes`, `index_build_peak_bytes`, `pipeline_peak_bytes`, `t_spatial_index_ms`, `neighbor_queries`, `neighbors_returned`, `cds_diameter`, `empirical_ratio` | yes | `neighbor_queries`, `neighbors_returned` are identical by construction |
| **Diagnostic** | `core_count`, `connector_count` (MIS/core vs connector), `domination_valid`, `connectivity_valid`, `undominated_count`, `max_neighbors_per_query`, `query_time_ns` | with care | — |
| **Backend-specific diagnostic** | `grid_candidates_examined`, `grid_distance_computations`, `grid_avg_candidates_per_query`, `grid_cells_examined`, `grid_max_candidates_per_query`; `cgal_range_candidates`, `cgal_exact_distance_evaluations`, `cgal_max_range_candidates_per_query`; `index_bytes` | within one backend only | **never** |
| **Analytical estimate** (datasets.csv) | `explicit_csr_bytes_estimate` = (n+1)·8 + 2|E|·4; `explicit_bitmatrix_bytes_estimate` = ⌈n²/8⌉ — what an explicit graph *would* need; |E| from streaming radius queries; **nothing is built** | yes | — |

Backend-specific columns are filled only for their own backend and are empty
otherwise. `cgal_range_candidates` counts points the CGAL radial search reported
(including the query point); CGAL's internal kd-tree node visits are not
exposed and are not reported. `index_bytes` is exact for the grid and
unavailable for CGAL; the memory-probe quantities below measure every backend
the same way.

**Memory (memory-probe rows; locked definitions).** One common baseline H₀ =
live heap just before the representation build starts (the independent
validation grid is built before H₀ when CGAL is the backend, so correctness
infrastructure is excluded). P_b = absolute heap peak during the build; H_r =
live heap after the build; H_s = live heap at `solve()` entry; I_a = peak
above H_s during `solve()`.

* `index_build_peak_bytes` = P_b − H₀: extra heap required at any point during
  representation construction;
* `final_representation_bytes` = H_r − H₀: retained representation footprint
  after construction completes;
* `algorithm_incremental_peak_bytes` = I_a: extra heap above the solve-entry
  baseline during the algorithm;
* `pipeline_peak_bytes` = max(P_b, H_s + I_a) − H₀: maximum end-to-end heap
  increase above the common pre-build baseline.

**CDS diameter** (secondary): hop diameter of the subgraph induced by the
returned CDS D — the maximum over pairs of selected vertices of the shortest
path using selected vertices only. Computed after the timer with the
independent grid, only for valid CDSs, once per distinct CDS; not an
optimisation objective.

## 6. Datasets, pairing and replication

* Geometries: uniform, clustered, perturbed_grid, corridor, dumbbell.
  **clustered** is a finite-window *Gaussian hotspot-plus-background model*:
  the clustered geometry is modeled as a finite-window hotspot-plus-background
  process, motivated by wireless-network models that superpose clustered and
  background node populations. Hotspot nodes are Gaussian-distributed around
  cluster centers, consistent with Thomas-process-style spatial models
  (Thomas-process-*inspired*: four fixed hotspots and a fixed 50/50 mixture,
  not a Thomas point process). Frozen version **D3-v2**: 4 hotspots, 50%
  background, σ = s · L with s = 0.05 and L = sqrt(n / density) the window
  side, and each hotspot point redrawn (same random stream) until it falls
  inside the window. Scaling σ with L keeps the local regime stable as n
  grows (thermodynamic scaling); s was selected by the preregistered
  calibration ladder (`experiments/calibration/generator_freeze_v2.json`).
  D3 v1 (absolute σ = 0.8, hotspot tails allowed outside the window) failed
  the connectivity and degree-regime gates: its hotspot degree grew roughly
  with n, and points falling outside the window became isolated. Draw order:
  centres, then background, then hotspot points round-robin.
  **dumbbell** (bottleneck geometry, successor of `cluster_bridge`): left
  square [0, a]², a corridor (neck) [a, a + l] × [a/2 − w/2, a/2 + w/2] and a
  right square, with w = 1.0, l = 3.0 (units of r) and
  a = sqrt((n / density − w · l) / 2), so the total area is n / density.
  Points are uniform over the domain: round(n · w · l / A) in the neck, the
  rest split equally between the squares; draw order left, neck, right. The
  neck holds ≤ 7.2% of the points at every primary n. v1 `cluster_bridge`
  (fixed-size Gaussian blobs joined by bridge chains) had a mean degree
  rising 88 → 1,781 over n and no response to density, so it failed the
  scale-stability and density-response requirements. The previous blobs-only construction (`background_fraction =
  0`) became essentially never connected at n ≥ 5,000 (blobs drift apart as
  the region grows), which would have forced acceptance-conditioned, highly
  atypical samples. Requested (`density_target`,
  `target_expected_degree`) and observed graph properties (mean/min/max/median
  degree, SD, density, components, isolated) are recorded per graph.
* Pairing: each (geometry, n, density, replicate) yields exactly one graph;
  all algorithms run on it. Rows carry `graph_id`, `dataset_id`,
  `dataset_sha256`, `points_fingerprint`, `graph_seed`.
* Seeds: SHA-256 of all factors; replicates never share a dataset (V4).
* Connectivity rule declared in the config; every attempt logged.
* Generation feasibility is checked before generation and recorded as
  `generation_infeasible_under_protocol` with the reason; such cells spend no
  attempts and are listed by `run_study.py plan`. Dumbbell: the domain is
  defined only if n / density > w · l and a ≥ w (excludes 8 of 9
  `exact_small` cells, none in the primary study). Legacy `cluster_bridge`
  (not used by any study): negligible probability of a connected UDG, with
  cluster coordinates bounded at 6 sigma (P < 2e-9 per coordinate; not a
  proof of impossibility). Sparse study: cells below the calibrated ≥ 18/24
  acceptance.
* Replicate counts are configuration-driven (`synthetic.replicates`). The graph
  is the statistical unit; timing repetitions are technical replicates
  (median per graph).

### Literature support (candidate citations — TO VERIFY against full text)

Brought in from a literature search; none has yet been read in full by the
project, so none is cited as established until checked and logged in
`docs/related_work_matrix.md` / `literature_search_log.xlsx`.

| Claim used | Candidate source | Status |
| --- | --- | --- |
| Connectivity of random geometric graphs at fixed density degrades with n; connectivity threshold tied to minimum degree / isolated vertices, growing ~ log n | M. D. Penrose, *Random Structures & Algorithms* 15(2), 1999 (minimum-degree / connectivity thresholds); M. D. Penrose, *Random Geometric Graphs*, Oxford Univ. Press, 2003 | to verify |
| Sharp asymptotic connectivity threshold for 2-D uniform geometric graphs | Penrose & Yang, *Annals of Applied Probability* (recent; Brunel repository record) | to verify (bibliographic details incomplete) |
| Connectivity edge-density threshold of random unit disk graphs ≈ ½ log n | "a recent ACM paper on random unit disk graphs" | **UNVERIFIED — SOURCE REQUIRED** (no resolvable reference yet) |
| Superposition of clustered users (Thomas cluster process) and uniform Poisson users in wireless networks | *Computer Networks*, 2020 (ScienceDirect S1389128619308874; reported as Ullah et al.) | to verify (authorship to confirm) |
| Gaussian-distributed nodes around hotspot centres (Thomas process) as an established wireless spatial model | *Frontiers in Communications and Networks*, 2022 (hotspot clusters) | to verify |
| Gaussian sensor clusters in non-homogeneous WSN deployments (coverage/connectivity) | *Ad Hoc Networks* (ScienceDirect S1570870512001680) | to verify |
| Thomas/Poisson cluster processes for IoT devices concentrated at hotspots | *Drones* 5(3):94 (MDPI), 2021 | to verify |
| Thermodynamic regime (finite mean degree) vs connectivity regime; growing the domain with n preserves the local regime | M. D. Penrose, *Random Geometric Graphs*, Oxford Univ. Press, 2003 | to verify |
| Connectivity of random geometric graphs in non-convex domains; narrow / quasi-one-dimensional regions change connectivity behaviour | Giles, Georgiou & Dettmann, "Connectivity of Soft Random Geometric Graphs over Annuli", *J. Stat. Phys.*, 2016 (doi 10.1007/s10955-015-1436-1) | to verify |
| Bottleneck / finitely ramified structures split into large components more easily than uniform RGGs | Dettmann, "Isolation and Connectivity in Random Geometric Graphs with Self-similar Intensity Measures", *J. Stat. Phys.*, 2018 (doi 10.1007/s10955-018-2059-0) | to verify |
| Domination number of random geometric graphs under thermodynamic scaling | Mitsche & Penrose (bibliographic details not yet resolved) | to verify (details incomplete) |

## 7. Exact OPT on small instances

Exhaustive search by increasing subset size (n ≤ 20), validated by the
independent validator, in its **own process with its own timeout**
(`exact.timeout_seconds`). A timeout or error is recorded
(`exact_status = timeout | error`, OPT and ratio empty) and never removes the
graph or its heuristic rows, avoiding survivorship bias. `empirical_ratio =
|D| / OPT` is an **empirical approximation ratio** on these instances, never
the theoretical ratio of a paper.

## 8. Statistics

Graph-level medians; per cell × backend × algorithm: count, mean, median, SD,
IQR, min, max, 95% bootstrap CIs; Wilson CIs for validity. Paired algorithm
comparisons on identical graphs within one backend for `t_algorithm_ms`,
`cds_size`, `cds_fraction`, `cds_diameter`: mean/median difference, bootstrap
CI, Cohen's d_z, wins/ties/losses; runtime also as a geometric-mean ratio. No
hypothesis tests. Replicate count: selected mechanically from the clean
precision pilot by `python/replicate_decision.py` under the locked rule
`experiments/precision/replicate_rule_v1.json` (Student-t CI half-widths of
paired CDS-fraction differences and log runtime ratios for k ∈ {20, 28, 36,
44, 52}, every (geometry, density) stratum; see the protocol §4).
`precision_curve.csv` and `precision.csv` remain descriptive aids only. Pareto views (median
per cell, Pareto-optimal algorithms ringed): CDS size vs T_algorithm, CDS size
vs neighbour queries, CDS fraction vs T_algorithm, empirical ratio vs
T_algorithm.

## 9. Separate studies (never mixed into the primary comparison)

| Config | Question |
| --- | --- |
| `final.json` | Primary: how do the four algorithms compare? (CGAL only) |
| `precision_pilot.json` | How many replicates are needed? |
| `exact_small.json` | How close to OPT on small UDGs? |
| `spatial_backend.json` | Does backend choice (CGAL vs grid) affect performance? (`backend_paired.csv`) |
| `real_world_scaling.json` | Real spatial data (template paths) |
| `smoke.json`, `pilot.json` | Pipeline checks |

## 10. Commands

```powershell
# One-time: CGAL (conda-forge) and a Release build with the same MSVC toolchain
conda create -n mcds-cgal -c conda-forge cgal-cpp=6.1.2 libboost-headers=1.88
cmake -S cpp -B cpp/build-msvc -DCMAKE_PREFIX_PATH=<conda>/envs/mcds-cgal/Library
cmake --build cpp/build-msvc --config Release --parallel
ctest --test-dir cpp/build-msvc -C Release
py -3 -m unittest discover -s python/tests

py -3 python/run_study.py plan      --config experiments/final.json
py -3 python/run_study.py reproduce --config experiments/smoke.json
```

Sub-commands: `plan`, `run`, `rebuild`, `analyze`, `figures`, `manifest`,
`reproduce`. Exit code 3 = fairness check failed; 2 = configuration /
environment refusal.

## 11. Fairness checks (automatic; V = study fails, W = reported)

V1 points/radius differ within a graph · V2 commit/solver/machine/config/build
differ · V3 unequal repetitions/warmups/instrumentation within a backend · V4
pseudo-replication · V5 timed rows not at the configured instrumentation · V6
solver fingerprint ≠ Python fingerprint · V7 unrequested backend · V8 backend
cross-check not identical · V9 an algorithm's CDS differs between backends ·
W1 missing timed rows (graph excluded from pairing) · W2 position imbalance ·
W3 a CDS changed across repetitions.

## 12. Memory measurement limitations

Heap tracking counts `operator new/delete` only (all STL containers), assumes
one thread, and adds a 16-byte header per allocation, so it is confined to
`mcds_bench_mem` whose timings are never analysed. Process RSS figures are
OS-specific and include shared preprocessing.

## 13. Known limitations

* Runtimes are properties of these centralized implementations (Funke and Li
  rescan all vertices per round / per selection), not of the distributed
  algorithms.
* Li's `(4.8 + ln 5)·opt + 1.2` bound is not claimed (conditional on Lemma 2).
* Exact OPT is exhaustive and capped at n = 20 (implicit: per-subset radius
  queries, no stored adjacency).
* CDS diameter costs |D|² radius queries per distinct CDS (implicit BFS,
  O(n) memory), always after the algorithm timer.
* CGAL internal search work is not observable; CGAL counters are limited to
  what the API returns.
* Single machine; no cross-machine runtime comparison.
