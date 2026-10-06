# Readiness report — before the clean precision pilot

Date: 2026-10-06. State: working tree on `main` (committed with this report),
**not tagged**. The final study has **not** been run. The next step is the
clean precision pilot; after it come the replicate count, the `final.json`
lock, the `v1.0-final-experiment` tag and the final runs, in that order.

## 1. Verdict

Ready for the clean precision pilot. Remaining open items, all deliberate and
scheduled:

* `final.json` `synthetic.replicates` is a placeholder (20) until the pilot
  selects k mechanically.
* The literature rows in `experimental_methodology.md` §6 are still marked
  "to verify" (none is cited as established).
* There is no final tag yet.

## 2. What changed since the last commit (0ee1860)

| Area | Change | Evidence |
| --- | --- | --- |
| Generators (frozen v2) | clustered = **D3-v2** (σ = 0.05·L, hotspots kept in the window); **dumbbell** (neck 1.0 × 3.0, area n/density) replaces `cluster_bridge` in the primary factorial; v1 generators kept unchanged for regression only | `experiments/calibration/generator_freeze_v2.json`, `generator_calibration_v2_decision.txt` (unedited script output) |
| Generator decision | locked gates G1–G3, requirements R1–R3, locked ladder and selection rule, fresh seeds 20261107; only s = 0.05 passes; dumbbell passes its single allowed calibration | `python/calibration_v2_decision.py` |
| Configs | all 7 study configs use D3-v2 + dumbbell; primary densities {8, 12}; new separate `sparse_density5.json` | `FrozenConfigTests` |
| Feasibility | dumbbell domain rule (n/density > w·l and a ≥ w), recorded as `generation_infeasible_under_protocol`: excludes 8/9 exact_small dumbbell cells, none elsewhere | `DumbbellFeasibilityTests`, `run_study.py plan` |
| Sparse admission | `feasibility_calibration` accepts per-geometry entries, so each geometry is judged by the calibration of its own generator revision; v1 evidence for the unchanged generators reproduced 48/48 graphs identically | `test_entry_list_*`, `test_sparse_admission_matches_the_freeze_decision` |
| Implicit-graph invariant | `--show-cds-edges` / `--no-cds-edges` / `--edge-k-limit`, the `cds_edges` helper, the GUI toggle and the legend entry removed: the plot draws points only. A C++ test oracle that stored Li's distance-2 graph H now evaluates it on demand. **No exceptions remain** | `test_visualization_draws_no_edges` |
| Guard | static tripwire extended to every C++/Python source incl. tests and test oracles, with 10 + 10 pattern families; it flags all three pre-change files (14 / 1 / 4 hits) | `test_tripwire_flags_known_violations` |
| Replicate rule | locked before the pilot: ladder 20/28/36/44/52 (exact Williams balance), Student-t CIs of paired CDS-fraction differences and log runtime ratios, narrowness in every (geometry, density) stratum, **stop** if 52 fails; trajectories plotted as a non-binding diagnostic | `experiments/precision/replicate_rule_v1.json`, `python/replicate_decision.py`, `test_replicate_decision.py` |
| Pilot config | 5 geometries × n {500, 2000, 10000} × densities {8, 12} × 52 graphs (1,560 graphs, 30 cells), final-study timing protocol | `test_pilot_config_matches_rule` |

## 3. Verification

* C++: 12/12 tests pass (Release, MSVC 2022, CGAL 6.1.2 / Boost 1.88);
  rebuilt after the oracle change; no compiler warnings.
* Python: 119 tests, all pass except one opt-in skip (the 10⁶-point
  infrastructure smoke, `MCDS_MILLION_TEST=1`).
* Behavioural guard: on a graph with 2,779,178 edges (explicit CSR ≈ 22.3 MB)
  the whole-process lifetime heap peak was 582 KB (CGAL) / 419 KB (grid).
* End-to-end on the frozen generators (outputs in `results/studies/`; the
  pre-freeze outputs are archived in `results/prefreeze_v1_generators/`):
  * smoke: fairness PASS, 40/40 solutions valid. The 4 W2 warnings are the
    expected ones for 10 single-replicate cells: Williams positions balance
    within a cell only when the replicate count is a multiple of 4.
  * exact_small: fairness PASS with 0 warnings, 888 graphs (37 feasible
    cells × 24), 3,552/3,552 solutions valid, exact OPT obtained for every
    graph, no retry exhaustion.

## 4. Provenance disclosures (also recorded in the files themselves)

1. **Wrong hand-typed timestamps.** `recorded_utc` in
   `generator_definitions_v2.json` (13:05Z) and
   `primary_geometry_requirements_v1.json` (12:40Z) were hand-typed and are
   later than the true write times (≈12:12Z and ≈12:09Z). The values are
   kept, with correction notes. The true order (definitions, then the
   calibration at 12:23Z) is shown by file times and the session transcript.
   The replicate rule's timestamps come from the system clock.
2. **R3 wording.** In discussion, R3 was proposed as "width < r"; it was
   locked as "width ≤ r" without the change being flagged. The single
   dumbbell candidate (w = 1.0) was then chosen by the assistant from two
   proposals. It sits exactly on the bound and would fail the strict
   wording. The rule as locked before calibration is applied (owner's
   decision).
3. **Thin margins.** For D3-v2, R2 is 1.88 against a limit of 2 and the
   worst G1 cell is 20/24. Dumbbell's sparse n = 5000 cell is 18/24. These do
   not reopen the selection.
4. **Replicate-rule amendments, both before any pilot data.**
   * The CI-width-improvement stability test was removed. It mostly measured
     1/√k arithmetic: in simulation k = 28 passes all strata with p ≈ 0.05,
     and 36+ always passes.
   * The fallback to 52 was replaced by an explicit STOP.
   * Both amendments are in the rule's `amendments` record.
5. **The engineering precision pilot was never completed**, so there was
   nothing to archive as `precision_pilot_engineering`. The clean pilot is
   the first one.

## 5. Next: the clean precision pilot (run by the owner)

1. Machine preparation: the checklist in `final_experiment_protocol.md`.
2. `py -3 python/run_study.py run --config experiments/precision_pilot.json`,
   then `analyze`.
3. `py -3 python/replicate_decision.py --study results/studies/precision_pilot
   --json results/studies/precision_pilot/replicate_decision.json --plots
   results/studies/precision_pilot/trajectories`.
   * Exit 0 means the selected k goes into `final.json`.
   * Exit 2 means the precision target was not met at 52: stop for a
     protocol decision.

Expected duration: roughly **8–10 hours**, dominated by the n = 10000 cells.
Measured wall time per n = 10000, density 12 graph (4 algorithms × (5 + 1)
runs) is ≈ 48 s (uniform, dumbbell) and ≈ 79 s (clustered), with Li's
S-MIS phase taking most of it. The pilot has 520 such graphs. It is
resumable if interrupted.

## 6. Outcome (added after the pilot)

The clean precision pilot ran from `4e03a2c`, uninterrupted, and passed every
integrity check. The frozen rule selected **k = 36** (20 and 28 failed; runtime
precision was binding). See `experiments/precision/replicate_selection_v1.json`
and the protocol §4. The protocol was then locked (commit `a5cebd7`).

**Superseded.** A read-only pre-final audit rejected that lock for final runtime
claims (Funke / Li S-MIS full-vertex scans). The protocol is reopened, the
local tag was deleted before being pushed, and the precision pilot will be
re-run after the output-identical fix (`experiments/precision_pilot_rerun.json`).
See `methodology_audit.md`, "Pre-final audit change".
