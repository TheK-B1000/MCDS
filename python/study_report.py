"""Generate study artifacts: failures.csv and batch_summary.md."""

from __future__ import annotations

import csv
import json
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def write_failures_csv(experiments_csv: Path, out_path: Path) -> int:
    if not experiments_csv.is_file():
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("", encoding="utf-8")
        return 0

    preferred = [
        "run_id",
        "algorithm",
        "distribution",
        "density",
        "n",
        "base_seed",
        "dataset_sha256",
        "status",
        "exit_code",
        "error",
        "algorithm_ms",
        "peak_memory_mb",
    ]
    with experiments_csv.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        all_fields = list(reader.fieldnames or [])
        rows = [row for row in reader if row.get("status") != "ok"]

    fields = [f for f in preferred if f in all_fields] or all_fields
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else float("nan")


def write_batch_summary(
    experiments_csv: Path,
    manifest_path: Path,
    batch_state_path: Path,
    out_path: Path,
    *,
    plot_dir: Path | None = None,
) -> None:
    manifest: dict[str, Any] = {}
    batch_state: dict[str, Any] = {}
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if batch_state_path.is_file():
        batch_state = json.loads(batch_state_path.read_text(encoding="utf-8"))

    rows: list[dict[str, str]] = []
    if experiments_csv.is_file():
        with experiments_csv.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))

    status_counts = Counter(r.get("status", "?") for r in rows)
    ok = [r for r in rows if r.get("status") == "ok"]
    config = manifest.get("config") or {}

    lines = [
        "# Study Summary",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Configuration",
        "",
        f"- Batch ID: `{manifest.get('batch_id', config.get('batch_id', 'unknown'))}`",
        f"- Config SHA256: `{manifest.get('config_sha256', '')}`",
        f"- Algorithms: {config.get('algorithms', [])}",
        f"- Distributions: {config.get('distributions', [])}",
        f"- Densities: {config.get('densities', [config.get('density')])}",
        f"- Sizes: {config.get('sizes', [])}",
        f"- Seeds: {config.get('seeds', [])}",
        f"- Radius: {config.get('radius', 1.0)}",
        f"- Timing repetitions: {config.get('timing_repetitions', 1)}",
        f"- Warmup runs: {config.get('warmup_runs', 0)}",
        f"- Max runtime seconds: {config.get('max_runtime_seconds', config.get('timeout_s'))}",
        f"- Max peak memory MB: {config.get('max_peak_memory_mb', config.get('max_memory_mb'))}",
        "",
        "## Machine / Build",
        "",
        f"- OS: {manifest.get('os', 'unknown')}",
        f"- CPU: {manifest.get('cpu', 'unknown')}",
        f"- Total RAM MB: {manifest.get('total_ram_mb', 'unknown')}",
        f"- Python: {manifest.get('python_version', 'unknown')}",
        f"- Solver: `{manifest.get('solver_path', 'unknown')}`",
        f"- Build type: {manifest.get('build_type', 'unknown')}",
        f"- Git commit: `{(manifest.get('git') or {}).get('commit', 'unknown')}`",
        f"- Git dirty: {(manifest.get('git') or {}).get('dirty', 'unknown')}",
        "",
        "## Completion",
        "",
        f"- Status: `{batch_state.get('status', 'unknown')}`",
        f"- Total CSV rows: {len(rows)}",
        f"- OK: {status_counts.get('ok', 0)}",
        f"- Failed/other: {sum(v for k, v in status_counts.items() if k != 'ok')}",
        f"- Interrupted: {batch_state.get('interrupted', False)}",
        "",
        "## Correctness",
        "",
    ]
    if ok:
        valid = sum(
            1
            for r in ok
            if str(r.get("valid_dominating")).lower() in {"true", "1"}
            and str(r.get("valid_connected")).lower() in {"true", "1"}
        )
        lines.append(f"- Valid CDS among OK runs: {valid}/{len(ok)}")
    else:
        lines.append("- No successful runs.")

    lines += ["", "## CDS Quality", ""]
    by_algo: dict[str, list[float]] = defaultdict(list)
    for r in ok:
        if r.get("cds_ratio") not in ("", None):
            by_algo[r["algorithm"]].append(float(r["cds_ratio"]))
    for algo in sorted(by_algo):
        vals = by_algo[algo]
        lines.append(
            f"- {algo}: mean CDS ratio={_mean(vals):.4f}, "
            f"median={statistics.median(vals):.4f}, n={len(vals)}"
        )

    lines += ["", "## Runtime", ""]
    by_ms: dict[str, list[float]] = defaultdict(list)
    for r in ok:
        if r.get("algorithm_ms") not in ("", None):
            by_ms[r["algorithm"]].append(float(r["algorithm_ms"]))
    for algo in sorted(by_ms):
        vals = by_ms[algo]
        lines.append(f"- {algo}: median ms={statistics.median(vals):.4f}")

    lines += ["", "## Memory", ""]
    by_mem: dict[str, list[float]] = defaultdict(list)
    for r in ok:
        if r.get("peak_memory_mb") not in ("", None):
            by_mem[r["algorithm"]].append(float(r["peak_memory_mb"]))
    for algo in sorted(by_mem):
        vals = by_mem[algo]
        lines.append(f"- {algo}: mean peak MB={_mean(vals):.3f}")

    lines += ["", "## Neighbor Query Cost", ""]
    by_q: dict[str, list[float]] = defaultdict(list)
    for r in ok:
        if r.get("algorithm_neighbor_queries") not in ("", None):
            by_q[r["algorithm"]].append(float(r["algorithm_neighbor_queries"]))
    for algo in sorted(by_q):
        vals = by_q[algo]
        lines.append(f"- {algo}: mean queries={_mean(vals):.1f}")

    lines += [
        "",
        "## Density Results",
        "",
        "See experiments.csv grouped by density (when present).",
        "",
        "## Geometry Results",
        "",
        "See experiments.csv grouped by distribution.",
        "",
        "## Scaling Results",
        "",
        "See plots of metrics vs n when generated.",
        "",
        "## Exact-Small Results",
        "",
        "See results/exact_small_study.csv when available.",
        "",
        "## Explicit vs Implicit Results",
        "",
        "See results/explicit_vs_implicit.csv when available.",
        "",
        "## Failures",
        "",
    ]
    for status, count in sorted(status_counts.items()):
        if status == "ok":
            continue
        lines.append(f"- `{status}`: {count}")
    if status_counts.get("ok", 0) == len(rows) and rows:
        lines.append("- None.")

    lines += ["", "## Plot Files", ""]
    if plot_dir and plot_dir.is_dir():
        plots = sorted(plot_dir.glob("*.png"))
        if plots:
            for p in plots:
                lines.append(f"- `{p.name}`")
        else:
            lines.append("- (none yet)")
    else:
        lines.append("- (plot directory not present)")

    lines.append("")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")


def generate_study_report(
    study_dir: Path,
    experiments_csv: Path,
    manifest_path: Path,
    batch_state_path: Path,
) -> None:
    write_failures_csv(experiments_csv, study_dir / "failures.csv")
    write_batch_summary(
        experiments_csv,
        manifest_path,
        batch_state_path,
        study_dir / "batch_summary.md",
        plot_dir=study_dir / "plots",
    )
