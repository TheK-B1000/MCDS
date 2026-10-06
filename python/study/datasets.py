"""Dataset planning and generation for MCDS studies.

Every generation attempt is recorded (accepted or rejected, with the reason),
so a reader can see exactly how often a connectivity rule rejected instances
and that no instance was cherry-picked. The acceptance rule is fixed in the
config *before* data collection.
"""

from __future__ import annotations

import json
import math
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import bench as bench_mod
from .fingerprint import file_points_fingerprint, graph_id_for, sha256_file
from .config import backends as config_backends
from .seeds import graph_seed

_PYTHON_DIR = Path(__file__).resolve().parent.parent
if str(_PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(_PYTHON_DIR))

from generators import generate, write_csv  # noqa: E402  (project generators, unchanged)


@dataclass
class PlannedDataset:
    plan_index: int
    dataset_id: str
    cell_id: str
    source_type: str  # "synthetic" | "real"
    geometry: str
    n: int | None
    radius: float
    radius_units: str
    density_target: float | None
    replicate: int
    params: dict[str, Any] = field(default_factory=dict)
    external_path: str | None = None
    source_path: str | None = None

    @property
    def key(self) -> str:
        return re.sub(r"[^A-Za-z0-9_.=-]+", "_", self.dataset_id)


def _fmt(x: float) -> str:
    return repr(float(x))


def plan(cfg: dict[str, Any]) -> list[PlannedDataset]:
    out: list[PlannedDataset] = []
    if "synthetic" in cfg:
        syn = cfg["synthetic"]
        radius = float(syn["radius"])
        for geometry in syn["geometries"]:
            params = dict(syn["geometry_parameters"].get(geometry, {}))
            for n in syn["sizes"]:
                for density in syn["densities"]:
                    cell = f"{geometry}|n={int(n)}|density={_fmt(density)}|r={_fmt(radius)}"
                    for rep in range(1, int(syn["replicates"]) + 1):
                        out.append(PlannedDataset(
                            plan_index=len(out), dataset_id=f"{cell}|rep={rep}", cell_id=cell,
                            source_type="synthetic", geometry=geometry, n=int(n), radius=radius,
                            radius_units="unit", density_target=float(density), replicate=rep,
                            params=params,
                        ))
    else:
        for entry in cfg["external"]["datasets"]:
            for radius in entry["radii"]:
                cell = f"{entry['name']}|r={_fmt(radius)}"
                out.append(PlannedDataset(
                    plan_index=len(out), dataset_id=cell, cell_id=cell, source_type="real",
                    geometry=entry["name"], n=None, radius=float(radius), radius_units=entry["units"],
                    density_target=None, replicate=1, external_path=entry["path"],
                    source_path=entry.get("source_path"),
                ))
    return out


def target_expected_degree(density: float | None, radius: float) -> float | None:
    """Nominal interior expected degree for a homogeneous density (uniform only).

    Reported as a *target*; the observed mean degree is always recorded too,
    and the two differ because of boundary effects and non-uniform geometries.
    """
    return None if density is None else density * math.pi * radius * radius


# Gaussian cluster coordinates are bounded by this many standard deviations in
# the feasibility argument; P(|N(0,1)| > 6) < 2e-9 per coordinate.
FEASIBILITY_SIGMA_BOUND = 6.0


def generation_feasibility(geometry: str, n: int, density: float, radius: float,
                           params: dict[str, Any]) -> tuple[bool, str]:
    """Pre-generation check: can this cell yield a connected UDG under the protocol?

    Only `cluster_bridge` is checked: cluster centres are placed in a row at
    least max(6*spread, 8) apart and round(bridge_fraction*n) bridge points are
    spread evenly along each gap (axial jitter +/- 0.1). A connected graph
    needs, across every gap, a chain of points whose x-coordinates differ by at
    most r. With cluster coordinates bounded at 6 sigma, each point's
    x-coordinate lies in a known interval; if their union leaves a hole wider
    than r, a connected instance requires a cluster coordinate beyond 6 sigma
    (probability < 2e-9 per coordinate). The Gaussian is unbounded, so this is
    NEGLIGIBLE probability, not impossibility. Such cells are excluded before
    generation and recorded as `generation_infeasible_under_protocol`: under
    the preregistered generator parameters and connectivity-attempt policy
    they have negligible probability of yielding a connected instance. This is
    a property of the generator, never of an MCDS algorithm.

    `dumbbell` is checked deterministically: the locked domain (two squares of
    side a = sqrt((n/density - w*l)/2) joined by a w x l neck) is well defined
    only if n/density > w*l and a >= w (the neck attaches within a square's
    side). Otherwise the cell cannot be generated under the protocol.
    """
    if geometry == "dumbbell":
        import math as _m  # noqa: PLC0415

        w = float(params.get("neck_width", 1.0))
        length = float(params.get("neck_length", 3.0))
        area = n / density if density > 0 else 0.0
        if area <= w * length:
            return False, (f"dumbbell at n={n}, density={density:g}: domain area {area:.3f} <= neck area "
                           f"{w * length:g}; the locked domain is not defined")
        a = _m.sqrt((area - w * length) / 2.0)
        if a < w:
            return False, (f"dumbbell at n={n}, density={density:g}: square side {a:.3f} < neck width {w:g}; "
                           f"the locked domain is not defined")
        return True, ""
    if geometry != "cluster_bridge":
        return True, ""
    import math as _m  # noqa: PLC0415

    from generators import UNIT_RADIUS  # noqa: PLC0415

    clusters = int(params.get("clusters", 8))
    spread = float(params.get("spread", 0.5))
    bridge_fraction = float(params.get("bridge_fraction", 0.15))
    gap = max(6.0 * spread, 8.0 * UNIT_RADIUS)
    n_bridge = int(round(n * bridge_fraction))
    gaps = clusters - 1
    reach = FEASIBILITY_SIGMA_BOUND * spread
    for g in range(gaps):
        share = n_bridge // gaps + (1 if g < n_bridge % gaps else 0)
        x0 = g * gap
        intervals = [(x0 - reach, x0 + reach), (x0 + gap - reach, x0 + gap + reach)]
        for k in range(share):
            xk = x0 + (k + 0.5) / share * gap
            intervals.append((xk - 0.1, xk + 0.1))
        intervals.sort()
        covered = intervals[0][1]
        for lo, hi in intervals[1:]:
            if lo - covered > radius:
                hole = lo - covered
                return False, (
                    f"cluster_bridge at n={n}: negligible probability of a connected instance under the "
                    f"protocol: gap {g} between cluster centres ({gap:g} apart) has {share} bridge point(s); "
                    f"the x-projection leaves a hole of {hole:.3f} > r={radius:g} unless a cluster coordinate "
                    f"falls beyond {FEASIBILITY_SIGMA_BOUND:g} sigma (P < 2e-9 per coordinate)")
            covered = max(covered, hi)
        if _m.isnan(covered):
            return False, "invalid parameters"
    return True, ""


def load_calibration(cal: dict[str, Any], repo_root: Path) -> dict[tuple, dict[str, Any]]:
    """Calibration cells keyed by (geometry, n, density, radius); verifies the file hash."""
    import hashlib  # noqa: PLC0415

    path = Path(cal["file"])
    if not path.is_absolute():
        path = repo_root / path
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != cal["sha256"]:
        raise RuntimeError(f"calibration file {path} has sha256 {digest}, config expects {cal['sha256']}")
    doc = json.loads(data.decode("utf-8"))
    return {(c["geometry"], int(c["n"]), float(c["density"]), float(c["radius"])): c for c in doc["cells"]}


def calibration_feasibility(cal: dict[str, Any], repo_root: Path, p: PlannedDataset) -> tuple[bool, str]:
    """A cell is admitted only if preregistered calibration measured its
    connectivity acceptance rate at or above the threshold. Cells the
    calibration did not cover are not admitted. `cal` is one entry or a list of
    entries; an entry with `geometries` speaks only for those geometries."""
    if isinstance(cal, list):
        chosen = [e for e in cal if not e.get("geometries") or p.geometry in e["geometries"]]
        if len(chosen) != 1:
            return False, f"geometry {p.geometry!r} is not covered by exactly one feasibility_calibration entry"
        cal = chosen[0]
    elif cal.get("geometries") and p.geometry not in cal["geometries"]:
        return False, f"geometry {p.geometry!r} is not covered by the calibration entry for {cal['geometries']}"
    cells = load_calibration(cal, repo_root)
    key = (p.geometry, int(p.n or 0), float(p.density_target or 0.0), float(p.radius))
    cell = cells.get(key)
    threshold = float(cal["min_acceptance_rate"])
    if cell is None:
        return False, f"not covered by the preregistered calibration {cal['file']}"
    rate = float(cell["acceptance_rate"])
    if rate < threshold:
        return False, (f"preregistered calibration measured acceptance {cell['connected']}/{cell['graphs']} "
                       f"= {rate:.3f} (Wilson 95% CI {cell['acceptance_wilson_low']:.3f}-"
                       f"{cell['acceptance_wilson_high']:.3f}) < required {threshold:g}")
    return True, ""


def _graph_probe(binary: Path, csv_path: Path, radius: float, backend: str) -> dict[str, Any]:
    """Untimed graph check with the study's primary backend. Fails on a CGAL /
    grid neighbour-set mismatch (the bench cross-checks every graph)."""
    out = bench_mod.run_bench(binary, csv_path, radius, spatial_backend=backend, graph_only=True,
                              timeout_s=3600)
    if not out.ok or out.data is None:
        raise RuntimeError(f"graph probe failed for {csv_path}: {out.error}")
    if out.data.get("backend_crosscheck", {}).get("status") not in ("identical", "not_applicable"):
        raise RuntimeError(f"backend cross-check failed for {csv_path}: {out.data.get('backend_crosscheck')}")
    return out.data


def _attempt_record(p: PlannedDataset, attempt: int, seed: int | None, accepted: bool, reason: str,
                    probe: dict[str, Any], sha: str, fp: str) -> dict[str, Any]:
    g = probe["graph"]
    return {
        "attempt": attempt, "graph_seed": seed, "accepted": accepted, "rejection_reason": reason,
        "connected": g["connected"], "component_count": g["component_count"],
        "largest_component": g["largest_component"], "isolated_count": g["isolated_count"],
        "mean_degree": g["mean_degree"], "dataset_sha256": sha, "points_fingerprint": fp,
    }


def prepare(p: PlannedDataset, cfg: dict[str, Any], repo_root: Path, out_dir: Path, binary: Path) -> dict[str, Any]:
    """Generates/loads one planned dataset and returns its persisted record."""
    rule = cfg["connectivity_rule"]
    record: dict[str, Any] = {"planned": p.__dict__ | {"key": p.key}, "attempts": [], "status": None}

    if p.source_type == "real":
        csv_path = Path(p.external_path or "")
        if not csv_path.is_absolute():
            csv_path = repo_root / csv_path
        if not csv_path.is_file():
            record["status"] = "missing_dataset"
            record["error"] = f"external dataset not found: {p.external_path}"
            return record
        sha = sha256_file(csv_path)
        fp = file_points_fingerprint(csv_path)
        probe = _graph_probe(binary, csv_path, p.radius, config_backends(cfg)[0])
        sidecar_path = csv_path.with_name(csv_path.stem + ".meta.json")
        sidecar = json.loads(sidecar_path.read_text(encoding="utf-8-sig")) if sidecar_path.is_file() else {}
        source_sha = sidecar.get("input_sha256")
        if p.source_path:
            sp = Path(p.source_path) if Path(p.source_path).is_absolute() else repo_root / p.source_path
            if sp.is_file():
                source_sha = sha256_file(sp)
        connected = probe["graph"]["connected"]
        record["attempts"].append(_attempt_record(p, 0, None, True,
                                                  "" if connected else "accepted_disconnected", probe, sha, fp))
        record.update({
            "status": "ok" if connected else "input_disconnected",
            "csv_path": str(csv_path), "dataset_sha256": sha, "points_fingerprint": fp,
            "graph_id": graph_id_for(sha, p.radius), "graph_seed": None, "generation_attempt": 0,
            "probe": probe, "generator_parameters": {},
            "real_metadata": {
                "source_sha256": source_sha,
                "coordinate_system": sidecar.get("output_crs") or sidecar.get("coordinates"),
                "projection": sidecar.get("projection_method"),
                "units": sidecar.get("units") or p.radius_units,
                "sampling": sidecar.get("sampling"),
                "sidecar": sidecar,
            },
        })
        return record

    feasible, reason = generation_feasibility(p.geometry, int(p.n or 0), float(p.density_target or 0.0),
                                              p.radius, p.params)
    if feasible and cfg.get("feasibility_calibration"):
        feasible, reason = calibration_feasibility(cfg["feasibility_calibration"], repo_root, p)
    if not feasible:
        # Excluded before generation: no attempts, no graph, no algorithm run.
        record["status"] = "generation_infeasible_under_protocol"
        record["error"] = reason
        return record

    ds_dir = out_dir / "datasets" / p.geometry
    ds_dir.mkdir(parents=True, exist_ok=True)
    max_attempts = int(rule.get("max_attempts", 1)) if rule["mode"] == "resample_until_connected" else 1
    for attempt in range(max_attempts):
        seed = graph_seed(cfg["study_seed"], p.geometry, int(p.n or 0), float(p.density_target or 0.0),
                          p.radius, p.replicate, attempt)
        gen = generate(p.geometry, int(p.n or 0), seed, density=float(p.density_target or 0.0), **p.params)
        csv_path = ds_dir / f"{p.key}_a{attempt}.csv"
        write_csv(str(csv_path), gen.points)
        sha = sha256_file(csv_path)
        fp = file_points_fingerprint(csv_path)
        probe = _graph_probe(binary, csv_path, p.radius, config_backends(cfg)[0])
        connected = bool(probe["graph"]["connected"])
        accept = connected or rule["mode"] == "accept_all"
        reason = "" if accept else "disconnected"
        record["attempts"].append(_attempt_record(p, attempt, seed, accept, reason, probe, sha, fp))
        if accept:
            record.update({
                "status": "ok" if connected else "input_disconnected",
                "csv_path": str(csv_path), "dataset_sha256": sha, "points_fingerprint": fp,
                "graph_id": graph_id_for(sha, p.radius), "graph_seed": seed, "generation_attempt": attempt,
                "probe": probe, "generator_parameters": gen.parameters,
            })
            return record
        if not cfg.get("keep_rejected_datasets"):
            csv_path.unlink(missing_ok=True)

    record["status"] = "connectivity_retry_exhausted"
    record["error"] = f"no connected instance in {max_attempts} attempts"
    return record
