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
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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

EXPERIMENT_COLUMNS = [
    "run_id",
    "algorithm",
    "distribution",
    "n",
    "base_seed",
    "effective_seed",
    "generation_attempt",
    "radius",
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
    "result_json",
    "exit_code",
    "status",
    "error",
]


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


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def dataset_basename(spec: DatasetSpec, effective_seed: int) -> str:
    if effective_seed == spec.base_seed:
        return f"{spec.distribution}_n{spec.n}_seed{spec.base_seed}.csv"
    return f"{spec.distribution}_n{spec.n}_seed{spec.base_seed}_eff{effective_seed}.csv"


def write_sidecar(meta_path: Path, payload: dict[str, Any]) -> None:
    meta_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def measure_peak_memory_mb(command: list[str], timeout_s: float | None = None) -> tuple[subprocess.CompletedProcess[str], float | None]:
    """Run a child process and estimate peak working-set / RSS in megabytes.

    Windows: polls ``GetProcessMemoryInfo`` WorkingSetSize while the child runs.
    POSIX: uses ``resource.getrusage(RUSAGE_CHILDREN).ru_maxrss`` after exit
    (Linux: kilobytes; macOS: bytes).

    Returns ``(completed_process, peak_memory_mb_or_None)``.
    """
    if platform.system() == "Windows":
        return _measure_peak_memory_windows(command, timeout_s)
    return _measure_peak_memory_posix(command, timeout_s)


def _measure_peak_memory_windows(
    command: list[str], timeout_s: float | None
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
    try:
        while True:
            if handle:
                counters = PROCESS_MEMORY_COUNTERS()
                counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
                if GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
                    peak = max(
                        peak,
                        int(counters.PeakWorkingSetSize),
                        int(counters.WorkingSetSize),
                    )
            if proc.poll() is not None:
                break
            if deadline is not None and time.time() > deadline:
                proc.kill()
                stdout, stderr = proc.communicate()
                return (
                    subprocess.CompletedProcess(command, 124, stdout or "", stderr or "timeout"),
                    peak / (1024.0 * 1024.0) if peak else None,
                )
            time.sleep(0.01)
        stdout, stderr = proc.communicate()
        if handle:
            counters = PROCESS_MEMORY_COUNTERS()
            counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
            if GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
                peak = max(
                    peak,
                    int(counters.PeakWorkingSetSize),
                    int(counters.WorkingSetSize),
                )
        return (
            subprocess.CompletedProcess(command, proc.returncode, stdout or "", stderr or ""),
            peak / (1024.0 * 1024.0) if peak else None,
        )
    finally:
        if handle:
            CloseHandle(handle)
        if proc.poll() is None:
            proc.kill()


def _measure_peak_memory_posix(
    command: list[str], timeout_s: float | None
) -> tuple[subprocess.CompletedProcess[str], float | None]:
    import resource

    completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout_s, check=False)
    usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    rss = float(usage.ru_maxrss)
    # Linux reports KB; macOS reports bytes.
    if sys.platform == "darwin":
        mb = rss / (1024.0 * 1024.0)
    else:
        mb = rss / 1024.0
    return completed, mb if mb > 0 else None


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
            # Pull known generate() kwargs; ignore unknown keys gently.
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
            "connected": connected,
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

        # Not connected: try next seed. Keep the CSV for inspection but continue.
        continue

    return {
        "status": "connectivity_exhausted",
        "csv_path": None,
        "meta_path": None,
        "meta": {
            "distribution": spec.distribution,
            "n": spec.n,
            "base_seed": spec.base_seed,
            "effective_seed": None,
            "attempt": max_attempts,
            "radius": spec.radius,
            "connected": False,
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


def run_algorithm_trial(
    executable: Path,
    algorithm: str,
    csv_path: Path,
    meta: dict[str, Any],
    results_dir: Path,
    radius: float,
    *,
    measure_memory: bool = True,
) -> dict[str, Any]:
    results_dir.mkdir(parents=True, exist_ok=True)
    rid = run_id_for(algorithm, csv_path)
    result_json = results_dir / f"{rid}.json"
    inv = build_solver_command(
        executable,
        csv_path,
        result_json,
        algorithm=algorithm,
        radius=radius,
        pretty=True,
    )

    peak_mb: float | None = None
    if measure_memory:
        completed, peak_mb = measure_peak_memory_mb(inv.command)
        outcome_exit = completed.returncode
        outcome_stdout = completed.stdout or ""
        outcome_stderr = completed.stderr or ""
        result = None
        error = None
        if result_json.is_file():
            try:
                result = json.loads(result_json.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                error = f"invalid solver JSON: {exc}"
        if outcome_exit != 0 and error is None:
            error = (outcome_stderr or outcome_stdout or f"exit {outcome_exit}").strip()
    else:
        outcome = run_solver(inv)
        outcome_exit = outcome.exit_code
        outcome_stdout = outcome.stdout
        outcome_stderr = outcome.stderr
        result = outcome.result
        error = outcome.error

    row: dict[str, Any] = {
        "run_id": rid,
        "algorithm": algorithm,
        "distribution": meta.get("distribution"),
        "n": meta.get("n"),
        "base_seed": meta.get("base_seed"),
        "effective_seed": meta.get("effective_seed"),
        "generation_attempt": meta.get("attempt"),
        "radius": radius,
        "dataset_csv": str(csv_path),
        "result_json": str(result_json) if result_json.is_file() else "",
        "exit_code": outcome_exit,
        "peak_memory_mb": f"{peak_mb:.4f}" if peak_mb is not None else "",
    }

    if result is None:
        row.update(
            {
                "status": "solver_error" if outcome_exit != 0 else "invalid_json",
                "error": error or "missing result JSON",
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
    status = "ok"
    err = ""
    if outcome_exit != 0:
        status = "solver_error"
        err = error or "nonzero exit"
    elif not valid_d or not valid_c:
        status = "validation_failure"
        err = "CDS failed independent validation"

    row.update(
        {
            "input_connected": result.get("connected_input"),
            "component_count": result.get("component_count"),
            "cds_size": result.get("cds_size"),
            "cds_ratio": result.get("cds_ratio"),
            "load_ms": result.get("load_ms"),
            "index_build_ms": result.get("index_build_ms"),
            "algorithm_ms": result.get("algorithm_ms"),
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
    _ = outcome_stdout
    return row


def expand_dataset_specs(config: dict[str, Any]) -> list[DatasetSpec]:
    specs: list[DatasetSpec] = []
    dist_params = config.get("distribution_parameters") or {}
    base_density = config.get("density", 2.0)
    radius = float(config.get("radius", 1.0))
    for distribution in config["distributions"]:
        params = {"density": base_density}
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
    exe_hash = ""
    try:
        data = executable.read_bytes()
        exe_hash = hashlib.sha256(data).hexdigest()
    except OSError:
        pass
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "os": platform.platform(),
        "python": sys.version,
        "executable": str(executable),
        "executable_sha256": exe_hash,
        "repo_root": str(repo_root),
        "config": config,
    }
    # Best-effort git commit.
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(repo_root), text=True
        ).strip()
        payload["git_commit"] = commit
    except Exception:  # noqa: BLE001
        payload["git_commit"] = None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


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


def paired_comparison(experiments_csv: Path, left: str = "marathe", right: str = "wan") -> str:
    """Compare two algorithms on identical dataset_csv paths."""
    if not experiments_csv.is_file():
        return "No experiments CSV found."
    with experiments_csv.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    by_ds: dict[str, dict[str, dict[str, str]]] = {}
    for row in rows:
        if row.get("status") != "ok":
            continue
        ds = row.get("dataset_csv", "")
        algo = row.get("algorithm", "")
        if not ds or not algo:
            continue
        by_ds.setdefault(ds, {})[algo] = row

    smaller = same = larger = 0
    deltas_cds: list[float] = []
    deltas_ms: list[float] = []
    deltas_q: list[float] = []
    for _ds, algos in by_ds.items():
        if left not in algos or right not in algos:
            continue
        a = float(algos[left]["cds_size"])
        b = float(algos[right]["cds_size"])
        deltas_cds.append(b - a)
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
        f"paired_datasets,{len(deltas_cds)}",
        f"{right}_cds_smaller,{smaller}",
        f"same_cds_size,{same}",
        f"{right}_cds_larger,{larger}",
        f"mean_delta_cds ({right}-{left}),{mean(deltas_cds):.4f}",
        f"mean_delta_algorithm_ms,{mean(deltas_ms):.4f}",
        f"mean_delta_neighbor_queries,{mean(deltas_q):.1f}",
    ]
    return "\n".join(lines) + "\n"


def run_campaign(config_path: Path, *, force: bool = False, measure_memory: bool = True) -> dict[str, Any]:
    repo_root = find_repo_root()
    config = load_config(config_path)
    executable = find_mcds_executable(repo_root)

    datasets_dir = repo_root / config.get("datasets_dir", "datasets/generated")
    results_dir = repo_root / config.get("results_dir", "results/runs")
    experiments_csv = repo_root / config.get("experiments_csv", "results/experiments.csv")
    manifest_path = repo_root / config.get("manifest_path", "results/experiment_manifest.json")

    write_manifest(manifest_path, config, repo_root, executable)

    require_connected = bool(config.get("require_connected", True))
    max_attempts = int(config.get("max_connectivity_attempts", 100))
    algorithms = list(config.get("algorithms", ["marathe"]))
    specs = expand_dataset_specs(config)

    completed = set() if force else load_completed_run_ids(experiments_csv)

    stats = {
        "datasets_ok": 0,
        "datasets_failed": 0,
        "runs_ok": 0,
        "runs_failed": 0,
        "runs_skipped": 0,
        "rows": 0,
    }

    # Stage 1+2: datasets
    prepared: list[dict[str, Any]] = []
    for spec in specs:
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
                row = {
                    "run_id": f"{algorithm}__{spec.key()}_FAILED",
                    "algorithm": algorithm,
                    "distribution": spec.distribution,
                    "n": spec.n,
                    "base_seed": spec.base_seed,
                    "effective_seed": "",
                    "generation_attempt": info["meta"].get("attempt"),
                    "radius": spec.radius,
                    "input_connected": False,
                    "status": "connectivity_exhausted",
                    "error": info.get("error", ""),
                    "exit_code": 1,
                }
                append_experiment_row(experiments_csv, row)
                stats["rows"] += 1
                stats["runs_failed"] += 1
            continue

        stats["datasets_ok"] += 1
        prepared.append(info)

    # Stage 3: algorithms on shared datasets
    for info in prepared:
        csv_path: Path = info["csv_path"]
        meta = info["meta"]
        for algorithm in algorithms:
            rid = run_id_for(algorithm, csv_path)
            if rid in completed:
                stats["runs_skipped"] += 1
                continue
            row = run_algorithm_trial(
                executable,
                algorithm,
                csv_path,
                meta,
                results_dir,
                radius=float(config.get("radius", 1.0)),
                measure_memory=measure_memory,
            )
            append_experiment_row(experiments_csv, row)
            stats["rows"] += 1
            if row["status"] == "ok":
                stats["runs_ok"] += 1
            else:
                stats["runs_failed"] += 1

    stats["experiments_csv"] = str(experiments_csv)
    stats["datasets_dir"] = str(datasets_dir)
    stats["results_dir"] = str(results_dir)
    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run reproducible MCDS experiments.")
    parser.add_argument("--config", required=True, help="experiment JSON config")
    parser.add_argument("--force", action="store_true", help="rerun even if run_id completed")
    parser.add_argument("--summary", action="store_true", help="print summary of experiments CSV and exit")
    parser.add_argument("--paired", action="store_true", help="print Marathe vs Wan paired comparison")
    parser.add_argument("--no-memory", action="store_true", help="skip peak-memory measurement")
    args = parser.parse_args(argv)

    config_path = Path(args.config)
    if args.summary or args.paired:
        repo_root = find_repo_root()
        config = load_config(config_path)
        experiments_csv = repo_root / config.get("experiments_csv", "results/experiments.csv")
        if args.summary:
            print(summarize(experiments_csv), end="")
        if args.paired:
            print(paired_comparison(experiments_csv), end="")
        return 0

    stats = run_campaign(config_path, force=args.force, measure_memory=not args.no_memory)
    print(json.dumps(stats, indent=2))
    print(summarize(Path(stats["experiments_csv"])), end="")
    print(paired_comparison(Path(stats["experiments_csv"])), end="")
    return 0 if stats["runs_failed"] == 0 and stats["datasets_failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
