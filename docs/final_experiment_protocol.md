# v1 Final Experiment Protocol (pre-registered)

**Status: REOPENED BEFORE ANY FINAL DATA — final run BLOCKED.** The
2026-10-06 lock (commit `a5cebd7`) was rejected for final runtime claims by the
pre-final read-only audit: Funke and Li S-MIS were
implemented as full-vertex scans (≈ rounds·n and ≈ blues·n neighbour queries)
while Marathe and Wan need ≈ 2n, so runtime partly measured implementation
quality. The fix changes only how Funke and Li find the next affected
vertices; their outputs are required to be identical to the pre-audit code
(§3a). The replicate count
is re-selected by re-running the precision pilot under the unchanged rule.
Previous status line: **LOCKED** (2026-10-06; git tag `v1.0-final-experiment`,
`METHODOLOGY_VERSION = "v1.0-final-experiment"`). That local tag was deleted
before it was ever pushed; the rejected build is identified by its commit
`a5cebd7`, and the tag name is reserved for the final lock. Decisions recorded on
2026-10-05 stand (no directional hypotheses, CGAL as the primary backend,
machine preparation, Li bound not claimed). The generators were frozen by the
v2 calibration and the replicate count (36) by the precision pilot (§4).
The older tag `v1.0-experiments` is historical provenance only and is not
this protocol. From the first final run onward, nothing below may be changed in response to results. A scientific change (algorithm semantics,
timing boundary, generator, validator, metric definition, exclusion rule or
schema) means: stop, document it, create a new methodology revision (new tag,
new `study_id`), and rerun the affected results. Ordinary bugs found during
collection are handled the same way if they affect any recorded value.

Machine-readable design: `experiments/final.json`.

## 1. Research questions

| RQ | Question | Primary metric |
| --- | --- | --- |
| RQ1 | How reliably does each implementation return a valid CDS? | `valid_solution` rate (Wilson CI) |
| RQ2 | How large is the CDS? | `cds_size`, `cds_fraction` |
| RQ3 | How fast is each implementation? | `t_algorithm_ms` (timed, `none`) |
| RQ4 | How does performance scale with n? | RQ2–RQ3 metrics vs n |
| RQ5 | How does density / observed degree affect behaviour? | vs `density_target` and observed `mean_degree` |
| RQ6 | How does spatial structure affect results? | by geometry |
| RQ7 | What internal work explains runtime differences? | `neighbor_queries`, core/connector counts |
| RQ8 | How much spatial-neighbourhood work does each require? | candidates, distance computations, cells |
| RQ9 | Do synthetic conclusions hold on real point data? | same metrics, real datasets (separate study) |
| RQ10 | How close to OPT on small instances? | `empirical_ratio` (separate `exact_small` study) |

## 2. Hypotheses

**No directional hypotheses are pre-registered.** The research questions are
comparative and exploratory; tradeoffs (one algorithm faster, another smaller,
a third more robust on some geometry) are valid findings. Results are reported
as estimates with uncertainty, not as confirmatory tests.

## 3. Algorithms

`marathe`, `wan`, `funke`, `li` exactly as implemented at the locked commit;
per-algorithm source hashes are recorded in `environment.json`. Source
verification status at lock time: see `docs/source_audit.md`
(Marathe YES; Funke YES against the 4-page PDF; Wan YES after adding the
§VI.A pruning rule; Li S-MIS PARTIAL, reported as "S-MIS connector phase with
centralized Wan-level MIS").
* **Li S-MIS:** the paper's `(4.8 + ln 5)·opt + 1.2` bound is **not claimed**
  for v1; it is stated only as conditional on Lemma 2. The proof sketch in
  `docs/algorithms/li_smis.md` is a project argument awaiting review and does
  not affect any experimental result.
* **Funke:** implementation source is the audited 4-page paper (Figure 1). Its
  private connectivity check was removed from the timed `solve()`;
  connectivity is verified once, untimed, for all four algorithms.
* **Wan:** includes the §VI.A black→gray pruning rule.

### 3a. Pre-final audit change: implementation efficiency, identical outputs

* **Funke** (`Funke.cpp`): Phase III queries only the neighbourhoods of this
  round's new black nodes (red/white → blue) and new blue nodes (white → red,
  parent = minimum-id new blue), instead of every red/white and white vertex
  each round. The rounds, colour rules, termination and exceptions are
  unchanged. Rounds are inherent to the algorithm; the per-round full scan was
  not.
* **Li S-MIS** (`LiSMIS.cpp`): Algorithm A's next grey vertex (larger y, then
  smaller id, thresholds 5→2) is found with a lazy max-heap instead of
  rescanning every grey vertex per selection. Exact because y never
  increases (argument in the source and in `docs/algorithms/li_smis.md`).
* **Equivalence evidence** (required before acceptance):
  `cpp/tests/test_search_equivalence.cpp` compares the current code with
  verbatim copies of the pre-audit code (`cpp/tests/reference/`, generated
  from commit `a5cebd7`) on thousands of random and
  adversarial instances, on both backends, with identity and permuted ids; a
  mutation check confirms the test detects tie-break changes. All
  precision-pilot graphs are also replayed through the new binary and
  compared with the CDSs recorded by the pre-audit build.
* Unchanged: Marathe, Wan, generators, CGAL semantics, timing boundaries,
  validation, metrics, the replicate rule and the experimental design.

## 4. Datasets

* Geometries (frozen 2026-10-06 by the v2 calibration; record
  `experiments/calibration/generator_freeze_v2.json`): uniform,
  **clustered = D3-v2 Gaussian hotspot-plus-background model** (4 hotspots,
  σ = 0.05 · L with L = sqrt(n / density) the window side, hotspot points
  restricted to the window by redrawing, 50% uniform background; see
  `experimental_methodology.md` §6), perturbed_grid (jitter 0.15), corridor
  (width 3.0), **dumbbell** (two squares joined by a neck of width 1.0 and
  length 3.0 in units of r; total area n / density; points uniform over the
  domain). The dumbbell replaces v1 `cluster_bridge` in the primary
  factorial. The v1 clustered (fixed σ = 0.8) and `cluster_bridge`
  generators are kept unchanged in code as rejected pre-freeze designs; no
  study config uses them.
* n ∈ {500, 1000, 2000, 5000, 10000}.
* Density target ∈ **{8, 12}** points per unit area at r = 1.0, for **all**
  geometries, so the primary factorial is complete and balanced (50 cells).
  Density 5 was removed from the primary design: at fixed density the
  connectivity of random geometric / unit disk graphs degrades as n grows
  (the connectivity threshold grows with log n; literature in
  `experimental_methodology.md` §6, to be verified), and the measured
  acceptance at density 5 falls at large n. No acceptance-conditioned rare
  connected graphs are used.
* Optional sparse study (secondary, exploratory, never mixed into the primary
  geometry comparison; `experiments/sparse_density5.json`): density 5 only
  for cells whose acceptance (≥ 18/24) was established in the preregistered
  calibration of that geometry's own generator revision — uniform and
  dumbbell from `generator_calibration_v2_cal_v2_uniform_dumbbell_s0025.json`,
  clustered from `generator_calibration_v2_cal_v2_s005.json`, perturbed_grid
  and corridor (generators unchanged; a reproduction check gave 48/48
  identical graphs) from `generator_calibration_v1.json`. Admitted: uniform,
  dumbbell and perturbed_grid at every n; corridor at n ≤ 2000; clustered at
  no n. All other density-5 cells are recorded as
  `generation_infeasible_under_protocol`.
* **Generator-freeze gates (locked 2026-10-06T12:01Z, before the clustered
  calibration results were inspected; `experiments/calibration/gates_v1.json`,
  applied mechanically by `python/calibration_gates.py`):**

  | Gate | Rule |
  | --- | --- |
  | G1 Connectivity | ≥ 18/24 validation graphs connected in every primary cell (Wilson 95% CI reported, not a pass/fail rule) |
  | G2 Clustering identity | D3 median clustering share ≥ 1.5 × uniform's at the same (n, density), and D3 Q1 > uniform Q3 (D3 vs uniform only) |
  | G3 Degree regime | R(n) = D3 / uniform mean degree ≤ 4 in every cell; within each density max_n R / min_n R ≤ 2 |
  | Sparse admission | ≥ 18/24 connected at density 5 |

  A failing gate is never loosened; the generator is redesigned and
  re-calibrated on new independent seeds against the same gates. Recorded in
  advance: with fixed σ and n/8 points per hotspot, D3's same-hotspot degree
  grows ~Θ(n), so G3 was expected to fail.
* **Primary-geometry requirements** (`primary_geometry_requirements_v1.json`,
  written ~12:09Z, before any redesign candidate existed): R1 density
  response, median mean degree at density 12 / density 8 ≥ 1.25 at every n;
  R2 scale stability, max / min over n of the median mean degree ≤ 2 within
  each density; R3 bottleneck character, corridor width ≤ r and < 10% of the
  points in the corridor at every n.
* **Generator freeze v2 outcome** (rules in `generator_definitions_v2.json`,
  written before the v2 calibration; applied by
  `python/calibration_v2_decision.py` on fresh seeds 20261107; output
  unedited in `generator_calibration_v2_decision.txt`): D3-v2 ladder
  s ∈ {0.025, 0.035, 0.05} — only s = 0.05 passes G1, G2, G3, R1, R2 and is
  selected (rule: highest minimum G2 ratio among passing values). The
  dumbbell passes G1, R1, R2, R3 on its single allowed calibration. Margins
  are thin in places (D3 R2 = 1.88 vs 2; worst G1 cell 20/24); the rules
  were locked first, so they do not reopen the selection.
* **Provenance disclosures.** (a) The `recorded_utc` values in
  `generator_definitions_v2.json` (13:05Z) and
  `primary_geometry_requirements_v1.json` (12:40Z) were entered manually
  and are wrong; they are kept, with correction notes giving the actual
  order (file times and session transcript). (b) R3 was proposed in
  discussion as "width < r" and locked as "width ≤ r"; the single dumbbell
  candidate (w = 1.0) was then chosen and sits exactly on the bound. Under
  the strict wording it would have failed R3. The rule as locked before
  calibration is applied unchanged (owner's decision).
* Generator parameters are frozen after calibration; calibration evidence
  (acceptance, clustering share, degree statistics, nearest-neighbour
  distance on independent validation seeds) is version-controlled.
* Observed degree statistics are recorded; the target is not assumed to be
  achieved.
* **Replicate-count selection — LOCKED: 36 independent graphs per cell.** The final number of independent graph instances per
  experimental cell will be selected using a clean precision pilot performed
  before the final experimental freeze. Candidate replicate counts are
  k ∈ {20, 28, 36, 44, 52}, preserving exact Williams execution-order balance
  for the four algorithms at every candidate level. For each k, paired
  confidence intervals are computed for the preregistered CDS-quality and
  runtime comparisons across the required pilot strata, covering all primary
  geometries, densities 8 and 12, and representative graph sizes. The
  selected replicate count is the smallest k satisfying the preregistered
  precision-width requirements. Point-estimate trajectories across
  increasing k are reported as a non-binding diagnostic and do not affect
  selection. If k = 52 does not satisfy the required precision thresholds,
  no replicate count is selected and the study stops for an explicit
  protocol decision before final data collection. Details
  (`experiments/precision/replicate_rule_v1.json`, recorded 13:20:56Z from
  the system clock; amended twice before any pilot data, with the reasons
  kept in its `amendments` record; applied by `python/replicate_decision.py`).
  * Pilot (`experiments/precision_pilot.json`): every primary geometry ×
    n ∈ {500, 2000, 10000} × both densities {8, 12}, 52 independent graphs
    per cell, the final study's measurement protocol (CGAL, Williams order,
    5 timed repetitions + 1 warmup), run under the machine-preparation
    checklist.
  * Ladder k ∈ {20, 28, 36, 44, 52}: every level is a multiple of 4, so the
    Williams order (row = (replicate − 1 + cell offset) mod 4) is exactly
    position-balanced for the first k replicates of every cell.
  * At each k, using replicates 1..k only, for all 6 algorithm pairs in every
    pilot cell: the Student-t 95% CI half-width of the paired CDS-fraction
    difference |D_A|/n − |D_B|/n (percentage points), and of the paired log
    runtime ratio ln(T_A/T_B), reported as a multiplicative half-width
    exp(h) − 1 (T = median of the graph's timed repetitions).
  * Narrow enough at k iff in **every (geometry, density) stratum** (densities
    never pooled): ≥ 90% of comparisons have CDS half-width ≤ 1 pp and none
    exceeds 2 pp, and ≥ 90% have runtime half-width ≤ 10% and none exceeds
    20%.
  * Selection: the smallest narrow-enough k. If even k = 52 fails, the result
    is reported as "precision target not met" with every failing comparison;
    52 is not declared sufficient, and the final experiment stops for a
    protocol decision.
  * No stability criterion: a "< 15% CI-width improvement per step" test was
    removed before any data because it mostly measures 1/√k arithmetic
    (simulated pass probability for k = 28 across all strata ≈ 0.05; 36+
    always passes). A nested "k+8 estimate inside the k CI" test was rejected
    because cumulative estimates share observations. Point-estimate
    trajectories across k are plotted as a **non-binding** diagnostic.
  * **Outcome** (`experiments/precision/replicate_selection_v1.json`, with
    SHA-256 of the rule, decision tool, pilot config, decision output and
    its input; byte-identical copies of the decision output, its input
    `graph_level.csv`, the fairness report and the environment record are
    committed under `experiments/precision/`): the clean pilot ran from
    commit `4e03a2c` with no local changes, uninterrupted, from an empty
    study directory (1,560 graphs, 30 cells, 31,200 timed runs, all valid;
    fairness PASS with 0 violations and 0 warnings; 0 failures). k = 20
    and 28 failed; **36 was the first k to pass in every stratum** (44 and
    52 also pass). Runtime precision was binding: at k = 28 only 15/18
    clustered comparisons per density were within ±10%, all involving
    Funke at n = 2000 and 10000. CDS-fraction precision already passed at
    k = 20 (max half-width 0.46 pp against 1 pp). `final.json` and the
    sparse study use 36.
  * Methods statement: "Each primary experimental cell uses 36 independently
    generated graph instances. This replicate count was selected before
    final data collection using a preregistered precision pilot with exact
    Williams execution-order balance; 36 was the smallest candidate count
    for which all required CDS-quality and runtime confidence-interval
    precision criteria were satisfied across all pilot strata."
* The graph instance is the statistical unit; timing repetitions on one graph are
  technical replicates, summarised by their median, and never counted as
  additional samples. Results are reported as distributions, paired effects
  and confidence intervals.
* Seeds: `study_seed = 20261101`; graph seed = first 63 bits of
  SHA-256("graph", study_seed, geometry, n, density, radius, replicate, attempt).

## 5. Connectivity rule and exclusion criteria (declared in advance)

* Rule: `resample_until_connected`, at most 80 attempts per (cell, replicate).
  Every attempt is logged in `generation_attempts.csv` with its component
  count. The acceptance rate per cell is reported alongside results, because
  the conditioned population (connected instances) differs from the raw
  generator's distribution.
* A (cell, replicate) with no connected instance in 80 attempts is recorded as
  `connectivity_retry_exhausted` and reported; it is not replaced.
* **Generation-infeasible cells** are excluded *before* generation and
  recorded as `generation_infeasible_under_protocol` (never as a retry or
  algorithm failure): under the preregistered generator parameters and
  connectivity-attempt policy, these cells have negligible probability of
  yielding a connected instance and are excluded before algorithm evaluation.
  The check (`study.datasets.generation_feasibility`) bounds Gaussian cluster
  coordinates at 6 sigma (P < 2e-9 per coordinate); it is not a claim of
  mathematical impossibility. Generator parameters are never changed to
  rescue a cell. The dumbbell check is deterministic: the locked domain
  is defined only if n / density > w · l and the square side a ≥ w. This
  excludes 8 of the 9 dumbbell cells of `exact_small` (only n = 16, density 3
  remains); no cell of the final study is affected. Calibration-gated
  exclusions (sparse study only) carry the measured acceptance as the
  reason. Table note: "Dumbbell instances are omitted from the exact-small
  regime wherever the fixed-neck domain cannot be formed at that n and
  density; these cells are excluded prior to algorithm evaluation."
* No other exclusions. "Graph cannot be generated" is never conflated with
  "MCDS algorithm could not find a solution". Outlier repetitions are not removed; the per-graph
  median is the robust summary.

## 6. Hard invariant and spatial backend

The input is a set of n points; the unit disk graph is never constructed or
stored explicitly at any point (see `docs/experimental_methodology.md` §0,
enforced by `python/tests/test_implicit_graph_guard.py`).


All primary comparisons use a common CGAL-backed spatial-query interface
(`spatial_backend = "cgal"`, CGAL 6.1.2 `Kd_tree` + `Fuzzy_sphere` radial-search candidate
retrieval; adjacency decided by the exact predicate `distanceSquared <= r²`).
An independently implemented uniform-grid backend and a brute-force geometric
reference are used for differential validation (every graph is cross-checked
against the grid before it is run) and for the optional backend-sensitivity
study. A final config with any other backend is rejected, and there is no
fallback if CGAL is unavailable.

## 7. Timing methodology

As in `docs/experimental_methodology.md`: Release build, `instrumentation=none`,
shared process per graph, 1 warmup + 5 timed repetitions interleaved across
algorithms, Williams-design order, timer around `solve()` only, timeout
3600 s per graph step. The warmup execution is logged (`phase = warmup`) for
audit only and is never used in any statistic.

**Machine preparation (locked).** Final benchmarks are executed on the same
machine using the Release build and identical compiler settings. The machine
is connected to AC power and uses the same Windows power mode for every study.
Nonessential foreground applications, development tools, cloud-sync activity,
downloads and other user workloads are closed before benchmarking. Security
software is not disabled. The system is allowed to idle before the study
begins, and only one study process is intentionally executed at a time.
Dataset generation, file I/O, validation, plotting and shared connectivity
checks are excluded from `algorithm_ms`. Algorithm execution order follows the
seeded Williams-design schedule. Hardware, OS, power plan, compiler,
dependency versions, Git commit and configuration hash are recorded
automatically with the study (`environment.json`, `methodology_manifest.json`).

## 8. Metrics

Taxonomy as in `docs/experimental_methodology.md` §5 and
`python/study/schema.py METRIC_TAXONOMY`.
Primary: `valid_solution`, `t_algorithm_ms`, `cds_size`, `cds_fraction`.
Secondary: `algorithm_incremental_peak_bytes`, `final_representation_bytes`,
`index_build_peak_bytes`, `pipeline_peak_bytes` (definitions locked in
`experimental_methodology.md` §5), `t_spatial_index_ms`,
`neighbor_queries`, `neighbors_returned`, `cds_diameter`, `empirical_ratio`
(exact_small study only).
Diagnostic: `core_count`, `connector_count`, validity components,
`max_neighbors_per_query`. Backend-specific diagnostics (`cgal_*`, `grid_*`,
`index_bytes`) are reported within one backend only.

## 9. Statistical analysis

Exactly as implemented in `python/study/analysis.py`:
unit = graph; per-graph median runtime; per cell × algorithm descriptives with
95% percentile-bootstrap CIs (B = 2000, seeded); Wilson CIs for validity;
paired comparisons on identical graphs for `t_algorithm_ms`, `cds_size`,
`cds_fraction` and `cds_diameter` (difference with bootstrap CI, Cohen's d_z,
wins/ties/losses; runtime also as geometric-mean ratio with bootstrap CI).
No hypothesis tests, no pooling across cells. Scaling is described per
geometry × density; any fitted exponent (if added) is exploratory.

## 10. Planned tables and figures

Tables: per-cell summary (median [IQR], CI) for CDS size, fraction, runtime;
validity table; paired-comparison table; generation acceptance table.
Figures: runtime / CDS size / CDS fraction / queries / candidates / distance
computations / memory vs n (per density, faceted by geometry); the same vs
density (per n); by geometry; runtime vs mean degree; CDS fraction vs mean
degree; runtime vs neighbour operations; validity rate; per-cell Pareto
(CDS size vs T_algorithm, CDS size vs neighbour queries, CDS fraction vs
T_algorithm, empirical ratio vs T_algorithm); empirical ratio vs n
(exact_small study); CDS diameter by geometry.
Every figure states the number of graphs per point.

## 11. Reporting constraints

* Theoretical guarantees are attributed to the papers' algorithms only, and
  only after primary-source verification; never to our implementations.
* `empirical_ratio` is labelled EMPIRICAL APPROXIMATION RATIO. Exact-solver
  timeouts/errors are reported (`exact_status`); such graphs keep their
  heuristic rows.
* No novelty ("first …") claim until the literature search in
  `docs/related_work_matrix.md` is complete.
* Runtime differences are reported as properties of *these implementations*
  (centralised simulations), not of the distributed algorithms.

## 12. Freeze procedure

1. Replicate count chosen from the precision pilot and written into
   `experiments/final.json`; cells reviewed; `METHODOLOGY_VERSION` in
   `python/study/__init__.py` set to the lock label.
2. Run the full test suites; commit; `git tag -a v1.0-final-experiment`.
3. `py -3 python/run_study.py reproduce --config experiments/final.json`
   on a clean tree (the runner refuses otherwise).
4. Archive `results/studies/final/` with its `methodology_manifest.json`.
5. Any later change to scientific semantics requires a new experiment
   revision (new tag, new `study_id`).
