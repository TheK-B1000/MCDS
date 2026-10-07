# Methodology Audit and Upgrade Record (v1 development)

Date: 2026-10-05. Audited state: `main` @ `06bf246` (clean). Source audit:
[source_audit.md](source_audit.md). Methodology reference:
[experimental_methodology.md](experimental_methodology.md).

**Project phase:** v1 methodology development. Final data collection has not
started. The methodology may still change; it will be locked by the procedure
in [final_experiment_protocol.md](final_experiment_protocol.md) (git tag, e.g.
`v1.0-final-experiment`, plus `methodology_manifest.json`). The older tag
`v1.0-experiments` (`18bdcea`) is a historical snapshot of the pre-upgrade
pipeline, not a freeze of the final methodology.

---

## 1. Baseline test results (before any change)

Build: MSVC 19.44.35222, Visual Studio 17 2022 generator, Release
(`/O2 /Ob2 /DNDEBUG`), C++17.

| Suite | Result |
| --- | --- |
| C++ (`ctest -C Release`) | 10/10 passed |
| Python (`py -3 -m unittest discover -s python/tests`) | 59 passed, 1 skipped (`MCDS_MILLION_TEST` gate) |

MSVC emits C4244 conversion warnings from `<xutility>` instantiations in
`mcds_core`; the README previously claimed a warning-free MSVC build.

## 2. Algorithm-output integrity check

HEAD was five commits past `v1.0-experiments`, touching all four algorithm
files (Li MIS refactored into `WanLevelMis.cpp`, DSU rewritten, role metadata
added). The tag was exported with `git archive`, built separately, and both
solvers were run on every pre-upgrade pilot dataset with n ≤ 1000:

| Comparison | Identical selected sets **and** identical query / candidate counts |
| --- | --- |
| before the upgrade | 540 / 540 (135 connected datasets × 4 algorithms) |
| after the upgrade | 540 / 540 |

No algorithm's output or spatial-query behaviour changed during the infrastructure work. The only later semantic change is the Wan pruning rule (§8).

## 3. Pre-upgrade pipeline (for the record)

```
generators.py -> CSV (+SHA-256) -> mcds --check-connectivity
   retry: effective_seed = base_seed + attempt
-> for algorithm in fixed order: for rep: one process per execution
     load -> index -> connectivity BFS -> solve() [timed] -> validate -> JSON
-> experiments.csv: median algorithm_ms; peak RSS of the whole process
-> plots.py / study_report.py (means, mean paired differences)
```

## 4. Risk register

### Correctness

| ID | Finding | Status |
| --- | --- | --- |
| C1 | Real-world mode passed the *top-level* config radius (default 1.0) to every trial, while connectivity was checked at the dataset's own radius (e.g. 100 m). A regression test reproduced it (`[1.0] != [100.0]`). No real-data results existed. | Fixed: the runner uses each dataset's own radius (external datasets *must* declare `radii`); covered by `test_external_real_data_failures_and_metadata` |
| C2 | Marathe roots at input index 0, the others at min id (identical for all generator/importer output). | Documented |

### Fairness

| ID | Finding | Status |
| --- | --- | --- |
| F1 | Funke's `solve()` ran an internal full connectivity BFS inside `T_algorithm` (1,000 of 15,329 queries at uniform n=1000). | Fixed (approved): removed from `solve()`; connectivity checked once, untimed, for all algorithms. Output identical on connected inputs; Funke queries drop by exactly n |
| F2 | Fixed algorithm order on every dataset. | Fixed: Williams design, recorded per trial |
| F3 | Funke and Li runtimes are dominated by centralised full rescans. Runtime compares *our implementations*. | Documented; must be stated in reports |
| F4 | Peak memory was whole-process (load + index + connectivity + validation). | Fixed: heap-tracked per-algorithm probe |

### Source verification

Primary PDFs for all four papers are now available locally (SHA-256 recorded
in `docs/algorithms/`) and each implementation has a paper-to-code audit; see
`source_audit.md`. Outcome: Marathe YES; Funke YES (4-page WiMob text; TOSN not
checked); Wan YES after adding the §VI.A pruning rule; Li S-MIS PARTIAL
(Lemma 2 for our MIS — a proof is proposed in `algorithms/li_smis.md`, not yet
adopted).

### Reproducibility

| ID | Finding | Status |
| --- | --- | --- |
| R1 | **Pseudo-replication:** `base_seed + attempt` let replicate r's retry reuse replicate r+1's seed. The pre-upgrade pilot has **31 point sets shared by more than one "independent" replicate** (e.g. uniform n=1000 density 3: seeds 1, 2, 3 are all effective seed 5). | Fixed: SHA-256 seed derivation + automatic uniqueness check (V4) |
| R2 | Compiler, flags, C++ standard recorded as "unknown". | Fixed: compiled into `mcds_bench` |
| R3 | No per-algorithm source hash, CPU model, physical cores, power plan. | Fixed: `environment.json` |
| R4 | Importer hashed output CSV only. | Fixed: `input_sha256` of the raw source |
| R5 | Resume appended to one CSV; config changes undetected. | Fixed: config-hash lock; CSVs derived from per-graph artifacts |

### Missing measurements → now collected

Graph statistics; distance computations; cells examined; max candidates /
neighbours per query; core vs connector counts; warmup rows; execution order;
solver-side dataset fingerprint; exact OPT inside the main runner.

### Statistics

S1 means only → medians, IQR, bootstrap CIs. S2 no CIs / paired means only →
paired differences with CIs, effect sizes, wins/ties/losses, runtime ratios on
the log scale. S3 pseudo-replication → R1. S4 undeclared acceptance rate →
every generation attempt logged, rule fixed in the config.

## 5. Prioritised upgrade plan and status

| Priority | Item | Status |
| --- | --- | --- |
| CRITICAL | Collision-free seeds; dataset-uniqueness check | done |
| CRITICAL | Per-dataset radius for real data | done |
| CRITICAL | Source audit; no algorithm change without primary sources | done |
| CRITICAL | One in-memory graph per process; fingerprint checked Python ↔ C++ | done |
| CRITICAL | Fairness checker that fails the study | done |
| CRITICAL | Only `solve()` timed; separate T_dataset / T_spatial_index / T_graph_stats / T_exact / T_validation | done |
| IMPORTANT | Balanced, recorded execution order | done |
| IMPORTANT | All warmup / timed repetitions kept raw; versioned long-form schema | done |
| IMPORTANT | Graph statistics, spatial counters, core/connector counts | done |
| IMPORTANT | Per-algorithm heap memory probes | done |
| IMPORTANT | Environment snapshot incl. compiler / flags | done |
| IMPORTANT | Bootstrap / Wilson CIs, paired analysis | done |
| IMPORTANT | Remove Funke's internal BFS (F1) | done (approved) |
| CRITICAL | Paper-to-code audits against primary PDFs | done (see `source_audit.md`) |
| CRITICAL | Implement Wan §VI.A black→gray pruning (was omitted) | done, tested against an asynchronous paper-rule reference |
| IMPORTANT | Li: conditional guarantee + adaptation label; Marathe stale comment; Funke tie-break doc | done (comment-only) |
| OPTIONAL | Algorithm-internal counters (Funke rounds, Li iterations, BFS calls) | not done (algorithm-file edits) |
| OPTIONAL | Exact OPT beyond n = 20 (ILP / branch-and-bound) | not done (no solver dependency) |
| OPTIONAL | CGAL SpatialIndex backend | not done |

## 6. Consolidation into one framework

There is one experiment runner, one result schema, one validator, one
`SpatialIndex` interface, one set of configs and one documentation path.

| Before | Now |
| --- | --- |
| `python/experiment_runner.py` + old `python/run_study.py` | `python/run_study.py` → `python/study/` |
| `python/preflight.py` | `Study.preflight()` (all algorithms valid on a small connected graph) |
| `python/study_report.py`, `python/plots.py`, `python/algorithm_summary.py` | `study/analysis.py`, `study/figures.py` |
| `python/exact_small_study.py` | `experiments/exact_small.json` (exact OPT inside the runner) |
| `experiments.csv` (+ side JSONs) | `raw_runs.csv`, `datasets.csv`, `generation_attempts.csv`, `failures.csv` (schema `mcds-results-1`) |
| 11 old-format configs | `experiments/{smoke,pilot,exact_small,real_world_scaling,final}.json` |
| `python/connectivity_calibration.py` | kept, now probes graphs with `mcds_bench --graph-only` |

Kept unchanged: `mcds` CLI (GUI and single runs), GUI, visualization,
importers, `divergence_search.py`, `explicit_baseline.py`.

Tests removed together with the code they tested: `test_experiment_runner.py`
and `test_lab_upgrades.py` (old runner's resume / batch state / failures CSV /
hashing). Their properties are now covered in `test_study.py` (resume without
duplication, config lock, failure recording, hashing/fingerprints). Old-runner
config tests in `test_real_dataset.py` were ported to the new config format.
The optional million-point test now probes with `mcds_bench --graph-only`.

Local pre-upgrade result folders `results/studies/{smoke,pilot}` were moved to
`results/legacy_pre_upgrade/` (git-ignored, untouched) so the new runner,
which refuses foreign directories, can use those study ids.

## 7. Files

Modified: `cpp/include/GridSpatialIndex.hpp`, `cpp/src/GridSpatialIndex.cpp`
(additive `cellsScannedFor()`; query path untouched), `cpp/CMakeLists.txt`
(appended targets), `python/real_dataset.py` (`input_sha256`),
`python/run_study.py` (replaced), `python/connectivity_calibration.py`,
`python/tests/test_real_dataset.py`, `README.md`, `experiments/*.json`.

New: `cpp/{include,src}/bench/*`, `cpp/include/bench/BuildInfo.hpp.in`,
`cpp/src/bench_main.cpp`, `cpp/tests/test_bench_support.cpp`, `python/study/*`,
`python/tests/test_study.py`, `docs/source_audit.md`,
`docs/experimental_methodology.md`, `docs/methodology_audit.md`,
`docs/final_experiment_protocol.md`, `docs/algorithms/*.md`.

Not modified: every algorithm source except `Wan.cpp` (pruning), `Funke.cpp` (connectivity check removed from `solve()`) and comment-only header edits (`Wan.hpp`, `LiSMIS.hpp`, `Marathe.hpp`, `Funke.hpp`), `WanLevelMis`, validator, connectivity,
CSV loader, PointSet, the `SpatialIndex` contract, `generators.py`, the `mcds`
CLI, and the project notes `docs/{marathe,wan,funke,li}.md`.

## 8. Changes that could alter algorithm semantics or measurements

| Proposed change | Semantics | Measurement | Decision |
| --- | --- | --- | --- |
| Remove `isConnected()` from `Funke::solve()` | Identical output on connected inputs; disconnected inputs are still rejected (runner pre-check; Funke throws `invalid_argument` when the red frontier dies out) | Funke's T_algorithm and queries drop by exactly one BFS (n queries) | **Done (approved)** |
| Wan's black→gray pruning | Shrinks Wan's CDS (pilot n ≤ 1000: mean 0–0.96 vertices per graph depending on geometry, max 5) | Adds one radius query per selected vertex inside T_algorithm | **Done** on your instruction, from the rule on p. 5 of the PDF |
| Funke from TOSN instead of WiMob text | Unknown | — | Not done — TOSN PDF not in the source set |
| Algorithm-internal counters | None if done carefully | Work inside the timed region | Not done |
| Instrumented index (`basic`/`detailed`) | None (tested: identical sets and counters) | Overhead → never used for runtime comparisons | Done, gated |

## 9. Upgrade outcome

| | Before | After |
| --- | --- | --- |
| C++ suites | 10/10 | 11/11 (+ `test_bench_support`; see §10 for current) |
| Python tests | 59 pass, 1 skip | 72 pass, 1 skip (before CGAL; see §10 for current) |
| Algorithm outputs vs old tag | 540/540 identical | Marathe, Funke, Li identical; Wan differs only by pruned vertices (always a subset, always valid) |

Findings that matter for the science:

1. The pre-upgrade pilot is pseudo-replicated (R1); its seed-level statistics
   overstate the sample size.
2. Funke is charged an extra BFS (F1).
3. Runtime reflects centralised simulations (Li: 64,356 queries vs Wan's 2,000
   at uniform n=1000).
4. Marathe and Wan often return the identical CDS; ties are reported
   explicitly in the paired analysis.
5. Real-data mode would have produced radius-1 m results (C1, fixed).

Remaining limitations: Li bound not claimed for v1 (Lemma 2 proof sketch unreviewed); Funke TOSN unaudited and not cited as the source; no algorithm-internal
counters; exact OPT capped at n = 20; heap probe excludes stack and non-`new`
allocations; position balance exact only when replicates are a multiple of 4;
single-machine design.

## 10. CGAL primary spatial backend (2026-10-05)

Context: the professor asked for CGAL. Decision: CGAL is the primary backend of
the final study; `GridSpatialIndex` stays as an independent secondary backend;
brute force stays as the test oracle. No algorithm file was changed.

**Repository events recorded for provenance.** (1) A branch created for the
earlier methodology commit was removed and `main` was found at the parent
commit; `main` was fast-forwarded to `c93fcd3` (no history rewritten). (2) The
tag `v1.0-final-experiment` (on the pre-CGAL commit `c93fcd3`) was deleted
locally on request because it no longer described the methodology; it had
never been pushed. No final tag exists. `METHODOLOGY_VERSION = "v1-dev"`.

**Dependency.** CGAL 6.1.2 + Boost 1.88 headers from conda-forge in a
dedicated env (`mcds-cgal`); the solver stays on the same toolchain as before
(MSVC 19.44.35222.0, VS 2022 generator, Release `/O2 /Ob2 /DNDEBUG`, C++17).
CGAL 6.2.1 was not solvable with the installed conda 24.7 (`__win` virtual
package reported as 0); upgrading base conda was avoided. Versions are compiled
into `mcds_bench` and recorded in `environment.json` and every manifest.

**Implementation.** `cpp/include/CgalSpatialIndex.hpp`,
`cpp/src/CgalSpatialIndex.cpp`: `CGAL::Kd_tree` over point indices
(`Search_traits_adapter` + `Pointer_property_map` on
`Search_traits_2<Simple_cartesian<double>>`), eager `build()`, queries with
`Fuzzy_iso_box` (ε = 0) of half-side `r(1+1e-9) + 8ε(|x|+|y|+r)`, then the
project's exact predicate `distanceSquared <= r²`. The widening adds only
candidates, never edges (argument in `experimental_methodology.md` §3). API
calls were checked against the installed headers (`Kd_tree.h`,
`Fuzzy_iso_box.h`, `Search_traits_adapter.h`, `property_map.h`).

**No silent fallback (each tested).** Configure without CGAL → CMake
FATAL_ERROR with install instructions. Grid-only build (`-DMCDS_WITH_CGAL=OFF`)
asked for `cgal` → exit 2, no output. Runner: refuses a study requesting cgal
on a solver without CGAL; rejects bench output reporting another backend;
`final: true` configs must use `cgal` only.

**Differential validation.** `test_spatial_backends`: 1,821 point sets,
258,886 neighbour queries (five geometries; n 1–600; densities 0.5–40; radii
0.5–3; offsets to ±1e7 and UTM scale; non-identity ids; exact-boundary,
one-ulp-outside, coincident (also r = 0), single/empty sets): CGAL = grid =
brute force, 0 discrepancies. All four algorithms on 839 connected graphs:
identical selected sets, roles, validity and query counts through CGAL and
grid. Shuffled neighbour order: identical outputs (no order dependence).
In production every graph is cross-checked (CGAL vs grid, all n neighbour
sets) before it is run; a mismatch blocks the graph (fairness V8). One test
defect was found and fixed during development (the test built a grid with
cell size 0 for the r = 0 case; not a backend discrepancy).

**Other changes in this pass.** Spatial backend as the single configuration
mechanism (`spatial_backend`, string or list; per-row provenance);
backend-specific counters renamed (`grid_*`, `cgal_*`, never cross-filled);
CDS diameter (after the timer, independent grid); separate connectivity
timing; exact OPT moved into its own process with its own timeout (failures
recorded, heuristic rows kept); per-metric paired statistics,
`backend_paired.csv`, `precision.csv`, `precision_curve.csv`; Pareto views;
configs `precision_pilot`, `spatial_backend`; fairness V7–V9; schema
`mcds-results-2`; bench schema `mcds-bench/2`.

**Funke.** The private connectivity check was already removed from the timed
`solve()` in the previous pass (identity verified on 174 graphs); it is not
reintroduced.

**Execution order.** Already balanced (seeded Williams design) and recorded
per row (`execution_order`, `execution_position`, `schedule_row`).

**Tests after this pass.** C++ 12/12 suites (+ `test_spatial_backends`);
Python 82 passed, 1 optional skip. Study results: see the hand-over report.

## 11. Hard invariant: the graph is never stored (2026-10-05)

Professor's requirement: the input remains a set of n points and the UDG is
never created or stored explicitly at any point. Audit of every path found
five places that stored edges; all are fixed, and a guard now enforces it.

| Place | Before | Now |
| --- | --- | --- |
| Real-data largest-component filter (`real_dataset.py`) | full Python adjacency list of the dataset | union-find over the grid scan, O(n); same tie-breaking (largest, then smallest member index) |
| Exact OPT (`ExactSmallMCDS.cpp`, n ≤ 20) | adjacency lists | per-subset radius queries through an implicit `GridSpatialIndex`; signature and tests unchanged |
| CDS diameter (`BenchSupport.cpp`) | CDS-induced subgraph lists | BFS from every CDS vertex with on-demand radius queries filtered to D; O(n) bitmap + distances |
| Explicit CSR backend | `ExplicitAdjacencyIndex` (whole UDG as CSR) | removed; `explicit` backend removed from bench, config and tests; replaced by `explicit_csr_bytes_estimate` / `explicit_bitmatrix_bytes_estimate` (count-only analytical size) |
| Visualisation `--show-cds-edges` | segments between adjacent CDS points (`cds_edges`) | removed (CLI flags, `--edge-k-limit`, GUI toggle, legend entry and helper); the plot draws points only; a test asserts the API and flags are gone and no line is drawn; tripwire extended to visualisation/GUI |

Already implicit (verified): all four algorithms (Marathe's per-level vertex
lists are O(n), no edges), validator, connectivity, graph statistics (degree
counts only), `explicit_baseline.py` (counts edges, stores none).

Guard (`python/tests/test_implicit_graph_guard.py`): behavioural — dense graph
with 2,779,178 edges (explicit CSR 22.3 MB): whole-process heap peak 592 KB
(CGAL) / 419 KB (grid) across every phase, required < 10% of the CSR; LCC
filter checked with `tracemalloc` (< 5 MB on ~2.4 M edges). Static tripwire —
flags adjacency-building constructs in production sources; verified to flag
all four pre-fix files (7 + 3 + 1 + 5 hits).

Memory accounting finalised with locked definitions (H₀ baseline;
`index_build_peak_bytes`, `final_representation_bytes`,
`algorithm_incremental_peak_bytes` — renamed from `heap_peak_additional_bytes`,
which was already incremental — and `pipeline_peak_bytes`). Schema
`mcds-results-3`.

Studies: the queue was stopped. smoke, spatial_backend and the partial
exact_small run are archived in `results/prefix_implicit_fix_engineering/`
as pre-fix engineering evidence (CDS diameter and exact OPT stored edges).
New CDS-diameter tests (known graphs + brute-force comparison on 60 random
sets) added. Tests after the fix: C++ 12/12; Python 86 passed + 1 optional
skip.

## 12. Structurally infeasible generator cells (2026-10-05)

The post-fix exact_small run stalled in its cluster_bridge cells: all 9
replicates of `cluster_bridge|n=10|density=3` exhausted 200 attempts. Cause
(generator design, not an MCDS issue): `gen_cluster_bridge` places cluster
centres at least max(6·spread, 8) apart and only round(0.25·n) = 2-4 bridge
points along each gap, so no connected UDG can exist at n = 10, 13, 16; ~14 h
would have been spent recording 216 predetermined failures. The run was
stopped and archived (`results/postfix_engineering/`).

Fix: deterministic pre-generation check `study.datasets.structural_feasibility`
(x-projection argument; cluster coordinates bounded at 6 sigma). Infeasible
cells are recorded as `structurally_infeasible` with the reason, spend no
attempts, and are listed by `run_study.py plan`. cluster_bridge stays in
every study where it is feasible, with unchanged parameters (bridge_fraction
was deliberately not raised to rescue the cells). Only the 9 exact_small
cluster_bridge cells are affected; no other config is. Tests: analytical
cases, an empirical cross-check (900 generator draws at the flagged sizes,
none connected), and an end-to-end exclusion test.

## 13. CGAL candidate query: radial search (2026-10-06)

Candidate retrieval switched from `Fuzzy_iso_box` to CGAL's radial range
search `Fuzzy_sphere` (radius r' = r(1+1e-9) + 8ε(|x|+|y|+r)), before any
reportable data. Reading the installed header showed that CGAL 6.1.2's sphere
boundary test differs by internal path (`contains()` inclusive,
`contains_point_given_as_coordinates()` exclusive), so the sphere is used only
to retrieve a guaranteed superset; adjacency is still decided by the shared
exact predicate. Counters renamed `cgal_range_candidates`,
`cgal_max_range_candidates_per_query`; bench `counter_semantics` =
`cgal_radial_report`. Differential suite re-run (see the hand-over report).

Terminology correction (2026-10-06): the status is
`generation_infeasible_under_protocol` (function `generation_feasibility`).
The Gaussian cluster coordinates are unbounded, so the 6-sigma argument shows
negligible probability (< 2e-9 per coordinate), not impossibility; the 900
failed draws are corroborating evidence, not a proof. The pre-freeze
exact_small run of 2026-10-06 00:42 still carries the earlier label
`structurally_infeasible` in its records.

## 14. Clustered geometry redesign and density-5 removal (2026-10-06)

Finding: the blobs-only clustered generator (4 Gaussian blobs, σ 0.8, centres
uniform in a region of side √(n/density)) almost never yields a connected UDG
at large n (connectivity acceptance 1.2% at n = 5,000 and 0.4% at
n = 10,000 in pre-freeze runs; 0/12 at n = 10,000 for every density in the
prototype comparison), so large-n clustered cells would contain only rare,
atypical accepted graphs (selection bias).

Prototype comparison (12 graphs per cell; connected count at densities 5/8/12;
scratch evidence, not committed):

| Design | n = 1,000 | n = 5,000 | n = 10,000 |
| --- | --- | --- | --- |
| D0 blobs only (old) | 1 / 2 / 3 | 0 / 0 / 1 | 0 / 0 / 0 |
| D1 ⌈n/100⌉ blobs | 0 / 1 / 3 | 0 / 0 / 1 | 0 / 0 / 0 |
| D2 + 40% background | 0 / 4 / 9 | 0 / 6 / 12 | 0 / 4 / 11 |
| D3 + 50% background | 6 / 7 / 12 | 0 / 8 / 11 | 0 / 8 / 9 |

Decision (user): adopt D3 (4 hotspots, σ 0.8, 50% hotspot / 50% uniform
background, same region/density convention) as the clustered generator;
primary final factorial uses densities 8 and 12 for all geometries (density 5
removed; balanced 50-cell design); density 5 only in an optional,
calibration-gated sparse study, never mixed into the primary comparison.
Implementation: `gen_clustered(..., background_fraction=0.5)`;
`background_fraction = 0` reproduces the old construction exactly (tested).
Preregistered calibration on independent validation seeds:
`python/connectivity_calibration.py` →
`experiments/calibration/generator_calibration_v1.json` (results: see the
hand-over report). Calibration-gated admission: `feasibility_calibration`
(file + sha256 + min_acceptance_rate); forbidden for `final: true`.

## Final freeze (2026-10-06)

* Generators frozen by the v2 calibration (`experiments/calibration/generator_freeze_v2.json`).
* Replicate count 36, selected mechanically by the clean precision pilot under the
  rule frozen beforehand (`experiments/precision/replicate_selection_v1.json`):
  k = 20 and 28 failed, 36 was the first k to pass in every stratum, and runtime
  precision (Funke on clustered graphs) was binding.
* `final.json` and `sparse_density5.json` set to 36; `METHODOLOGY_VERSION` set
  to `v1.0-final-experiment`; annotated tag `v1.0-final-experiment` on the
  freeze commit. `v1.0-experiments` remains as a historical tag.
* From here on, a scientific change means a new methodology revision (new tag,
  new `study_id`) and rerunning the affected results, never a silent patch.

## Pre-final audit change (before any final data)

* A read-only audit of the frozen build (commit `a5cebd7`) found it
  correct (implicit graph, CGAL predicate, validation, timed region all PASS)
  but implementation efficiency asymmetric: Li S-MIS rescanned every grey
  vertex per connector (≈ 192–238 queries per vertex at n = 5000, ≈ 79% of the
  pilot's n = 10000 wall time) and Funke queried every red/white and white
  vertex every round (≈ 11–100 queries per vertex), while Marathe and Wan use
  ≈ 2.1. The final run was blocked.
* Only those two search loops were rewritten (protocol §3a). Outputs must be
  identical to the pre-audit code; evidence: `test_search_equivalence` and a full replay of the
  precision-pilot graphs. The precision pilot is re-run because runtime
  precision selected k.
* `docs/algorithms/funke.md` corrected: the n + 2 round guard stops the loop,
  it does not throw (true before and after the change).
* The local tag `v1.0-final-experiment` (annotated object `73c91fb`, on
  `a5cebd7`) was deleted on the owner's request before it was ever pushed, so
  the team only ever sees one final tag. The name will be created again on the
  final lock commit. The rejected build is identified by commit `a5cebd7`;
  results made with it record that commit and the label
  `v1.0-final-experiment`.
* Work stays on `main` (no revision branch, no v1.1 naming). The protocol
  label is `v1.0-dev` until the final lock.
* **Pilot re-run on `27c7d26` (`precision_pilot_rerun`, 2026-10-07 00:10:47Z–
  01:02:53Z).** Clean start, uninterrupted, fairness PASS, all 31,200 timed runs
  valid; the frozen rule selected k = 20 (every k passed every stratum; widest
  runtime CI ±6.4% at k = 20). Literal history: the machine was **not** fully
  quiet. The test target `test_search_equivalence` was compiled at ~00:12:54Z,
  and the owner's commits `c8566aa` (removing the optional
  `representation_ablation` config and its mentions) and `d4c96cc` (removing
  unused includes from four algorithm sources and an unused BFS `parent` array
  from `WanLevelMis.cpp`, inside Li's timed MIS step) were made at
  00:29–00:31Z. The timing binary itself was built at 00:01:10Z from `27c7d26`
  and never rebuilt during the run (all 1,560 results report the same build).
* Because `d4c96cc` changed timed algorithm code after that pilot, the owner
  chose to keep it, re-validate outputs (equivalence test and full replay
  against the pre-audit CDSs) and re-run the pilot on the code to be locked
  (`experiments/precision_pilot_rerun2.json`, same design and seed). The
  `precision_pilot_rerun` results are kept as evidence and are superseded.

## Final lock (2026-10-07)

* `precision_pilot_rerun2` (authoritative; on `d4c96cc` via `ba197e7`, quiet
  machine verified by file times) selected k = 20; every candidate passed.
* `final.json` and `sparse_density5.json` set to 20 (final study 1,000
  graphs); evidence in `experiments/precision/replicate_selection_final.json`;
  `METHODOLOGY_VERSION = "v1.0-final-experiment"`; annotated tag
  `v1.0-final-experiment` created on the lock commit.
* From here on, a scientific change means a new methodology revision and
  rerunning the affected results, never a silent patch.
