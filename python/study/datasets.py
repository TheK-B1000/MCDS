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
