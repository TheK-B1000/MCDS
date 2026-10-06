"""Automatic detection of unfair or pseudo-replicated comparisons.

Violations (study FAILS):
  V1  rows of one graph disagree on points fingerprint / dataset hash / radius
  V2  rows of one graph disagree on solver, commit, machine, config or build
  V3  algorithms received different numbers of timed repetitions or warmups
      on the same graph, or different instrumentation for the same phase
  V4  two accepted replicates of a synthetic study share a dataset (pseudo-
      replication) — the old ``base_seed + attempt`` failure mode
  V5  a timed row was produced with instrumentation other than the config's
  V6  the bench reported a points fingerprint different from Python's

  V7  a row was produced with a spatial backend the config did not request
  V8  a graph's backend cross-check against the independent grid was not
      "identical" (CGAL / explicit neighbour sets must equal the grid's)
  V9  the same algorithm returned a different CDS on the same graph under
      different spatial backends (backend choice changed the graph)

Warnings (reported, study does not fail):
  W1  a graph is missing an algorithm's timed rows (e.g. timeout) — the graph
      is excluded from paired analyses, as pre-declared in the protocol
  W2  execution positions are imbalanced beyond the Williams-design ideal
  W3  a deterministic algorithm returned different CDS hashes across reps
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from .config import backends as config_backends
from .schema import PHASE_MEMORY, PHASE_TIMED, PHASE_WARMUP

_GRAPH_INVARIANTS = ("points_fingerprint", "dataset_sha256", "radius")
_ENV_INVARIANTS = ("solver_sha256", "git_commit", "machine_id", "config_sha256", "build_config")


def check(tables: dict[str, list[dict[str, Any]]], cfg: dict[str, Any]) -> dict[str, Any]:
    raw = tables["raw_runs"]
    datasets = tables["datasets"]
    violations: list[str] = []
    warnings: list[str] = []
    algos = list(cfg["algorithms"])
    expected_instr = cfg["timing"]["instrumentation"]
    allowed_backends = set(config_backends(cfg))

    by_graph: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in raw:
        by_graph[r["graph_id"]].append(r)

    ds_fp = {d["graph_id"]: d["points_fingerprint"] for d in datasets}

    complete_graphs = 0
    for gid, rows in by_graph.items():
        for key in _GRAPH_INVARIANTS:
            values = {str(r.get(key)) for r in rows}
            if len(values) > 1:
                violations.append(f"V1 graph {gid}: {key} differs across rows {sorted(values)}")
        # Memory probes come from the separate heap-tracking binary, so the
        # environment invariants are checked within each binary's rows.
        for is_probe in (False, True):
            group = [r for r in rows if (r["phase"] == PHASE_MEMORY) == is_probe]
            for key in _ENV_INVARIANTS:
                values = {str(r.get(key)) for r in group}
                if len(values) > 1:
                    violations.append(f"V2 graph {gid}: {key} differs across {'memory-probe' if is_probe else 'timing'} rows {sorted(values)}")
        fps = {r["points_fingerprint"] for r in rows}
        if gid in ds_fp and fps != {ds_fp[gid]}:
            violations.append(f"V6 graph {gid}: bench fingerprint {sorted(fps)} != python {ds_fp[gid]}")

        used = {r.get("spatial_backend") for r in rows}
        if not used <= allowed_backends:
            violations.append(f"V7 graph {gid}: rows from unrequested backend(s) {sorted(map(str, used - allowed_backends))}")
        cross = {r.get("backend_crosscheck") for r in rows}
        if not cross <= {"identical", "not_applicable"}:
            violations.append(f"V8 graph {gid}: backend cross-check status {sorted(map(str, cross))}")

        # Symmetry is required within each backend: every algorithm gets the
        # same repetitions, warmups and instrumentation on the same backend.
        for backend in sorted(map(str, used)):
            brows = [r for r in rows if str(r.get("spatial_backend")) == backend]
            for phase in (PHASE_TIMED, PHASE_WARMUP):
                counts = Counter(r["algorithm"] for r in brows if r["phase"] == phase)
                present = {a: counts.get(a, 0) for a in algos}
                nonzero = {v for v in present.values() if v}
                if len(nonzero) > 1:
                    violations.append(f"V3 graph {gid} [{backend}]: unequal {phase} repetitions {present}")
                if phase == PHASE_TIMED and any(v == 0 for v in present.values()):
                    missing = [a for a, v in present.items() if v == 0]
                    warnings.append(f"W1 graph {gid} [{backend}]: no timed rows for {missing}; "
                                    "excluded from paired analysis")
                instr = {r["instrumentation"] for r in brows if r["phase"] == phase}
                if len(instr) > 1:
                    violations.append(f"V3 graph {gid} [{backend}]: mixed instrumentation in phase {phase}: {sorted(instr)}")
                if phase == PHASE_TIMED and instr and instr != {expected_instr}:
                    violations.append(f"V5 graph {gid} [{backend}]: timed rows used instrumentation {sorted(instr)}, "
                                      f"config says {expected_instr}")
            if all(any(r["algorithm"] == a and r["phase"] == PHASE_TIMED for r in brows) for a in algos):
                complete_graphs += 1

        hashes: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
        for r in rows:
            if r.get("cds_hash"):
                hashes[r["algorithm"]][str(r.get("spatial_backend"))].add(r["cds_hash"])
        for a, per_backend in hashes.items():
            for backend, hs in per_backend.items():
                if len(hs) > 1:
                    warnings.append(f"W3 graph {gid} [{backend}]: {a} returned {len(hs)} different CDSs across executions")
            if len(per_backend) > 1 and len(set().union(*per_backend.values())) > 1:
                violations.append(f"V9 graph {gid}: {a} returned different CDSs under backends {sorted(per_backend)}")

    if "synthetic" in cfg:
        owners: dict[str, list[str]] = defaultdict(list)
        for d in datasets:
            if d.get("graph_status") == "ok":
                owners[d["dataset_sha256"]].append(d["dataset_id"])
        for sha, ids in owners.items():
            if len(ids) > 1:
                violations.append(f"V4 dataset {sha[:12]} shared by replicates {ids} (pseudo-replication)")

    # Position balance over timed rows (one order per graph).
    positions: dict[str, Counter] = defaultdict(Counter)
    seen = set()
    for r in raw:
        if r["phase"] != PHASE_TIMED:
            continue
        key = (r["graph_id"], r.get("spatial_backend"), r["algorithm"])
        if key in seen:
            continue
        seen.add(key)
        positions[r["algorithm"]][int(r["execution_position"])] += 1
    balance = {a: dict(sorted(c.items())) for a, c in positions.items()}
    if positions and cfg["timing"]["process_mode"] == "shared":
        k = len(algos)
        for a, c in positions.items():
            counts = [c.get(i, 0) for i in range(k)]
            if max(counts) - min(counts) > 1 and max(counts) > 0:
                total = sum(counts)
                # Perfect balance needs graphs to be a multiple of the row count.
                if max(counts) - min(counts) > max(1, total // (2 * k)):
                    warnings.append(f"W2 {a}: execution positions imbalanced {counts}")

    return {
        "passed": not violations,
        "violations": violations,
        "warnings": warnings,
        "graphs_with_rows": len(by_graph),
        "graph_backend_pairs_complete_for_all_algorithms": complete_graphs,
        "execution_position_balance": balance,
    }
