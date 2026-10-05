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
| C++ suites | 10/10 | 11/11 (+ `test_bench_support`) |
| Python tests | 59 pass, 1 skip | see the latest run in the hand-over message |
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
