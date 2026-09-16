"""Preflight checks before launching an experiment campaign."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from generators import GENERATOR_TYPES, generate, write_csv
from gui_support import build_solver_command, run_solver
from lab_utils import detect_build_type, log_line

KNOWN_ALGORITHMS = ("marathe", "wan", "funke", "li")


class PreflightError(RuntimeError):
    """Fatal preflight failure."""


def run_preflight(
    config: dict[str, Any],
    executable: Path,
    repo_root: Path,
    *,
    verbose: bool = True,
    show_progress: bool = False,
) -> None:
    """Raise PreflightError on fatal issues. Print warnings otherwise."""

    def note(msg: str) -> None:
        log_line(msg, progress=show_progress, verbose=True)

    if not executable.is_file():
        raise PreflightError(f"solver executable not found: {executable}")

    build_type = detect_build_type(executable)
    if build_type == "Debug":
        note(
            "WARNING:\n"
            "Solver appears to be a Debug build.\n"
            "Runtime measurements may not be representative."
        )

    # Solver launches
    try:
        help_out = subprocess.run(
            [str(executable), "--help"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if help_out.returncode not in (0, 2) and "usage" not in (help_out.stdout + help_out.stderr).lower():
            note(f"WARNING: solver --help returned {help_out.returncode}")
    except Exception as exc:  # noqa: BLE001
        raise PreflightError(f"solver failed to launch: {exc}") from exc

    for key in ("distributions", "sizes", "seeds"):
        if key not in config or not config[key]:
            raise PreflightError(f"config missing or empty required key {key!r}")

    algorithms = list(config.get("algorithms", ["marathe"]))
    if not algorithms:
        raise PreflightError("algorithms list is empty")
    for algo in algorithms:
        if algo not in KNOWN_ALGORITHMS:
            raise PreflightError(f"unrecognized algorithm {algo!r}; known={KNOWN_ALGORITHMS}")

    for dist in config["distributions"]:
        if dist not in GENERATOR_TYPES:
            raise PreflightError(f"unknown distribution {dist!r}")

    # Writable output dirs
    for key, default in (
        ("datasets_dir", "datasets/generated"),
        ("results_dir", "results/runs"),
    ):
        path = repo_root / config.get(key, default)
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".preflight_write_probe"
        try:
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
        except OSError as exc:
            raise PreflightError(f"output directory not writable: {path} ({exc})") from exc

    # Python deps
    try:
        import matplotlib  # noqa: F401
    except ImportError as exc:
        raise PreflightError("matplotlib is required; install python/requirements.txt") from exc
    try:
        import tqdm  # noqa: F401
    except ImportError as exc:
        raise PreflightError("tqdm is required; install python/requirements.txt") from exc

    # Tiny connected dataset + each algorithm
    with tempfile.TemporaryDirectory(prefix="mcds_preflight_") as tmp:
        tmp_path = Path(tmp)
        csv_path = tmp_path / "preflight.csv"
        # Dense enough to connect at tiny n.
        result = generate("uniform", 12, 1, density=8.0)
        write_csv(str(csv_path), result.points)

        conn_json = tmp_path / "conn.json"
        conn = run_solver(
            build_solver_command(executable, csv_path, conn_json, check_connectivity_only=True)
        )
        if not conn.result or not conn.result.get("connected_input"):
            lines = ["id,x,y"] + [f"{i},{i * 0.5},0.0" for i in range(12)]
            csv_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            conn = run_solver(
                build_solver_command(executable, csv_path, conn_json, check_connectivity_only=True)
            )
            if not conn.result or not conn.result.get("connected_input"):
                raise PreflightError("failed to produce a connected preflight dataset")

        for algo in algorithms:
            out_json = tmp_path / f"{algo}.json"
            outcome = run_solver(
                build_solver_command(executable, csv_path, out_json, algorithm=algo)
            )
            if outcome.exit_code != 0 or not outcome.result:
                raise PreflightError(
                    f"preflight algorithm {algo!r} failed: {outcome.error or outcome.stderr}"
                )
            if not outcome.result.get("valid_dominating") or not outcome.result.get("valid_connected"):
                raise PreflightError(f"preflight algorithm {algo!r} failed CDS validation")
            # Ensure JSON parses
            json.loads(out_json.read_text(encoding="utf-8"))

    if shutil.which("git") is None:
        note("WARNING: git not found; provenance will be incomplete")

    if sys.version_info < (3, 10):
        note(f"WARNING: Python {sys.version.split()[0]} is below recommended 3.10+")

    note("Preflight checks passed.")
