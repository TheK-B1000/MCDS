"""Study configuration: strict loading, defaults, validation, hashing.

Unknown keys are errors, not warnings: a misspelt key that silently falls back
to a default would change the methodology without anyone noticing.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

KNOWN_ALGORITHMS = ("marathe", "wan", "funke", "li")
KNOWN_GEOMETRIES = ("uniform", "clustered", "perturbed_grid", "corridor", "cluster_bridge")
INSTRUMENTATION_LEVELS = ("none", "basic", "detailed")
CONNECTIVITY_MODES = ("resample_until_connected", "accept_all")
PROCESS_MODES = ("shared", "isolated")
EXACT_HARD_MAX_N = 20

# Parameters `generators.generate` accepts (density is a factor, not a param).
GENERATOR_PARAMETERS = {
    "width", "height", "region", "clusters", "spread", "spacing", "jitter",
    "corridor_width", "bridge_fraction", "bridge_width",
}

DEFAULTS: dict[str, Any] = {
    "description": "",
    "final": False,
    "algorithms": list(KNOWN_ALGORITHMS),
    "connectivity_rule": {"mode": "resample_until_connected", "max_attempts": 50},
    "timing": {
        "repetitions": 5,
        "warmups": 1,
        "instrumentation": "none",
        "process_mode": "shared",
        "validate": "all",
        "timeout_seconds": 1800,
    },
    "memory_probe": True,
    "counter_pass": "basic",
    "exact": {"max_n": 0},
    "keep_rejected_datasets": False,
    "output_dir": None,
}

TOP_LEVEL_KEYS = set(DEFAULTS) | {"study_id", "study_seed", "synthetic", "external"}
SYNTHETIC_KEYS = {"geometries", "sizes", "densities", "radius", "replicates", "geometry_parameters"}
EXTERNAL_KEYS = {"datasets"}
EXTERNAL_DATASET_KEYS = {"name", "path", "radii", "units", "source_path", "notes"}
TIMING_KEYS = set(DEFAULTS["timing"])


class ConfigError(ValueError):
    pass


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def _unknown(keys: set[str], allowed: set[str], where: str) -> None:
    extra = sorted(keys - allowed)
    if extra:
        raise ConfigError(f"unknown key(s) in {where}: {extra}")


def resolve(raw: dict[str, Any]) -> dict[str, Any]:
    _unknown(set(raw), TOP_LEVEL_KEYS, "config")
    cfg = _merge(DEFAULTS, raw)

    for key in ("study_id", "study_seed"):
        if key not in cfg:
            raise ConfigError(f"missing required key {key!r}")
    if not isinstance(cfg["study_seed"], int):
        raise ConfigError("study_seed must be an integer")
    if not str(cfg["study_id"]).replace("_", "").replace("-", "").isalnum():
        raise ConfigError("study_id may contain only letters, digits, '-' and '_'")

    algos = cfg["algorithms"]
    if not algos or len(set(algos)) != len(algos):
        raise ConfigError("algorithms must be a non-empty list without duplicates")
    for a in algos:
        if a not in KNOWN_ALGORITHMS:
            raise ConfigError(f"unknown algorithm {a!r}")

    has_syn = "synthetic" in cfg
    has_ext = "external" in cfg
    if has_syn == has_ext:
        raise ConfigError("exactly one of 'synthetic' or 'external' is required")

    if has_syn:
        syn = cfg["synthetic"]
        _unknown(set(syn), SYNTHETIC_KEYS, "synthetic")
        for key in ("geometries", "sizes", "densities", "replicates"):
            if key not in syn:
                raise ConfigError(f"synthetic.{key} is required")
        syn.setdefault("radius", 1.0)
        syn.setdefault("geometry_parameters", {})
        for g in syn["geometries"]:
            if g not in KNOWN_GEOMETRIES:
                raise ConfigError(f"unknown geometry {g!r}")
        for g, params in syn["geometry_parameters"].items():
            if g not in KNOWN_GEOMETRIES:
                raise ConfigError(f"geometry_parameters for unknown geometry {g!r}")
            _unknown(set(params), GENERATOR_PARAMETERS, f"geometry_parameters.{g}")
        if int(syn["replicates"]) < 1:
            raise ConfigError("synthetic.replicates must be >= 1")
        if any(int(n) <= 0 for n in syn["sizes"]) or any(float(d) <= 0 for d in syn["densities"]):
            raise ConfigError("sizes and densities must be positive")
        if not float(syn["radius"]) > 0:
            raise ConfigError("synthetic.radius must be positive")
    else:
        ext = cfg["external"]
        _unknown(set(ext), EXTERNAL_KEYS, "external")
        if not ext.get("datasets"):
            raise ConfigError("external.datasets must be a non-empty list")
        names = set()
        for entry in ext["datasets"]:
            _unknown(set(entry), EXTERNAL_DATASET_KEYS, "external.datasets[]")
            for key in ("name", "path", "radii", "units"):
                if key not in entry:
                    raise ConfigError(f"external dataset entry missing {key!r} (radius per dataset is mandatory)")
            if entry["name"] in names:
                raise ConfigError(f"duplicate external dataset name {entry['name']!r}")
            names.add(entry["name"])
            if not entry["radii"] or any(not float(r) > 0 for r in entry["radii"]):
                raise ConfigError(f"{entry['name']}: radii must be positive")

    rule = cfg["connectivity_rule"]
    if rule.get("mode") not in CONNECTIVITY_MODES:
        raise ConfigError(f"connectivity_rule.mode must be one of {CONNECTIVITY_MODES}")
    if rule["mode"] == "resample_until_connected" and int(rule.get("max_attempts", 0)) < 1:
        raise ConfigError("connectivity_rule.max_attempts must be >= 1")
    if has_ext and rule["mode"] == "resample_until_connected":
        # Real data cannot be resampled; disconnected inputs are recorded, never fixed silently.
        cfg["connectivity_rule"] = {"mode": "accept_all"}

    timing = cfg["timing"]
    _unknown(set(timing), TIMING_KEYS, "timing")
    if timing["instrumentation"] not in INSTRUMENTATION_LEVELS:
        raise ConfigError(f"timing.instrumentation must be one of {INSTRUMENTATION_LEVELS}")
    if timing["process_mode"] not in PROCESS_MODES:
        raise ConfigError(f"timing.process_mode must be one of {PROCESS_MODES}")
    if timing["validate"] not in ("all", "first"):
        raise ConfigError("timing.validate must be 'all' or 'first'")
    if int(timing["repetitions"]) < 1 or int(timing["warmups"]) < 0:
        raise ConfigError("timing.repetitions >= 1 and timing.warmups >= 0")
    if cfg["counter_pass"] not in (None, "basic", "detailed"):
        raise ConfigError("counter_pass must be null, 'basic' or 'detailed'")
    max_n = int(cfg["exact"].get("max_n", 0))
    if not 0 <= max_n <= EXACT_HARD_MAX_N:
        raise ConfigError(f"exact.max_n must be within [0, {EXACT_HARD_MAX_N}] (exhaustive search)")

    if not cfg["output_dir"]:
        cfg["output_dir"] = f"results/studies/{cfg['study_id']}"
    return cfg


def load(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        raw = json.load(handle)
    if not isinstance(raw, dict):
        raise ConfigError("config must be a JSON object")
    return resolve(raw)


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def config_sha256(cfg: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(cfg).encode("utf-8")).hexdigest()
