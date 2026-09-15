"""Visualize an implicit-UDG point set and an MCDS result.

Reads a point CSV and a result JSON produced by the C++ ``mcds`` executable.
Does not run any MCDS algorithm.

Example:

    python python/visualization.py \\
        --points datasets/e2e_bridge_300.csv \\
        --result results/e2e_bridge_300.json \\
        --save results/e2e_bridge_300.png \\
        --no-show
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Allow importing sibling modules when run as a script.
_PYTHON_DIR = Path(__file__).resolve().parent
if str(_PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(_PYTHON_DIR))

from generators import read_csv  # noqa: E402

# CDS edge drawing is skipped when the selected set exceeds this size unless
# the caller forces it. Avoids an accidental O(k^2) visualization cost.
DEFAULT_EDGE_K_LIMIT = 2000
DEFAULT_MAX_RENDER_POINTS = 50_000


@dataclass
class PlotData:
    """Parsed inputs ready for plotting."""

    point_ids: list[int]
    xs: list[float]
    ys: list[float]
    selected_ids: list[int]
    selected_set: set[int]
    radius: float
    result: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)


class VisualizationError(ValueError):
    """User-facing visualization failure."""


def load_result_json(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError as exc:
        raise VisualizationError(f"result file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise VisualizationError(f"invalid result JSON: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise VisualizationError(f"result JSON must be an object: {path}")
    return data


def load_metadata_sidecar(points_path: str | Path) -> dict[str, Any]:
    """Load optional dataset sidecar ``<stem>.meta.json`` if present.

    Never invents generator parameters from coordinates.
    """
    points_path = Path(points_path)
    candidates = [
        points_path.with_suffix(points_path.suffix + ".meta.json"),
        points_path.with_name(points_path.stem + ".meta.json"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            try:
                # utf-8-sig tolerates a BOM written by some Windows tools.
                with candidate.open("r", encoding="utf-8-sig") as handle:
                    data = json.load(handle)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict):
                return data
    return {}


def prepare_plot_data(points_path: str | Path, result_path: str | Path) -> PlotData:
    rows = read_csv(str(points_path))
    if not rows:
        raise VisualizationError(f"point CSV contains no points: {points_path}")

    result = load_result_json(result_path)
    selected_raw = result.get("selected_ids")
    if selected_raw is None:
        raise VisualizationError("result JSON missing 'selected_ids'")
    if not isinstance(selected_raw, list):
        raise VisualizationError("'selected_ids' must be a list")

    try:
        selected_ids = [int(x) for x in selected_raw]
    except (TypeError, ValueError) as exc:
        raise VisualizationError("selected_ids must be integers") from exc

    try:
        radius = float(result.get("radius", 1.0))
    except (TypeError, ValueError) as exc:
        raise VisualizationError("result radius is not numeric") from exc
    if radius < 0.0:
        raise VisualizationError("result radius must be non-negative")

    id_to_index = {row[0]: i for i, row in enumerate(rows)}
    missing = [sid for sid in selected_ids if sid not in id_to_index]
    if missing:
        preview = ", ".join(str(x) for x in missing[:8])
        raise VisualizationError(
            f"{len(missing)} selected id(s) not present in point CSV "
            f"(examples: {preview})"
        )

    metadata = load_metadata_sidecar(points_path)
    return PlotData(
        point_ids=[row[0] for row in rows],
        xs=[row[1] for row in rows],
        ys=[row[2] for row in rows],
        selected_ids=selected_ids,
        selected_set=set(selected_ids),
        radius=radius,
        result=result,
        metadata=metadata,
    )


def downsample_ordinary_indices(
    n: int,
    selected: set[int],
    point_ids: list[int],
    max_render_points: int,
    seed: int = 0,
) -> list[int]:
    """Deterministically sample ordinary (non-CDS) point indices for display.

    Selected CDS points are never dropped here; the caller plots them separately.
    """
    if max_render_points <= 0 or n <= max_render_points:
        return list(range(n))

    ordinary = [i for i, pid in enumerate(point_ids) if pid not in selected]
    # Budget for ordinary points after reserving room for all CDS markers.
    ordinary_budget = max(0, max_render_points - len(selected))
    if len(ordinary) <= ordinary_budget:
        return list(range(n))

    rng = random.Random(seed)
    sampled = rng.sample(ordinary, ordinary_budget)
    sampled.sort()
    return sampled


def cds_edges(
    data: PlotData,
    *,
    enabled: bool = True,
    k_limit: int = DEFAULT_EDGE_K_LIMIT,
) -> list[tuple[float, float, float, float]]:
    """Return CDS-to-CDS edge segments within ``radius``.

    Uses a uniform grid over the selected points so cost is near-linear in k
    for bounded density, not a blind O(k^2) double loop when k is large.
    """
    k = len(data.selected_ids)
    if not enabled or k < 2:
        return []
    if k > k_limit:
        return []

    id_to_xy = {pid: (x, y) for pid, x, y in zip(data.point_ids, data.xs, data.ys)}
    selected = [(sid, id_to_xy[sid]) for sid in data.selected_ids]
    radius = data.radius
    radius_sq = radius * radius
    cell = max(radius, 1e-12)

    buckets: dict[tuple[int, int], list[tuple[int, float, float]]] = {}
    for sid, (x, y) in selected:
        key = (int(math.floor(x / cell)), int(math.floor(y / cell)))
        buckets.setdefault(key, []).append((sid, x, y))

    edges: list[tuple[float, float, float, float]] = []
    seen: set[tuple[int, int]] = set()
    for (gx, gy), members in buckets.items():
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                others = buckets.get((gx + dx, gy + dy))
                if not others:
                    continue
                for a_id, ax, ay in members:
                    for b_id, bx, by in others:
                        if a_id >= b_id:
                            continue
                        pair = (a_id, b_id)
                        if pair in seen:
                            continue
                        if (ax - bx) * (ax - bx) + (ay - by) * (ay - by) <= radius_sq:
                            seen.add(pair)
                            edges.append((ax, ay, bx, by))
    return edges


def build_title(data: PlotData) -> str:
    result = data.result
    algo = str(result.get("algorithm", "unknown")).replace("_", " ").title()
    if algo.lower() == "marathe":
        algo = "Marathe CDOM"
    elif algo.lower() == "wan":
        algo = "Wan–Alzoubi–Frieder"
    n = int(result.get("n", len(data.point_ids)))
    cds = int(result.get("cds_size", len(data.selected_ids)))
    ratio = float(result.get("cds_ratio", cds / n if n else 0.0))
    runtime = float(result.get("algorithm_ms", 0.0))
    return f"{algo}\nn={n} | CDS={cds} ({100.0 * ratio:.1f}%) | {runtime:.3f} ms"


def build_subtitle(data: PlotData) -> str:
    parts: list[str] = []
    meta = data.metadata
    if meta.get("distribution"):
        parts.append(str(meta["distribution"]))
    if "seed" in meta or "base_seed" in meta:
        seed = meta.get("effective_seed", meta.get("base_seed", meta.get("seed")))
        parts.append(f"seed={seed}")
    params = meta.get("generator_parameters") or meta.get("parameters") or {}
    if isinstance(params, dict):
        for key in ("width", "height", "spread", "clusters", "corridor_width"):
            if key in params:
                parts.append(f"{key}={params[key]}")

    result = data.result
    valid_d = result.get("valid_dominating")
    valid_c = result.get("valid_connected")
    if valid_d is not None and valid_c is not None:
        status = "valid" if valid_d and valid_c else "INVALID"
        parts.append(status)
    queries = result.get("algorithm_neighbor_queries")
    if queries is not None:
        parts.append(f"queries={queries}")
    return " | ".join(parts)


def create_figure(
    data: PlotData,
    *,
    show_cds_edges: bool = True,
    max_render_points: int = DEFAULT_MAX_RENDER_POINTS,
    edge_k_limit: int = DEFAULT_EDGE_K_LIMIT,
    downsample_seed: int = 0,
):
    """Build a matplotlib Figure for the plot data."""
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8.0, 6.5))

    ordinary_indices = downsample_ordinary_indices(
        len(data.point_ids),
        data.selected_set,
        data.point_ids,
        max_render_points,
        seed=downsample_seed,
    )
    # Plot only non-selected points in the ordinary layer.
    ox = [data.xs[i] for i in ordinary_indices if data.point_ids[i] not in data.selected_set]
    oy = [data.ys[i] for i in ordinary_indices if data.point_ids[i] not in data.selected_set]
    if ox:
        ax.scatter(ox, oy, s=8, c="#9aa5b1", alpha=0.75, linewidths=0, label="points", zorder=1)

    id_to_xy = {pid: (x, y) for pid, x, y in zip(data.point_ids, data.xs, data.ys)}
    sx = [id_to_xy[sid][0] for sid in data.selected_ids]
    sy = [id_to_xy[sid][1] for sid in data.selected_ids]
    if sx:
        ax.scatter(
            sx,
            sy,
            s=36,
            c="#c0392b",
            edgecolors="#5b1a14",
            linewidths=0.4,
            label="CDS",
            zorder=3,
        )

    edges = cds_edges(data, enabled=show_cds_edges, k_limit=edge_k_limit)
    for x0, y0, x1, y1 in edges:
        ax.plot([x0, x1], [y0, y1], color="#c0392b", alpha=0.35, linewidth=0.8, zorder=2)

    ax.set_aspect("equal", adjustable="datalim")
    ax.set_title(build_title(data), fontsize=12, pad=12)
    subtitle = build_subtitle(data)
    if subtitle:
        ax.text(
            0.5,
            1.02,
            subtitle,
            transform=ax.transAxes,
            ha="center",
            va="bottom",
            fontsize=9,
            color="#4a5560",
        )
    ax.legend(loc="best", frameon=False)
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    fig.tight_layout()
    return fig


def render(
    points_path: str | Path,
    result_path: str | Path,
    *,
    save: str | Path | None = None,
    show: bool = True,
    show_cds_edges: bool | None = None,
    max_render_points: int = DEFAULT_MAX_RENDER_POINTS,
    edge_k_limit: int = DEFAULT_EDGE_K_LIMIT,
    downsample_seed: int = 0,
):
    """High-level entry used by CLI and GUI."""
    data = prepare_plot_data(points_path, result_path)
    if show_cds_edges is None:
        # Auto: on for small CDS, off for large.
        show_cds_edges = len(data.selected_ids) <= edge_k_limit

    fig = create_figure(
        data,
        show_cds_edges=show_cds_edges,
        max_render_points=max_render_points,
        edge_k_limit=edge_k_limit,
        downsample_seed=downsample_seed,
    )

    if save is not None:
        save_path = Path(save)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_path, dpi=140, bbox_inches="tight")

    if show:
        import matplotlib.pyplot as plt

        plt.show()
    else:
        import matplotlib.pyplot as plt

        plt.close(fig)

    return fig, data


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Plot a point set and MCDS result (no algorithm runs here).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--points", required=True, help="input point CSV")
    parser.add_argument("--result", required=True, help="mcds result JSON")
    parser.add_argument("--save", default=None, help="optional PNG/SVG output path")
    parser.add_argument("--no-show", action="store_true", help="do not open an interactive window")
    parser.add_argument(
        "--show-cds-edges",
        dest="show_cds_edges",
        action="store_true",
        default=None,
        help="draw edges between adjacent CDS vertices",
    )
    parser.add_argument(
        "--no-cds-edges",
        dest="show_cds_edges",
        action="store_false",
        help="do not draw CDS edges",
    )
    parser.add_argument(
        "--max-render-points",
        type=int,
        default=DEFAULT_MAX_RENDER_POINTS,
        help="max ordinary points drawn (CDS always kept)",
    )
    parser.add_argument(
        "--edge-k-limit",
        type=int,
        default=DEFAULT_EDGE_K_LIMIT,
        help="skip CDS edge drawing when |CDS| exceeds this",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    try:
        render(
            args.points,
            args.result,
            save=args.save,
            show=not args.no_show,
            show_cds_edges=args.show_cds_edges,
            max_render_points=args.max_render_points,
            edge_k_limit=args.edge_k_limit,
        )
    except VisualizationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    # Prefer a non-interactive backend when --no-show is used and DISPLAY is unset.
    if "--no-show" in sys.argv and "MPLBACKEND" not in os.environ:
        import matplotlib

        matplotlib.use("Agg")
    sys.exit(main())
