"""Reproducible experiment runner for implicit-UDG MCDS.

Stages:

1. Generate each unique dataset once (distribution × n × seed × params).
2. Optionally retry with effective_seed = base_seed + attempt until connected.
3. Run every configured algorithm against that same CSV.
4. Append one CSV row per trial (including failures).

Example:

    python python/experiment_runner.py --config experiments/smoke.json
    python python/experiment_runner.py --config experiments/smoke.json --summary
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import platform
import statistics
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None  # type: ignore[misc, assignment]

_PYTHON_DIR = Path(__file__).resolve().parent
if str(_PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(_PYTHON_DIR))

from generators import generate, write_csv  # noqa: E402
from gui_support import (  # noqa: E402
    build_solver_command,
    find_mcds_executable,
    find_repo_root,
    run_solver,
)
from lab_utils import (  # noqa: E402
    atomic_write_json,
    config_sha256,
    detect_build_type,
    log_line,
    machine_provenance,
    sha256_file,
)

EXPERIMENT_COLUMNS = [
    "run_id",
    "algorithm",
    "distribution",
    "n",
    "base_seed",
    "effective_seed",
    "generation_attempt",
    "radius",
    "density",
    "input_connected",
    "component_count",
    "cds_size",
    "cds_ratio",
    "load_ms",
    "index_build_ms",
    "algorithm_ms",
    "validation_ms",
    "total_ms",
    "algorithm_neighbor_queries",
    "algorithm_candidates_examined",
    "peak_memory_mb",
    "valid_dominating",
    "valid_connected",
    "dataset_csv",
    "dataset_sha256",
    "result_json",
    "exit_code",
    "status",
    "error",
]

EXIT_TIMEOUT = 124
EXIT_MEMORY_LIMIT = 125


@dataclass
class DatasetSpec:
    distribution: str
    n: int
    base_seed: int
    radius: float
    params: dict[str, Any] = field(default_factory=dict)

    def key(self) -> str:
        param_blob = json.dumps(self.params, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha1(param_blob.encode("utf-8")).hexdigest()[:8]
        return f"{self.distribution}_n{self.n}_seed{self.base_seed}_{digest}"

    @property
    def density(self) -> float | None:
        value = self.params.get("density")
        return float(value) if value is not None else None


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def dataset_basename(spec: DatasetSpec, effective_seed: int) -> str:
    if effective_seed == spec.base_seed:
        return f"{spec.distribution}_n{spec.n}_seed{spec.base_seed}.csv"
    return f"{spec.distribution}_n{spec.n}_seed{spec.base_seed}_eff{effective_seed}.csv"


def write_sidecar(meta_path: Path, payload: dict[str, Any]) -> None:
    meta_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def measure_peak_memory_mb(
    command: list[str],
    timeout_s: float | None = None,
    max_peak_memory_mb: float | None = None,
) -> tuple[subprocess.CompletedProcess[str], float | None]:
    """Run a child process and estimate peak working-set / RSS in megabytes.

    Windows: polls ``GetProcessMemoryInfo`` WorkingSetSize while the child runs.
    POSIX: polls ``/proc/pid/status`` VmRSS when available, else ``ru_maxrss`` after exit.

    Returns ``(completed_process, peak_memory_mb_or_None)``.
    Exit code 124 = timeout, 125 = memory limit exceeded.
    """
    if platform.system() == "Windows":
        return _measure_peak_memory_windows(command, timeout_s, max_peak_memory_mb)
    return _measure_peak_memory_posix(command, timeout_s, max_peak_memory_mb)


def _read_proc_rss_kb(pid: int) -> int | None:
    status_path = Path(f"/proc/{pid}/status")
    if not status_path.is_file():
        return None
    try:
        for line in status_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1])
            if line.startswith("VmHWM:"):
                return int(line.split()[1])
    except (OSError, ValueError):
        return None
    return None


def _measure_peak_memory_windows(
    command: list[str],
    timeout_s: float | None,
    max_peak_memory_mb: float | None,
) -> tuple[subprocess.CompletedProcess[str], float | None]:
    import ctypes
    from ctypes import wintypes

    class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    PROCESS_QUERY_INFORMATION = 0x0400
    PROCESS_VM_READ = 0x0010
    limit_bytes = None if max_peak_memory_mb is None else int(max_peak_memory_mb * 1024 * 1024)

    psapi = ctypes.WinDLL("psapi")
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    OpenProcess = kernel32.OpenProcess
    OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    OpenProcess.restype = wintypes.HANDLE
    CloseHandle = kernel32.CloseHandle
    CloseHandle.argtypes = [wintypes.HANDLE]
    CloseHandle.restype = wintypes.BOOL
    GetProcessMemoryInfo = psapi.GetProcessMemoryInfo
    GetProcessMemoryInfo.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(PROCESS_MEMORY_COUNTERS),
        wintypes.DWORD,
    ]
    GetProcessMemoryInfo.restype = wintypes.BOOL

    proc = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    handle = OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, proc.pid)
    peak = 0
    deadline = None if timeout_s is None else time.time() + timeout_s
    memory_limited = False
    timed_out = False
    try:
        while True:
            if handle:
                counters = PROCESS_MEMORY_COUNTERS()
                counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
                if GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
                    current = max(int(counters.PeakWorkingSetSize), int(counters.WorkingSetSize))
                    peak = max(peak, current)
                    if limit_bytes is not None and current > limit_bytes:
                        memory_limited = True
                        proc.kill()
                        break
            if proc.poll() is not None:
                break
            if deadline is not None and time.time() > deadline:
                timed_out = True
                proc.kill()
                break
            time.sleep(0.01)
        stdout, stderr = proc.communicate()
        if handle and not memory_limited:
            counters = PROCESS_MEMORY_COUNTERS()
            counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
            if GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
                peak = max(
                    peak,
                    int(counters.PeakWorkingSetSize),
                    int(counters.WorkingSetSize),
                )
        exit_code = proc.returncode if proc.returncode is not None else 1
        if memory_limited:
            exit_code = EXIT_MEMORY_LIMIT
            stderr = (stderr or "") + "\nmemory limit exceeded"
        elif timed_out:
            exit_code = EXIT_TIMEOUT
            stderr = (stderr or "") + "\ntimeout"
        return (
            subprocess.CompletedProcess(command, exit_code, stdout or "", stderr or ""),
            peak / (1024.0 * 1024.0) if peak else None,
        )
    finally:
        if handle:
            CloseHandle(handle)
        if proc.poll() is None:
            proc.kill()


def _measure_peak_memory_posix(
    command: list[str],
    timeout_s: float | None,
    max_peak_memory_mb: float | None,
) -> tuple[subprocess.CompletedProcess[str], float | None]:
    import resource

    limit_bytes = None if max_peak_memory_mb is None else int(max_peak_memory_mb * 1024 * 1024)
    proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    peak_kb = 0
    deadline = None if timeout_s is None else time.time() + timeout_s
    memory_limited = False
    timed_out = False
    try:
        while True:
            rss_kb = _read_proc_rss_kb(proc.pid)
            if rss_kb is not None:
                peak_kb = max(peak_kb, rss_kb)
                if limit_bytes is not None and rss_kb * 1024 > limit_bytes:
                    memory_limited = True
                    proc.kill()
                    break
            if proc.poll() is not None:
                break
            if deadline is not None and time.time() > deadline:
                timed_out = True
                proc.kill()
                break
            time.sleep(0.01)
        stdout, stderr = proc.communicate()
    finally:
        if proc.poll() is None:
            proc.kill()
            stdout, stderr = proc.communicate()

    usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    rss = float(usage.ru_maxrss)
    if sys.platform == "darwin":
        usage_mb = rss / (1024.0 * 1024.0)
    else:
        usage_mb = rss / 1024.0
        if peak_kb:
            usage_mb = max(usage_mb, peak_kb / 1024.0)

    exit_code = proc.returncode if proc.returncode is not None else 1
    if memory_limited:
        exit_code = EXIT_MEMORY_LIMIT
        stderr = (stderr or "") + "\nmemory limit exceeded"
    elif timed_out:
        exit_code = EXIT_TIMEOUT
        stderr = (stderr or "") + "\ntimeout"

    return (
        subprocess.CompletedProcess(command, exit_code, stdout or "", stderr or ""),
        usage_mb if usage_mb > 0 else None,
    )


def check_connected(
    executable: Path,
    csv_path: Path,
    temp_json: Path,
    radius: float,
) -> tuple[bool, dict[str, Any] | None, str | None]:
    inv = build_solver_command(
        executable,
        csv_path,
        temp_json,
        check_connectivity_only=True,
        radius=radius,
        pretty=True,
    )
    outcome = run_solver(inv)
    if outcome.result is None:
        return False, None, outcome.error or outcome.stderr or "connectivity check failed"
    return bool(outcome.result.get("connected_input")), outcome.result, outcome.error


def ensure_connected_dataset(
    spec: DatasetSpec,
    datasets_dir: Path,
    executable: Path,
    *,
    require_connected: bool,
    max_attempts: int,
) -> dict[str, Any]:
    """Generate (or reuse) a dataset. Returns a status dict with paths/meta."""
    datasets_dir.mkdir(parents=True, exist_ok=True)
    temp_json = datasets_dir / f".conn_{spec.key()}.json"

    for attempt in range(max_attempts if require_connected else 1):
        effective_seed = spec.base_seed + attempt
        csv_name = dataset_basename(spec, effective_seed)
        csv_path = datasets_dir / csv_name
        meta_path = datasets_dir / (csv_name[:-4] + ".meta.json")

        if not csv_path.is_file():
            gen_kwargs = dict(spec.params)
            allowed = {
                "density",
                "width",
                "height",
                "region",
                "clusters",
                "spread",
                "spacing",
                "jitter",
                "corridor_width",
                "bridge_fraction",
                "bridge_width",
            }
            filtered = {k: v for k, v in gen_kwargs.items() if k in allowed}
            result = generate(spec.distribution, spec.n, effective_seed, **filtered)
            write_csv(str(csv_path), result.points)
            params = result.parameters
        else:
            params = spec.params

        dataset_hash = sha256_file(csv_path)
        density = params.get("density", spec.params.get("density"))

        connected = True
        conn_result = None
        error = None
        if require_connected:
            connected, conn_result, error = check_connected(executable, csv_path, temp_json, spec.radius)

        meta = {
            "distribution": spec.distribution,
            "n": spec.n,
            "base_seed": spec.base_seed,
            "effective_seed": effective_seed,
            "attempt": attempt,
            "radius": spec.radius,
            "density": density,
            "connected": connected,
            "dataset_sha256": dataset_hash,
            "generator_parameters": params,
            "component_count": None if conn_result is None else conn_result.get("component_count"),
        }
        write_sidecar(meta_path, meta)

        if connected or not require_connected:
            if temp_json.exists():
                temp_json.unlink()
            return {
                "status": "ok",
                "csv_path": csv_path,
                "meta_path": meta_path,
                "meta": meta,
            }

        continue

    return {
        "status": "connectivity_retry_exhausted",
        "csv_path": None,
        "meta_path": None,
        "meta": {
            "distribution": spec.distribution,
            "n": spec.n,
            "base_seed": spec.base_seed,
            "effective_seed": None,
            "attempt": max_attempts,
            "radius": spec.radius,
            "density": spec.params.get("density"),
            "connected": False,
            "dataset_sha256": "",
            "generator_parameters": spec.params,
        },
        "error": f"no connected instance in {max_attempts} attempts",
    }


def run_id_for(algorithm: str, csv_path: Path) -> str:
    return f"{algorithm}__{csv_path.stem}"


def load_completed_run_ids(experiments_csv: Path) -> set[str]:
    if not experiments_csv.is_file():
        return set()
    done: set[str] = set()
    with experiments_csv.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if row.get("status") == "ok" and row.get("run_id"):
                done.add(row["run_id"])
    return done


def append_experiment_row(experiments_csv: Path, row: dict[str, Any]) -> None:
    experiments_csv.parent.mkdir(parents=True, exist_ok=True)
    write_header = not experiments_csv.is_file()
    with experiments_csv.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=EXPERIMENT_COLUMNS)
        if write_header:
            writer.writeheader()
        writer.writerow({k: row.get(k, "") for k in EXPERIMENT_COLUMNS})


def _status_from_exit(exit_code: int, *, has_result: bool, valid: bool) -> tuple[str, str]:
    if exit_code == EXIT_TIMEOUT:
        return "timeout", "solver timed out"
    if exit_code == EXIT_MEMORY_LIMIT:
        return "memory_limit", "peak memory limit exceeded"
    if not has_result:
        return ("invalid_json" if exit_code == 0 else "solver_error"), "missing result JSON"
    if exit_code != 0:
        return "solver_error", f"nonzero exit ({exit_code})"
    if not valid:
        return "validation_failure", "CDS failed independent validation"
    return "ok", ""


def _parse_solver_json(result_json: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not result_json.is_file():
        return None, "missing result JSON"
    try:
        return json.loads(result_json.read_text(encoding="utf-8")), None
    except json.JSONDecodeError as exc:
        return None, f"invalid solver JSON: {exc}"


def run_algorithm_trial(
    executable: Path,
    algorithm: str,
    csv_path: Path,
    meta: dict[str, Any],
    results_dir: Path,
    radius: float,
    *,
    measure_memory: bool = True,
    timeout_s: float | None = None,
    max_memory_mb: float | None = None,
    timing_repetitions: int = 1,
    warmup_runs: int = 0,
) -> dict[str, Any]:
    results_dir.mkdir(parents=True, exist_ok=True)
    rid = run_id_for(algorithm, csv_path)
    result_json = results_dir / f"{rid}.json"
    timings_json = results_dir / f"{rid}.timings.json"

    inv = build_solver_command(
        executable,
        csv_path,
        result_json,
        algorithm=algorithm,
        radius=radius,
        pretty=True,
    )

    peak_mb: float | None = None
    timing_raw_ms: list[float] = []
    outcome_exit = 0
    outcome_stderr = ""
    result: dict[str, Any] | None = None
    error: str | None = None

    reps = max(1, int(timing_repetitions))
    warmups = max(0, int(warmup_runs))
    multi_timing = reps > 1 or warmups > 0

    if multi_timing:
        for _ in range(warmups):
            run_solver(inv, timeout_s=timeout_s)

        for rep_idx in range(reps):
            is_last = rep_idx == reps - 1
            use_memory = measure_memory and is_last
            if use_memory:
                completed, peak_mb = measure_peak_memory_mb(
                    inv.command,
                    timeout_s=timeout_s,
                    max_peak_memory_mb=max_memory_mb,
                )
                outcome_exit = completed.returncode
                outcome_stderr = completed.stderr or ""
                parsed, parse_err = _parse_solver_json(result_json)
                if parsed is not None:
                    algo_ms = parsed.get("algorithm_ms")
                    if algo_ms is not None:
                        timing_raw_ms.append(float(algo_ms))
                    if is_last:
                        result = parsed
                elif parse_err:
                    error = parse_err
            else:
                outcome = run_solver(inv, timeout_s=timeout_s)
                outcome_exit = outcome.exit_code
                outcome_stderr = outcome.stderr or ""
                if outcome.result is not None:
                    algo_ms = outcome.result.get("algorithm_ms")
                    if algo_ms is not None:
                        timing_raw_ms.append(float(algo_ms))
                    if is_last:
                        result = outcome.result
                elif is_last:
                    error = outcome.error
    elif measure_memory:
        completed, peak_mb = measure_peak_memory_mb(
            inv.command,
            timeout_s=timeout_s,
            max_peak_memory_mb=max_memory_mb,
        )
        outcome_exit = completed.returncode
        outcome_stderr = completed.stderr or ""
        result, error = _parse_solver_json(result_json)
        if outcome_exit != 0 and error is None:
            error = (outcome_stderr or completed.stdout or f"exit {outcome_exit}").strip()
    else:
        outcome = run_solver(inv, timeout_s=timeout_s)
        outcome_exit = outcome.exit_code
        outcome_stderr = outcome.stderr or ""
        result = outcome.result
        error = outcome.error

    if timing_raw_ms:
        atomic_write_json(
            timings_json,
            {
                "run_id": rid,
                "algorithm": algorithm,
                "dataset_csv": str(csv_path),
                "warmup_runs": warmups,
                "timing_repetitions": reps,
                "timing_raw_ms": timing_raw_ms,
                "timing_median_ms": statistics.median(timing_raw_ms),
            },
        )

    density = meta.get("density")
    if density is None:
        density = (meta.get("generator_parameters") or {}).get("density")

    row: dict[str, Any] = {
        "run_id": rid,
        "algorithm": algorithm,
        "distribution": meta.get("distribution"),
        "n": meta.get("n"),
        "base_seed": meta.get("base_seed"),
        "effective_seed": meta.get("effective_seed"),
        "generation_attempt": meta.get("attempt"),
        "radius": radius,
        "density": density,
        "dataset_csv": str(csv_path),
        "dataset_sha256": meta.get("dataset_sha256", ""),
        "result_json": str(result_json) if result_json.is_file() else "",
        "exit_code": outcome_exit,
        "peak_memory_mb": f"{peak_mb:.4f}" if peak_mb is not None else "",
    }

    if result is None:
        status, err = _status_from_exit(outcome_exit, has_result=False, valid=False)
        row.update(
            {
                "status": status,
                "error": error or err or "missing result JSON",
                "input_connected": "",
                "component_count": "",
                "cds_size": "",
                "cds_ratio": "",
                "valid_dominating": "",
                "valid_connected": "",
            }
        )
        return row

    valid_d = bool(result.get("valid_dominating"))
    valid_c = bool(result.get("valid_connected"))
    status, err = _status_from_exit(outcome_exit, has_result=True, valid=valid_d and valid_c)
    if error and status != "ok":
        err = error

    algorithm_ms = result.get("algorithm_ms")
    if timing_raw_ms:
        algorithm_ms = statistics.median(timing_raw_ms)

    row.update(
        {
            "input_connected": result.get("connected_input"),
            "component_count": result.get("component_count"),
            "cds_size": result.get("cds_size"),
            "cds_ratio": result.get("cds_ratio"),
            "load_ms": result.get("load_ms"),
            "index_build_ms": result.get("index_build_ms"),
            "algorithm_ms": algorithm_ms,
            "validation_ms": result.get("validation_ms"),
            "total_ms": result.get("total_ms"),
            "algorithm_neighbor_queries": result.get("algorithm_neighbor_queries"),
            "algorithm_candidates_examined": result.get("algorithm_candidates_examined"),
            "valid_dominating": valid_d,
            "valid_connected": valid_c,
            "status": status,
            "error": err,
        }
    )
    _ = outcome_stderr
    return row


def expand_dataset_specs(config: dict[str, Any]) -> list[DatasetSpec]:
    specs: list[DatasetSpec] = []
    dist_params = config.get("distribution_parameters") or {}
    densities = config.get("densities")
    if densities is None:
        densities = [config.get("density", 2.0)]
    radius = float(config.get("radius", 1.0))
    for density in densities:
        for distribution in config["distributions"]:
            params = {"density": density}
            params.update(dist_params.get(distribution, {}))
            for n in config["sizes"]:
                for seed in config["seeds"]:
                    specs.append(
                        DatasetSpec(
                            distribution=distribution,
                            n=int(n),
                            base_seed=int(seed),
                            radius=radius,
                            params=dict(params),
                        )
                    )
    return specs


def write_manifest(path: Path, config: dict[str, Any], repo_root: Path, executable: Path) -> None:
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "config_sha256": config_sha256(config),
        **machine_provenance(repo_root, executable),
        "repo_root": str(repo_root),
        "config": config,
    }
    atomic_write_json(path, payload)


def write_batch_manifest(study_dir: Path, config: dict[str, Any], repo_root: Path, executable: Path) -> Path:
    path = study_dir / "batch_manifest.json"
    write_manifest(path, config, repo_root, executable)
    return path


def write_batch_state(
    path: Path,
    *,
    config_path: Path,
    stats: dict[str, Any],
    completed_run_ids: set[str],
    interrupted: bool = False,
    planned_runs: int | None = None,
) -> None:
    if interrupted:
        status = "interrupted"
    elif int(stats.get("runs_failed", 0)) > 0 or int(stats.get("datasets_failed", 0)) > 0:
        status = "completed_with_failures"
    else:
        status = "completed"
    # completed_run_ids only contains successful (status=ok) run IDs, including
    # those loaded from a prior resume — so its size is cumulative successes.
    atomic_write_json(
        path,
        {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "config_path": str(config_path),
            "status": status,
            "interrupted": interrupted,
            "planned_runs": planned_runs,
            "completed_runs": len(completed_run_ids),
            "successful_runs": len(completed_run_ids),
            "successful_this_invocation": int(stats.get("runs_ok", 0)),
            "failed_this_invocation": int(stats.get("runs_failed", 0)),
            "skipped_existing": int(stats.get("runs_skipped", 0)),
            "failed_runs": int(stats.get("runs_failed", 0)),
            "completed_run_ids": sorted(completed_run_ids),
            "stats": stats,
        },
    )


def preflight(
    config: dict[str, Any],
    executable: Path,
    repo_root: Path,
    *,
    verbose: bool = True,
    show_progress: bool = False,
) -> list[str]:
    """Run preflight checks. Raises on fatal failure; returns warning strings."""
    try:
        from preflight import PreflightError, run_preflight  # noqa: WPS433
    except ImportError:
        log_line("preflight module not found; skipping preflight checks.", progress=show_progress, verbose=verbose)
        return []
    try:
        result = run_preflight(
            config, executable, repo_root, verbose=verbose, show_progress=show_progress
        )
        return list(result) if result else []
    except PreflightError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"preflight failed: {exc}") from exc

def study_preview(config: dict[str, Any], specs: list[DatasetSpec], algorithms: list[str]) -> str:
    total_datasets = len(specs)
    logical_runs = total_datasets * len(algorithms)
    largest_n = max((spec.n for spec in specs), default=0)
    densities = sorted({spec.density for spec in specs if spec.density is not None})
    timing_reps = max(1, int(config.get("timing_repetitions", 1)))
    warmup = max(0, int(config.get("warmup_runs", 0)))
    launches_per_logical = timing_reps + warmup
    total_launches = logical_runs * launches_per_logical
    lines = [
        "STUDY PREVIEW",
        "",
        f"Algorithms:              {len(algorithms)}  {algorithms}",
        f"Distributions:           {len(config.get('distributions', []))}  {config.get('distributions', [])}",
        f"Sizes:                   {config.get('sizes', [])}",
        f"Seeds:                   {config.get('seeds', [])}",
        f"Densities:               {densities}",
        f"Radius:                  {config.get('radius', 1.0)}",
        "",
        f"Unique datasets:         {total_datasets}",
        f"Logical algorithm runs:  {logical_runs}",
        f"Measured repetitions:    {timing_reps} per run",
        f"Warmups:                 {warmup} per run",
        f"Total solver launches:   {total_launches}",
        "",
        f"Largest n:               {largest_n}",
        f"Max runtime seconds:     {config.get('max_runtime_seconds', config.get('timeout_s'))}",
        f"Max peak memory MB:      {config.get('max_peak_memory_mb', config.get('max_memory_mb'))}",
        "",
        "No experiments executed." if True else "",
    ]
    return "\n".join(lines)


def summarize(experiments_csv: Path) -> str:
    if not experiments_csv.is_file():
        return "No experiments CSV found."
    rows: list[dict[str, str]] = []
    with experiments_csv.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    groups: dict[tuple[str, str, str], list[dict[str, str]]] = {}
    for row in rows:
        key = (row.get("algorithm", "?"), row.get("distribution", "?"), row.get("n", "?"))
        groups.setdefault(key, []).append(row)

    lines = [
        "algorithm,distribution,n,runs,ok,failures,"
        "mean_cds_size,mean_cds_ratio,median_algorithm_ms,"
        "mean_neighbor_queries,mean_candidates,mean_peak_memory_mb"
    ]
    for (algo, dist, n), items in sorted(
        groups.items(), key=lambda kv: (kv[0][0], kv[0][1], int(float(kv[0][2])))
    ):
        ok = [r for r in items if r.get("status") == "ok"]
        failures = len(items) - len(ok)

        def mean_of(key: str) -> float:
            vals = [float(r[key]) for r in ok if r.get(key) not in ("", None)]
            return sum(vals) / len(vals) if vals else float("nan")

        sizes = [float(r["cds_size"]) for r in ok if r.get("cds_size") not in ("", None)]
        ratios = [float(r["cds_ratio"]) for r in ok if r.get("cds_ratio") not in ("", None)]
        times = sorted(float(r["algorithm_ms"]) for r in ok if r.get("algorithm_ms") not in ("", None))
        median_ms = times[len(times) // 2] if times else float("nan")
        mean_size = sum(sizes) / len(sizes) if sizes else float("nan")
        mean_ratio = sum(ratios) / len(ratios) if ratios else float("nan")
        lines.append(
            f"{algo},{dist},{n},{len(items)},{len(ok)},{failures},"
            f"{mean_size:.4f},{mean_ratio:.6f},{median_ms:.4f},"
            f"{mean_of('algorithm_neighbor_queries'):.1f},"
            f"{mean_of('algorithm_candidates_examined'):.1f},"
            f"{mean_of('peak_memory_mb'):.4f}"
        )
    return "\n".join(lines) + "\n"


def _pair_key(row: dict[str, str]) -> str:
    sha = row.get("dataset_sha256", "").strip()
    if sha:
        return sha
    return row.get("dataset_csv", "")


def paired_comparison(experiments_csv: Path, left: str = "marathe", right: str = "wan") -> str:
    """Compare two algorithms on identical datasets (prefer dataset_sha256)."""
    if not experiments_csv.is_file():
        return "No experiments CSV found."
    with experiments_csv.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    by_ds: dict[str, dict[str, dict[str, str]]] = {}
    for row in rows:
        if row.get("status") != "ok":
            continue
        ds = _pair_key(row)
        algo = row.get("algorithm", "")
        if not ds or not algo:
            continue
        by_ds.setdefault(ds, {})[algo] = row

    smaller = same = larger = 0
    deltas_cds: list[float] = []
    deltas_ms: list[float] = []
    deltas_q: list[float] = []
    ratios: list[float] = []
    for _ds, algos in by_ds.items():
        if left not in algos or right not in algos:
            continue
        a = float(algos[left]["cds_size"])
        b = float(algos[right]["cds_size"])
        deltas_cds.append(b - a)
        if a > 0:
            ratios.append(b / a)
        if b < a:
            smaller += 1
        elif b == a:
            same += 1
        else:
            larger += 1
        deltas_ms.append(float(algos[right]["algorithm_ms"]) - float(algos[left]["algorithm_ms"]))
        deltas_q.append(
            float(algos[right]["algorithm_neighbor_queries"])
            - float(algos[left]["algorithm_neighbor_queries"])
        )

    def mean(xs: list[float]) -> float:
        return sum(xs) / len(xs) if xs else float("nan")

    lines = [
        f"pair,{right}_vs_{left}",
        f"paired_datasets,{len(deltas_cds)}",
        f"{right}_cds_smaller,{smaller}",
        f"same_cds_size,{same}",
        f"{right}_cds_larger,{larger}",
        f"mean_cds_ratio ({right}/{left}),{mean(ratios):.4f}",
        f"mean_delta_cds ({right}-{left}),{mean(deltas_cds):.4f}",
        f"mean_delta_algorithm_ms,{mean(deltas_ms):.4f}",
        f"mean_delta_neighbor_queries,{mean(deltas_q):.1f}",
    ]
    return "\n".join(lines) + "\n"


def all_paired_comparisons(experiments_csv: Path) -> str:
    """Emit Li/Funke/Wan/Marathe paired comparisons when present."""
    with experiments_csv.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    algos = {r.get("algorithm", "") for r in rows if r.get("status") == "ok"}
    chunks: list[str] = []
    if "li" in algos:
        for other in ("marathe", "wan", "funke"):
            if other in algos:
                chunks.append(paired_comparison(experiments_csv, left=other, right="li"))
    elif "funke" in algos:
        for other in ("marathe", "wan"):
            if other in algos:
                chunks.append(paired_comparison(experiments_csv, left=other, right="funke"))
    elif "wan" in algos and "marathe" in algos:
        chunks.append(paired_comparison(experiments_csv, left="marathe", right="wan"))
    return "".join(chunks) if chunks else paired_comparison(experiments_csv)


def run_campaign(
    config_path: Path,
    *,
    force: bool = False,
    measure_memory: bool = True,
    show_progress: bool = True,
    verbose: bool = True,
    dry_run: bool = False,
    skip_preflight: bool = False,
) -> dict[str, Any]:
    repo_root = find_repo_root()
    config = load_config(config_path)
    executable = find_mcds_executable(repo_root)

    if detect_build_type(executable) == "Debug":
        log_line(
            "WARNING: solver executable appears to be a Debug build; timing results may be unreliable.",
            progress=show_progress,
            verbose=verbose,
        )

    study_dir_cfg = config.get("study_dir")
    study_dir = (repo_root / study_dir_cfg).resolve() if study_dir_cfg else None
    if study_dir is not None:
        study_dir.mkdir(parents=True, exist_ok=True)

    datasets_dir = repo_root / config.get("datasets_dir", "datasets/generated")
    results_dir = repo_root / config.get("results_dir", "results/runs")
    experiments_csv = repo_root / config.get("experiments_csv", "results/experiments.csv")
    manifest_path = (
        study_dir / "batch_manifest.json"
        if study_dir is not None
        else repo_root / config.get("manifest_path", "results/experiment_manifest.json")
    )
    batch_state_path = (
        study_dir / "batch_state.json"
        if study_dir is not None
        else repo_root / config.get("batch_state_path", "results/batch_state.json")
    )

    require_connected = bool(config.get("require_connected", True))
    max_attempts = int(config.get("max_connectivity_attempts", 100))
    algorithms = list(config.get("algorithms", ["marathe"]))
    specs = expand_dataset_specs(config)

    timeout_s = config.get("max_runtime_seconds", config.get("timeout_s"))
    if timeout_s is not None:
        timeout_s = float(timeout_s)
    max_memory_mb = config.get("max_peak_memory_mb", config.get("max_memory_mb"))
    if max_memory_mb is not None:
        max_memory_mb = float(max_memory_mb)
    timing_repetitions = int(config.get("timing_repetitions", 1))
    warmup_runs = int(config.get("warmup_runs", 0))

    preview = study_preview(config, specs, algorithms)
    if dry_run:
        log_line(preview, progress=False, verbose=True)
        timing_reps = max(1, int(config.get("timing_repetitions", 1)))
        warmup = max(0, int(config.get("warmup_runs", 0)))
        logical = len(specs) * len(algorithms)
        return {
            "dry_run": True,
            "preview": preview,
            "datasets": len(specs),
            "logical_runs": logical,
            "timing_repetitions": timing_reps,
            "warmup_runs": warmup,
            "solver_launches": logical * (timing_reps + warmup),
            "trials": logical,
        }

    if not skip_preflight:
        try:
            for msg in preflight(config, executable, repo_root, verbose=verbose, show_progress=show_progress):
                log_line(msg, progress=show_progress, verbose=verbose)
        except Exception as exc:  # noqa: BLE001 — PreflightError or RuntimeError
            log_line(f"PREFLIGHT FAILED: {exc}", progress=False, verbose=True)
            return {
                "preflight_failed": True,
                "error": str(exc),
                "datasets_ok": 0,
                "datasets_failed": 0,
                "runs_ok": 0,
                "runs_failed": 0,
                "runs_skipped": 0,
                "rows": 0,
            }

    write_manifest(manifest_path, config, repo_root, executable)

    completed = set() if force else load_completed_run_ids(experiments_csv)

    stats = {
        "datasets_ok": 0,
        "datasets_failed": 0,
        "runs_ok": 0,
        "runs_failed": 0,
        "runs_skipped": 0,
        "rows": 0,
    }

    interrupted = False
    progress_enabled = show_progress and tqdm is not None
    postfix = {"ok": 0, "fail": 0, "skip": 0}

    total_trials = len(specs) * len(algorithms)
    initial = min(len(completed), total_trials) if not force else 0
    bar = None
    if progress_enabled:
        bar = tqdm(
            total=total_trials,
            initial=initial,
            desc="experiments",
            unit="trial",
            dynamic_ncols=True,
        )

    def _log(msg: str) -> None:
        log_line(msg, progress=progress_enabled, verbose=verbose)

    def _update_postfix(**kwargs: Any) -> None:
        postfix.update(kwargs)
        if bar is not None:
            bar.set_postfix(
                ok=postfix["ok"],
                fail=postfix["fail"],
                skip=postfix["skip"],
                refresh=False,
            )

    planned = len(specs) * len(algorithms)

    def _persist_state() -> None:
        write_batch_state(
            batch_state_path,
            config_path=config_path,
            stats=stats,
            completed_run_ids=completed,
            interrupted=interrupted,
            planned_runs=planned,
        )

    try:
        prepared: list[dict[str, Any]] = []
        for spec in specs:
            if interrupted:
                break
            info = ensure_connected_dataset(
                spec,
                datasets_dir,
                executable,
                require_connected=require_connected,
                max_attempts=max_attempts,
            )
            if info["status"] != "ok":
                stats["datasets_failed"] += 1
                for algorithm in algorithms:
                    if interrupted:
                        break
                    row = {
                        "run_id": f"{algorithm}__{spec.key()}_FAILED",
                        "algorithm": algorithm,
                        "distribution": spec.distribution,
                        "n": spec.n,
                        "base_seed": spec.base_seed,
                        "effective_seed": "",
                        "generation_attempt": info["meta"].get("attempt"),
                        "radius": spec.radius,
                        "density": spec.density,
                        "input_connected": False,
                        "dataset_sha256": info["meta"].get("dataset_sha256", ""),
                        "status": "connectivity_retry_exhausted",
                        "error": info.get("error", ""),
                        "exit_code": 1,
                    }
                    append_experiment_row(experiments_csv, row)
                    stats["rows"] += 1
                    stats["runs_failed"] += 1
                    postfix["fail"] += 1
                    if bar is not None:
                        bar.update(1)
                        bar.set_postfix(algo=algorithm, dist=spec.distribution, n=spec.n, seed=spec.base_seed, **postfix)
                continue

            stats["datasets_ok"] += 1
            prepared.append(info)

        for info in prepared:
            if interrupted:
                break
            csv_path: Path = info["csv_path"]
            meta = info["meta"]
            for algorithm in algorithms:
                if interrupted:
                    break
                rid = run_id_for(algorithm, csv_path)
                if rid in completed:
                    stats["runs_skipped"] += 1
                    postfix["skip"] += 1
                    if bar is not None:
                        bar.update(1)
                        bar.set_postfix(
                            algo=algorithm,
                            dist=meta.get("distribution"),
                            n=meta.get("n"),
                            seed=meta.get("base_seed"),
                            **postfix,
                        )
                    continue

                row = run_algorithm_trial(
                    executable,
                    algorithm,
                    csv_path,
                    meta,
                    results_dir,
                    radius=float(config.get("radius", 1.0)),
                    measure_memory=measure_memory,
                    timeout_s=timeout_s,
                    max_memory_mb=max_memory_mb,
                    timing_repetitions=timing_repetitions,
                    warmup_runs=warmup_runs,
                )
                append_experiment_row(experiments_csv, row)
                stats["rows"] += 1
                if row["status"] == "ok":
                    stats["runs_ok"] += 1
                    completed.add(rid)
                    postfix["ok"] += 1
                else:
                    stats["runs_failed"] += 1
                    postfix["fail"] += 1
                _persist_state()
                if bar is not None:
                    bar.update(1)
                    bar.set_postfix(
                        algo=algorithm,
                        dist=meta.get("distribution"),
                        n=meta.get("n"),
                        seed=meta.get("base_seed"),
                        **postfix,
                    )

    except KeyboardInterrupt:
        interrupted = True
        _persist_state()
        _log(
            "\nExperiment interrupted.\n\n"
            "Completed results were preserved.\n"
            "Run the same command again to resume."
        )
        if bar is not None:
            bar.close()
        stats["interrupted"] = True
        stats["experiments_csv"] = str(experiments_csv)
        stats["datasets_dir"] = str(datasets_dir)
        stats["results_dir"] = str(results_dir)
        stats["batch_state_path"] = str(batch_state_path)
        return stats

    if bar is not None:
        bar.close()

    _persist_state()

    if study_dir is not None:
        try:
            from study_report import generate_study_report  # noqa: WPS433

            generate_study_report(study_dir, experiments_csv, manifest_path, batch_state_path)
        except ImportError:
            _log("study_report module not found; skipping report generation.")

    stats["interrupted"] = interrupted
    stats["experiments_csv"] = str(experiments_csv)
    stats["datasets_dir"] = str(datasets_dir)
    stats["results_dir"] = str(results_dir)
    stats["batch_state_path"] = str(batch_state_path)
    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run reproducible MCDS experiments.")
    parser.add_argument("--config", required=True, help="experiment JSON config")
    parser.add_argument("--force", action="store_true", help="rerun even if run_id completed")
    parser.add_argument("--summary", action="store_true", help="print summary of experiments CSV and exit")
    parser.add_argument("--paired", action="store_true", help="print paired algorithm comparisons")
    parser.add_argument("--no-memory", action="store_true", help="skip peak-memory measurement")
    parser.add_argument("--no-progress", action="store_true", help="disable tqdm progress bar")
    parser.add_argument("--verbose", action="store_true", help="print detailed log messages")
    parser.add_argument("--dry-run", action="store_true", help="preview study without executing")
    parser.add_argument("--skip-preflight", action="store_true", help="skip preflight checks")
    args = parser.parse_args(argv)

    config_path = Path(args.config)
    if args.summary or args.paired:
        repo_root = find_repo_root()
        config = load_config(config_path)
        experiments_csv = repo_root / config.get("experiments_csv", "results/experiments.csv")
        if args.summary:
            print(summarize(experiments_csv), end="")
        if args.paired:
            print(all_paired_comparisons(experiments_csv), end="")
        return 0

    stats = run_campaign(
        config_path,
        force=args.force,
        measure_memory=not args.no_memory,
        show_progress=not args.no_progress,
        verbose=args.verbose,
        dry_run=args.dry_run,
        skip_preflight=args.skip_preflight,
    )
    if stats.get("dry_run"):
        return 0
    print(json.dumps(stats, indent=2))
    print(summarize(Path(stats["experiments_csv"])), end="")
    print(all_paired_comparisons(Path(stats["experiments_csv"])), end="")
    if stats.get("interrupted"):
        return 130
    return 0 if stats["runs_failed"] == 0 and stats["datasets_failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
