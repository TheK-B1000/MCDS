# v1 Final Experiment Protocol (pre-registered)

**Status: NOT YET LOCKED.** Decisions recorded on 2026-10-05 stand (no
directional hypotheses, CGAL as the primary backend, machine preparation,
Li bound not claimed). Still open before the lock: the replicate count
(justified by the precision pilot, §4) and the final review of the
experimental cells. When locked, the protocol and code are tagged together
(e.g. `v1.0-final-experiment`; no such tag exists yet). From the first final
run onward, nothing below may be changed in response to results. A scientific change (algorithm semantics,
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

## 4. Datasets

* Geometries: uniform, clustered (4 clusters, spread 0.8), perturbed_grid
  (jitter 0.15), corridor (width 3.0), cluster_bridge (3 clusters, spread
  0.45, bridge fraction 0.2, width 0.6) — v1 generator parameters, unchanged.
* n ∈ {500, 1000, 2000, 5000, 10000}.
* Density target ∈ {5, 8, 12} points per unit area at r = 1.0. Observed
  degree statistics are recorded; the target is not assumed to be achieved.
* **Replicates: OPEN — chosen from the precision pilot before the lock.**
  `experiments/precision_pilot.json` collects 40 independent graphs per
  representative cell; `precision_curve.csv` reports the 95% CI half-width
  of the paired differences ΔCDS = |D_A| − |D_B| and ΔT = T_A − T_B using the
  first k = 5, 10, 15, 20, 25, 30, 40 graphs. The final count is the smallest
  multiple of 4 at which those half-widths have stabilised (documented with
  the numbers in `methodology_audit.md`). `final.json` currently holds a
  placeholder (20). A multiple of 4 keeps execution positions exactly
  balanced within each cell. The graph
  instance is the statistical unit; timing repetitions on one graph are
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
* A graph is excluded from *paired* analyses only if some algorithm produced
  no timed result (error / timeout); such graphs are listed. Invalid CDSs are
  **not** excluded — they are an RQ1 outcome.
* No other exclusions. Outlier repetitions are not removed; the per-graph
  median is the robust summary.

## 6. Spatial backend

All primary comparisons use a common CGAL-backed spatial-query interface
(`spatial_backend = "cgal"`, CGAL 6.1.2 `Kd_tree` + `Fuzzy_iso_box` candidate
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
Secondary: `heap_peak_additional_bytes`, `t_spatial_index_ms`,
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
