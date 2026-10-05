# Experimental methodology

How the project measures the four MCDS algorithms. The experiment runner is
`python/run_study.py` (package `python/study/`, C++ driver `mcds_bench`). It
changes no algorithm, generator, validator or spatial-index semantics; it
controls *how they are measured*.

This document describes the v1 methodology under development. It will be
locked with the final protocol ([final_experiment_protocol.md](final_experiment_protocol.md)).
Audit trail: [methodology_audit.md](methodology_audit.md). Paper verification:
[source_audit.md](source_audit.md).

```
config.json ──► plan (cells × replicates, seeds = SHA-256 of all factors)
                 │
                 ▼
generators.py (v1, unchanged) ──► CSV ──► SHA-256 + FNV points fingerprint
                 │                         │
                 ▼                         ▼
     mcds_bench --graph-only    (connectivity rule; EVERY attempt logged)
                 │
                 ▼  accepted graph, Williams-design order e.g. wan>li>marathe>funke
     mcds_bench (one process per graph)
        load once ─ T_dataset
        grid once ─ T_spatial_index
        graph stats ─ T_graph_stats            (outside every algorithm timer)
        [exact OPT] ─ T_exact                  (n ≤ 20 only)
        warmup:  A B C D
        timed 1: A B C D   ◄── timer wraps solve() only
        timed R: A B C D
        validate each execution (outside timer, raw grid)
     mcds_bench_mem (one process per algorithm)  ─ heap-tracked memory probe
     mcds_bench --instrumentation basic          ─ untimed counter pass
                 │
                 ▼
     graphs/<graph_id>/*.json ──► raw_runs.csv, datasets.csv,
                                  generation_attempts.csv, failures.csv
                 │
                 ▼
     fairness check (fails the study on violation)
                 │
                 ▼
     analysis: graph_level.csv, summary.csv, paired.csv, validity.csv
     figures/  methodology_manifest.json
```

## Commands

```powershell
# Build (Release): mcds, mcds_bench, mcds_bench_mem and all tests
cmake -S cpp -B cpp/build-msvc
cmake --build cpp/build-msvc --config Release --parallel
ctest --test-dir cpp/build-msvc -C Release

# Python tests
py -3 -m unittest discover -s python/tests

# Inspect a design without running it
py -3 python/run_study.py plan --config experiments/pilot.json

# ONE command that reproduces a study (resumable; re-run the same command)
py -3 python/run_study.py reproduce --config experiments/smoke.json
```

Sub-commands: `plan`, `run`, `rebuild` (re-derive CSVs from stored JSON),
`analyze`, `figures`, `manifest`, `reproduce`. Exit code 3 = fairness check
failed; 2 = configuration / environment refusal.

Studies shipped: `smoke` (pipeline check), `pilot`, `exact_small` (RQ10),
`real_world_scaling` (RQ9, template paths), `final` (do not run before the
protocol is approved; `final: true` refuses a dirty tree or a non-Release build).

## Fairness safeguards

| Safeguard | Where |
| --- | --- |
| All algorithms of a graph run in one process on one in-memory point set and one index | `bench_main.cpp` |
| Solver recomputes the points fingerprint; runner aborts on mismatch with Python's | `runner.run_graphs` |
| Same reps / warmups / instrumentation for every algorithm on every graph | `fairness.py` V3/V5 |
| No dataset reused across replicates | `seeds.py`, `fairness.py` V4 |
| Commit / solver / machine / config / build identical within a graph | `fairness.py` V2 (recorded per step) |
| Balanced, recorded execution order | `schedule.py` (Williams design) |
| Config hash locks a study directory; environment change refused on resume | `runner._init_dir` |
| Graphs with a missing algorithm are excluded from paired analysis and reported | `fairness.py` W1, `analysis.paired` |

## Timing methodology

* Clock: `std::chrono::steady_clock` (QPC on Windows; observed resolution
  recorded in `build.clock_observed_resolution_ns`, 100 ns on the audit machine).
* Timed region: `algorithm->solve(points, index, radius)`. Stats reset happens
  before the first clock read; validation, hashing, role counting and JSON
  serialisation after the second. No I/O inside.
* Warmups: recorded as `phase=warmup`, excluded from statistics. Rationale:
  the first execution in a process pays page-fault and allocator start-up
  costs that are not properties of the algorithm.
* Repetitions are interleaved across algorithms (A B C D, A B C D, …) so slow
  drift affects all algorithms alike; every repetition is a raw row.
* Primary runtime metric: `t_algorithm_ms` of `phase=timed` rows at
  `instrumentation=none`. Per graph, use the median over repetitions.
* `T_dataset`, `T_spatial_index`, `T_graph_stats`, `T_exact` are per graph
  (datasets.csv); `T_validation` is per execution (raw_runs.csv). `T_output`
  and `T_total` are not timed inside the solver; the runner records step
  wall time in `graphs/*/…meta.json`.

## Instrumentation levels

| Level | Index given to the algorithm | Extra data | Use |
| --- | --- | --- | --- |
| `none` | the grid itself (identical hot path to v1) | queries, candidates, neighbours, distance computations | **all runtime comparisons** |
| `basic` | `InstrumentedSpatialIndex` (forwarding decorator) | + cells examined, max candidates/query, max neighbours/query | counter pass (`phase=counters`) |
| `detailed` | decorator + per-query clock | + total query time | diagnostics only |

A test proves the decorator is transparent: every algorithm returns the same
set and the same counters through it.

## Metric dictionary (raw_runs.csv, schema `mcds-results-1`)

| Column | Definition | RQ |
| --- | --- | --- |
| `t_algorithm_ns` / `_ms` | wall time of `solve()` | RQ3, RQ4 |
| `neighbor_queries` | calls to `radiusQuery` during `solve()` | RQ7, RQ8 |
| `candidates_examined` | points in scanned grid cells, summed (includes the query point) | RQ8 |
| `distance_computations` | `candidates_examined − neighbor_queries` (exact for the grid: the query point is always scanned and is the only candidate skipped before the distance test) | RQ8 |
| `neighbors_returned` | Σ neighbours returned | RQ8 |
| `cells_examined`, `max_*_per_query` | counter pass only | RQ8 |
| `cds_size`, `cds_fraction` | |D|, |D|/|V| | RQ2 |
| `core_count`, `connector_count` | from the algorithms' existing role tags: MIS/core vs connector. Diagnostic only — not comparable as "work" | RQ7 |
| `valid_solution`, `domination_valid`, `connectivity_valid`, `failure_reason` | independent validator | RQ1 |
| `opt_size`, `empirical_ratio` | exact OPT (n ≤ 20) and |D|/OPT — *empirical* ratio | RQ10 |
| `heap_peak_additional_bytes` | peak live heap bytes above the level at `solve()` entry (memory probe rows) | memory |
| `heap_allocation_count`, `heap_allocated_bytes` | allocations during `solve()` | memory |
| `process_peak_rss_bytes`, `rss_before_algorithm_bytes` | process RSS around a probe (includes shared preprocessing) | memory |
| `execution_order`, `execution_position`, `schedule_row`, `sequence` | scheduling provenance | fairness |
| `cds_hash` | FNV-1a of the sorted selected ids (determinism check) | RQ1 |

Graph-level metrics (datasets.csv): `edges`, `mean/min/max/median_degree`,
`degree_std`, `graph_density`, `component_count`, `largest_component`,
`isolated_count`, `target_expected_degree` (= density·π·r², nominal only),
`index_bytes`, `dataset_bytes`, generation seed/attempt, projection metadata.

## Memory measurement limitations

* Heap tracking counts `operator new/delete` only (all STL containers). It
  does not see `malloc` from C code (none in this project) or stack usage, and
  assumes a single thread (true for the solver).
* The heap-tracking allocator adds a 16-byte header per allocation, so it is
  confined to `mcds_bench_mem`; its timings are never analysed.
* Process RSS figures are OS-dependent (Windows working set vs Linux
  `ru_maxrss`) and include shared preprocessing; they are context, not
  algorithm memory.

## Known limitations

* Funke and Li runtimes reflect centralised full-rescan simulations.
* All algorithms are deterministic; `algorithm_seed` is `n/a`.
* Exact OPT is exhaustive and capped at n = 20.
* Source verification status per algorithm: `docs/source_audit.md`.
