"""Thin interface to the C++ `mcds_bench` / `mcds_bench_mem` binaries."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

BENCH_SCHEMA = "mcds-bench/1"

_CANDIDATE_DIRS = (
    "cpp/build-msvc/Release",
    "cpp/build/Release",
    "cpp/build",
    "build/Release",
    "build",
)


def find_binary(repo_root: Path, name: str) -> Path:
    env = os.environ.get("MCDS_BENCH_DIR")
    dirs = [Path(env)] if env else [repo_root / d for d in _CANDIDATE_DIRS]
    found = []
    for d in dirs:
        for candidate in (d / f"{name}.exe", d / name):
            if candidate.is_file():
                found.append(candidate)
    if not found:
        raise FileNotFoundError(
            f"{name} not found. Build it: cmake -S cpp -B cpp/build -DCMAKE_BUILD_TYPE=Release && "
            f"cmake --build cpp/build --config Release --target {name} (or set MCDS_BENCH_DIR)."
        )
    # Deterministic choice: first match in the documented search order.
    return found[0]


@dataclass
class BenchOutcome:
    ok: bool
    data: dict[str, Any] | None
    error: str | None
    returncode: int | None


def run_bench(
    binary: Path,
    csv_path: Path,
    radius: float,
    *,
    algorithms: list[str] | None = None,
    repetitions: int = 1,
    warmups: int = 0,
    instrumentation: str = "none",
    validate: str = "all",
    exact_max_n: int = 0,
    graph_only: bool = False,
    run_disconnected: bool = False,
    emit_solution: bool = False,
    timeout_s: float | None = None,
    output_json: Path | None = None,
) -> BenchOutcome:
    """Runs the binary; the JSON is written to a temp file, then moved atomically."""
    target = output_json
    tmp_dir = (target.parent if target else Path(tempfile.gettempdir()))
    tmp_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".bench_", suffix=".json", dir=str(tmp_dir))
    os.close(fd)
    tmp = Path(tmp_name)

    cmd = [str(binary), "--input", str(csv_path), "--radius", repr(float(radius)), "--output", str(tmp),
           "--instrumentation", instrumentation, "--validate", validate,
           "--repetitions", str(repetitions), "--warmups", str(warmups)]
    if algorithms:
        cmd += ["--algorithms", ",".join(algorithms)]
    if exact_max_n:
        cmd += ["--exact-max-n", str(exact_max_n)]
    if graph_only:
        cmd.append("--graph-only")
    if run_disconnected:
        cmd.append("--run-disconnected")
    if emit_solution:
        cmd.append("--emit-solution")

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        tmp.unlink(missing_ok=True)
        return BenchOutcome(False, None, f"timeout after {timeout_s}s", None)

    if proc.returncode != 0:
        tmp.unlink(missing_ok=True)
        return BenchOutcome(False, None, (proc.stderr or proc.stdout or "").strip() or f"exit {proc.returncode}",
                            proc.returncode)
    try:
        data = json.loads(tmp.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        tmp.unlink(missing_ok=True)
        return BenchOutcome(False, None, f"invalid bench JSON: {exc}", proc.returncode)
    if data.get("schema") != BENCH_SCHEMA:
        tmp.unlink(missing_ok=True)
        return BenchOutcome(False, None, f"unexpected bench schema {data.get('schema')!r}", proc.returncode)

    if target is not None:
        os.replace(tmp, target)
    else:
        tmp.unlink(missing_ok=True)
    return BenchOutcome(True, data, None, proc.returncode)


def build_info(binary: Path) -> dict[str, Any] | None:
    """Reads the compiler/flags block by running the binary on a 1-point graph."""
    with tempfile.TemporaryDirectory() as d:
        csv_path = Path(d) / "one.csv"
        csv_path.write_text("id,x,y\n0,0.0,0.0\n", encoding="utf-8")
        out = run_bench(binary, csv_path, 1.0, graph_only=True, timeout_s=60)
        return out.data.get("build") if out.ok and out.data else None
