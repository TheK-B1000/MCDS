"""Reusable orchestration helpers for the MCDS GUI and experiment runner.

These functions intentionally contain no Tkinter widgets so they can be unit
tested without a display.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_PYTHON_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _PYTHON_DIR.parent
if str(_PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(_PYTHON_DIR))

from generators import GENERATOR_TYPES, generate, write_csv  # noqa: E402


ALGORITHMS = ("marathe", "wan")

# Distribution -> which geometry fields are relevant in the GUI.
DISTRIBUTION_FIELDS: dict[str, tuple[str, ...]] = {
    "uniform": ("width", "height", "density"),
    "clustered": ("width", "height", "density", "clusters", "spread"),
    "perturbed_grid": ("density", "spacing", "jitter"),
    "corridor": ("density", "corridor_width"),
    "cluster_bridge": ("clusters", "spread", "bridge_fraction", "bridge_width"),
}


@dataclass
class SolverInvocation:
    command: list[str]
    input_csv: Path
    output_json: Path


@dataclass
class SolverOutcome:
    exit_code: int
    stdout: str
    stderr: str
    duration_s: float
    result: dict[str, Any] | None = None
    error: str | None = None


def find_repo_root(start: Path | None = None) -> Path:
    here = (start or Path(__file__).resolve()).resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "cpp" / "CMakeLists.txt").is_file() and (candidate / "python").is_dir():
            return candidate
    return _REPO_ROOT


def find_mcds_executable(repo_root: Path | None = None) -> Path:
    root = repo_root or find_repo_root()
    candidates = [
        root / "build" / "mcds.exe",
        root / "build" / "mcds",
        root / "build" / "Release" / "mcds.exe",
        root / "build" / "Debug" / "mcds.exe",
        root / "build-msvc" / "mcds.exe",
        root / "build-msvc" / "Release" / "mcds.exe",
        root / "cpp" / "build" / "mcds.exe",
        root / "cpp" / "build" / "mcds",
        root / "cpp" / "build" / "Release" / "mcds.exe",
    ]
    env = os.environ.get("MCDS_EXECUTABLE")
    if env:
        candidates.insert(0, Path(env))
    for path in candidates:
        if path.is_file():
            return path
    raise FileNotFoundError(
        "C++ mcds executable not found. Build it first "
        "(cmake -S cpp -B build && cmake --build build), "
        "or set MCDS_EXECUTABLE."
    )


def dataset_paths(work_dir: Path, label: str = "gui") -> tuple[Path, Path, Path]:
    """Return (csv, meta_json, result_json) under work_dir."""
    work_dir.mkdir(parents=True, exist_ok=True)
    return (
        work_dir / f"{label}_points.csv",
        work_dir / f"{label}_points.meta.json",
        work_dir / f"{label}_result.json",
    )


def map_generation_kwargs(
    distribution: str,
    n: int,
    seed: int,
    *,
    radius: float = 1.0,
    density: float = 2.0,
    width: float | None = None,
    height: float | None = None,
    clusters: int = 8,
    spread: float = 0.5,
    spacing: float | None = None,
    jitter: float = 0.2,
    corridor_width: float = 2.0,
    bridge_fraction: float = 0.15,
    bridge_width: float = 0.5,
) -> dict[str, Any]:
    if distribution not in GENERATOR_TYPES:
        raise ValueError(f"unknown distribution {distribution!r}")
    kwargs: dict[str, Any] = {
        "type": distribution,
        "n": n,
        "seed": seed,
        "density": density,
        "clusters": clusters,
        "spread": spread,
        "jitter": jitter,
        "corridor_width": corridor_width,
        "bridge_fraction": bridge_fraction,
        "bridge_width": bridge_width,
    }
    if width is not None:
        kwargs["width"] = width
    if height is not None:
        kwargs["height"] = height
    if spacing is not None:
        kwargs["spacing"] = spacing
    _ = radius  # radius is a UDG parameter, not a generator parameter
    return kwargs


def write_dataset_with_metadata(
    csv_path: Path,
    meta_path: Path,
    *,
    distribution: str,
    n: int,
    seed: int,
    **gen_kwargs: Any,
) -> dict[str, Any]:
    result = generate(distribution, n, seed, **{k: v for k, v in gen_kwargs.items() if k != "type"})
    write_csv(str(csv_path), result.points)
    meta = {
        "distribution": distribution,
        "n": n,
        "seed": seed,
        "base_seed": seed,
        "effective_seed": seed,
        "attempt": 0,
        "generator_parameters": result.parameters,
    }
    meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return meta


def build_solver_command(
    executable: Path,
    input_csv: Path,
    output_json: Path,
    *,
    algorithm: str = "marathe",
    radius: float = 1.0,
    check_connectivity_only: bool = False,
    pretty: bool = True,
) -> SolverInvocation:
    if algorithm not in ALGORITHMS and not check_connectivity_only:
        raise ValueError(f"unknown algorithm {algorithm!r}")
    cmd = [str(executable), "--input", str(input_csv), "--radius", str(radius)]
    if check_connectivity_only:
        cmd.append("--check-connectivity")
    else:
        cmd.extend(["--algorithm", algorithm])
    cmd.extend(["--output", str(output_json)])
    if pretty:
        cmd.append("--pretty")
    return SolverInvocation(command=cmd, input_csv=input_csv, output_json=output_json)


def run_solver(invocation: SolverInvocation, *, timeout_s: float | None = None) -> SolverOutcome:
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            invocation.command,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except FileNotFoundError as exc:
        return SolverOutcome(
            exit_code=127,
            stdout="",
            stderr=str(exc),
            duration_s=time.perf_counter() - started,
            error=f"executable not found: {invocation.command[0]}",
        )
    except subprocess.TimeoutExpired as exc:
        return SolverOutcome(
            exit_code=124,
            stdout=(exc.stdout or "") if isinstance(exc.stdout, str) else "",
            stderr="solver timed out",
            duration_s=time.perf_counter() - started,
            error="solver timed out",
        )

    duration = time.perf_counter() - started
    result = None
    error = None
    if invocation.output_json.is_file():
        try:
            result = json.loads(invocation.output_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            error = f"invalid solver JSON: {exc}"
    elif completed.returncode == 0:
        error = f"solver produced no JSON at {invocation.output_json}"

    if completed.returncode != 0 and error is None:
        err = (completed.stderr or completed.stdout or "").strip()
        error = err or f"solver exited with code {completed.returncode}"

    return SolverOutcome(
        exit_code=completed.returncode,
        stdout=completed.stdout or "",
        stderr=completed.stderr or "",
        duration_s=duration,
        result=result,
        error=error,
    )


def friendly_solver_error(outcome: SolverOutcome) -> str:
    if outcome.error:
        text = outcome.error
    elif outcome.stderr.strip():
        text = outcome.stderr.strip()
    else:
        text = f"solver failed with exit code {outcome.exit_code}"

    lower = text.lower()
    if "disconnected" in lower:
        return "Input UDG is disconnected. Generate a denser or bridged instance, or lower the region size."
    if "not found" in lower or outcome.exit_code == 127:
        return "C++ mcds executable was not found. Build the project first."
    if "cannot open" in lower or "no points" in lower:
        return "Point CSV could not be loaded. Check the file path and format."
    if "invalid solver json" in lower or "no json" in lower:
        return "Solver finished without a readable JSON result."
    if "validation failed" in lower or (
        outcome.result
        and (
            outcome.result.get("valid_dominating") is False
            or outcome.result.get("valid_connected") is False
        )
    ):
        return "Solver output failed independent validation."
    # Keep message short for dialogs; full text remains in outcome.stderr.
    first_line = text.splitlines()[0] if text else "Unknown solver error."
    if first_line.startswith("error: "):
        first_line = first_line[7:]
    return first_line
