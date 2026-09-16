"""One-command study orchestration for the MCDS experiment laboratory."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_PYTHON_DIR = Path(__file__).resolve().parent
if str(_PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(_PYTHON_DIR))

from experiment_runner import load_config, run_campaign  # noqa: E402
from gui_support import find_repo_root  # noqa: E402
from lab_utils import config_sha256, log_line  # noqa: E402


def _study_already_complete(state_path: Path) -> bool:
    if not state_path.is_file():
        return False
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    return state.get("status") in {"completed", "completed_with_failures"} and not state.get(
        "interrupted"
    )


def prepare_study_dirs(repo: Path, config: dict[str, Any], config_path: Path) -> dict[str, Any]:
    """Ensure study_dir layout exists and rewrite relative paths into it."""
    batch_id = config.get("batch_id")
    if not batch_id:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        batch_id = f"{config_path.stem}_{stamp}"
    study_dir = repo / config.get("study_dir", f"results/studies/{batch_id}")
    study_dir = study_dir if study_dir.is_absolute() else repo / study_dir
    (study_dir / "datasets").mkdir(parents=True, exist_ok=True)
    (study_dir / "runs").mkdir(parents=True, exist_ok=True)
    (study_dir / "plots").mkdir(parents=True, exist_ok=True)

    # Mutate a copy used for the campaign.
    cfg = dict(config)
    cfg["batch_id"] = batch_id
    cfg["study_dir"] = str(study_dir.relative_to(repo)).replace("\\", "/")
    cfg.setdefault("datasets_dir", str((study_dir / "datasets").relative_to(repo)).replace("\\", "/"))
    cfg.setdefault("results_dir", str((study_dir / "runs").relative_to(repo)).replace("\\", "/"))
    cfg.setdefault(
        "experiments_csv",
        str((study_dir / "experiments.csv").relative_to(repo)).replace("\\", "/"),
    )
    cfg.setdefault(
        "manifest_path",
        str((study_dir / "batch_manifest.json").relative_to(repo)).replace("\\", "/"),
    )
    return {"batch_id": batch_id, "study_dir": study_dir, "config": cfg}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a complete MCDS study pipeline.")
    parser.add_argument("--config", required=True, help="experiment JSON config")
    parser.add_argument("--force", action="store_true", help="rerun completed trials")
    parser.add_argument("--dry-run", action="store_true", help="preview only")
    parser.add_argument("--no-progress", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--skip-preflight", action="store_true")
    parser.add_argument("--no-memory", action="store_true")
    parser.add_argument("--no-plots", action="store_true")
    args = parser.parse_args(argv)

    repo = find_repo_root()
    config_path = Path(args.config)
    if not config_path.is_file():
        config_path = repo / args.config
    raw = load_config(config_path)
    prepared = prepare_study_dirs(repo, raw, config_path)
    study_dir: Path = prepared["study_dir"]
    cfg: dict[str, Any] = prepared["config"]

    state_path = study_dir / "batch_state.json"
    if not args.force and not args.dry_run and _study_already_complete(state_path):
        print("Study already complete.")
        print("Use --force to rerun.")
        return 0

    # Write a temporary config with study paths so campaign uses them.
    tmp_config = study_dir / "resolved_config.json"
    cfg["config_sha256"] = config_sha256(raw)
    tmp_config.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")

    stats = run_campaign(
        tmp_config,
        force=args.force,
        measure_memory=not args.no_memory,
        show_progress=not args.no_progress,
        verbose=args.verbose,
        dry_run=args.dry_run,
        skip_preflight=args.skip_preflight,
    )

    if stats.get("dry_run"):
        return 0
    if stats.get("preflight_failed"):
        return 2
    if stats.get("interrupted"):
        return 130

    experiments_csv = Path(stats.get("experiments_csv", study_dir / "experiments.csv"))

    # Failures + summary
    try:
        from study_report import generate_study_report

        generate_study_report(
            study_dir,
            experiments_csv,
            study_dir / "batch_manifest.json",
            study_dir / "batch_state.json",
        )
    except Exception as exc:  # noqa: BLE001
        log_line(f"WARNING: study report failed: {exc}", progress=False, verbose=True)

    # Plots
    if not args.no_plots:
        try:
            from plots import generate_plots

            exact = repo / "results" / "exact_small_study.csv"
            paths = generate_plots(
                experiments_csv,
                study_dir / "plots",
                exact if exact.is_file() else None,
            )
            for path in paths:
                log_line(f"wrote {path}", progress=False, verbose=True)
        except Exception as exc:  # noqa: BLE001
            log_line(f"WARNING: plot generation failed: {exc}", progress=False, verbose=True)

    print(json.dumps({k: stats[k] for k in stats if k != "preview"}, indent=2))
    return 0 if stats.get("runs_failed", 0) == 0 and stats.get("datasets_failed", 0) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
