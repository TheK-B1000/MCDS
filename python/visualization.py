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
from visualization_style import (  # noqa: E402
    AXIS_PAD_FRACTION,
    COLOR_MODE_FINAL,
    COLOR_MODE_ROLES,
    COLOR_MODES,
    FIGURE_SIZE,
    ORDINARY_POINT_SIZE,
    ROLE_CONNECTOR,
    ROLE_CORE,
    ROLE_ORDINARY,
    SELECTED_POINT_SIZE,
    color_mode_title_suffix,
    legend_labels,
    palette,
    parse_roles,
    roles_available,
)

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


def algorithm_display_name(data: PlotData) -> str:
    raw = data.result.get("algorithm", "unknown")
    algo = str(raw if raw is not None else "unknown").strip()
    key = algo.lower().replace("-", "_").replace(" ", "_")
    if key in {"", "none", "null", "preview"}:
        return "Point set"
    if key == "marathe":
        return "Marathe CDOM"
    if key == "wan":
        return "Wan–Alzoubi–Frieder"
    if key == "funke":
        return "Funke–Kesselman–Meyer–Segal"
    if key in {"li", "li_smis", "s_mis", "smis"}:
        return "Li S-MIS"
    return algo.replace("_", " ").title()


def build_stats_line(data: PlotData) -> str:
    result = data.result
    n = int(result.get("n", len(data.point_ids)))
    raw_algo = str(result.get("algorithm", "") or "").strip().lower()
    if raw_algo in {"", "none", "null", "preview"}:
        return f"n={n} | preview — click Run MCDS"
    cds = int(result.get("cds_size", len(data.selected_ids)))
    ratio = float(result.get("cds_ratio", cds / n if n else 0.0))
    runtime = float(result.get("algorithm_ms", 0.0))
    return f"n={n} | CDS={cds} ({100.0 * ratio:.1f}%) | {runtime:.3f} ms"


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


def build_title(data: PlotData) -> str:
    """Full multi-line header used by tests/CLI helpers."""
    lines = [algorithm_display_name(data), build_stats_line(data)]
    subtitle = build_subtitle(data)
    if subtitle:
        lines.append(subtitle)
    return "\n".join(lines)


def data_axis_limits(xs: list[float], ys: list[float]) -> tuple[float, float, float, float]:
    """Shared axis window for same-dataset screenshots across algorithms."""
    if not xs or not ys:
        return 0.0, 1.0, 0.0, 1.0
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    dx = max_x - min_x
    dy = max_y - min_y
    pad_x = dx * AXIS_PAD_FRACTION if dx > 0 else 1.0
    pad_y = dy * AXIS_PAD_FRACTION if dy > 0 else 1.0
    return min_x - pad_x, max_x + pad_x, min_y - pad_y, max_y + pad_y


def create_figure(
    data: PlotData,
    *,
    show_cds_edges: bool = True,
    max_render_points: int = DEFAULT_MAX_RENDER_POINTS,
    edge_k_limit: int = DEFAULT_EDGE_K_LIMIT,
    downsample_seed: int = 0,
    dark: bool = False,
    color_mode: str = COLOR_MODE_FINAL,
):
    """Build a matplotlib Figure for the plot data."""
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    if color_mode not in COLOR_MODES:
        color_mode = COLOR_MODE_FINAL

    colors = palette(dark)
    roles = parse_roles(data.result)
    has_roles = bool(roles)
    effective_mode = color_mode
    role_fallback_note = False
    if color_mode == COLOR_MODE_ROLES and not has_roles:
        role_fallback_note = str(data.result.get("algorithm", "")).lower() not in {
            "",
            "none",
            "null",
            "preview",
        }

    fig, ax = plt.subplots(figsize=FIGURE_SIZE)
    fig.patch.set_facecolor(colors.background)
    ax.set_facecolor(colors.axis_background)

    keep_ids = set(data.selected_set)
    if has_roles:
        keep_ids.update(roles.keys())
    ordinary_indices = downsample_ordinary_indices(
        len(data.point_ids),
        keep_ids,
        data.point_ids,
        max_render_points,
        seed=downsample_seed,
    )
    ox = [data.xs[i] for i in ordinary_indices if data.point_ids[i] not in data.selected_set]
    oy = [data.ys[i] for i in ordinary_indices if data.point_ids[i] not in data.selected_set]
    if ox:
        ax.scatter(
            ox,
            oy,
            s=ORDINARY_POINT_SIZE,
            c=colors.ordinary,
            alpha=0.75,
            linewidths=0,
            label="_nolegend_",
            zorder=1,
        )

    id_to_xy = {pid: (x, y) for pid, x, y in zip(data.point_ids, data.xs, data.ys)}

    def _scatter_selected(ids: list[int], face: str, edge: str) -> None:
        if not ids:
            return
        sx = [id_to_xy[sid][0] for sid in ids if sid in id_to_xy]
        sy = [id_to_xy[sid][1] for sid in ids if sid in id_to_xy]
        if not sx:
            return
        ax.scatter(
            sx,
            sy,
            s=SELECTED_POINT_SIZE,
            c=face,
            edgecolors=edge,
            linewidths=0.4,
            label="_nolegend_",
            zorder=3,
        )

    if effective_mode == COLOR_MODE_ROLES and has_roles:
        core_ids = [sid for sid in data.selected_ids if roles.get(sid) == ROLE_CORE]
        conn_ids = [sid for sid in data.selected_ids if roles.get(sid) == ROLE_CONNECTOR]
        other_ids = [
            sid
            for sid in data.selected_ids
            if roles.get(sid) not in {ROLE_CORE, ROLE_CONNECTOR}
        ]
        _scatter_selected(core_ids + other_ids, colors.core, colors.core)
        _scatter_selected(conn_ids, colors.connector, colors.cds_edge_marker)
    else:
        face = colors.cds if effective_mode == COLOR_MODE_FINAL else colors.core
        edge = colors.cds_edge_marker if effective_mode == COLOR_MODE_FINAL else colors.core
        _scatter_selected(list(data.selected_ids), face, edge)

    edges = cds_edges(data, enabled=show_cds_edges, k_limit=edge_k_limit)
    for x0, y0, x1, y1 in edges:
        ax.plot(
            [x0, x1],
            [y0, y1],
            color=colors.edge,
            alpha=0.40 if dark else 0.35,
            linewidth=0.8,
            zorder=2,
        )

    ax.set_aspect("equal", adjustable="box")
    xmin, xmax, ymin, ymax = data_axis_limits(data.xs, data.ys)
    ax.set_xlim(xmin, xmax)
    ax.set_ylim(ymin, ymax)

    algo_name = algorithm_display_name(data)
    mode_suffix = color_mode_title_suffix(effective_mode)
    if str(data.result.get("algorithm", "")).lower() in {"", "none", "null", "preview"}:
        title = algo_name
    else:
        title = f"{algo_name} — {mode_suffix}"
    stats = build_stats_line(data)
    subtitle = build_subtitle(data)
    if role_fallback_note:
        note = "Role detail unavailable for this algorithm."
        subtitle = f"{subtitle} | {note}" if subtitle else note

    fig.suptitle(title, fontsize=14, fontweight="bold", color=colors.text, y=0.975)
    fig.text(
        0.5,
        0.915,
        stats,
        ha="center",
        va="center",
        fontsize=10,
        color=colors.muted,
        transform=fig.transFigure,
    )
    if subtitle:
        fig.text(
            0.5,
            0.860,
            subtitle,
            ha="center",
            va="center",
            fontsize=10,
            color=colors.muted,
            transform=fig.transFigure,
        )
        axes_top = 0.78
    else:
        axes_top = 0.86

    algo_key = str(data.result.get("algorithm", ""))
    legend_items = legend_labels(algo_key, effective_mode, has_roles=has_roles)
    handles = []
    labels = []
    swatch = {
        ROLE_ORDINARY: colors.ordinary,
        "cds": colors.cds,
        ROLE_CORE: colors.core,
        ROLE_CONNECTOR: colors.connector,
        "edge": colors.edge,
    }
    for key, label in legend_items:
        if key == "edge" and not show_cds_edges:
            continue
        if key == "edge":
            handles.append(Line2D([0], [0], color=swatch[key], linewidth=1.5))
        else:
            size = ORDINARY_POINT_SIZE if key == ROLE_ORDINARY else SELECTED_POINT_SIZE
            handles.append(
                Line2D(
                    [0],
                    [0],
                    marker="o",
                    color="none",
                    markerfacecolor=swatch[key],
                    markeredgecolor=swatch[key],
                    markersize=max(4, size / 4),
                    linestyle="None",
                )
            )
        labels.append(label)
    if handles:
        legend = ax.legend(
            handles,
            labels,
            loc="upper right",
            frameon=False,
            fontsize=8,
            labelcolor=colors.text,
        )
        if legend is not None:
            for text in legend.get_texts():
                text.set_color(colors.text)

    ax.set_xlabel("x", color=colors.text)
    ax.set_ylabel("y", color=colors.text)
    ax.tick_params(colors=colors.muted)
    for spine in ax.spines.values():
        spine.set_color(colors.spine)
    fig.subplots_adjust(left=0.10, right=0.98, bottom=0.08, top=axes_top)
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
    color_mode: str = COLOR_MODE_FINAL,
    dark: bool = False,
):
    """High-level entry used by CLI and GUI."""
    data = prepare_plot_data(points_path, result_path)
    if show_cds_edges is None:
        show_cds_edges = len(data.selected_ids) <= edge_k_limit

    fig = create_figure(
        data,
        show_cds_edges=show_cds_edges,
        max_render_points=max_render_points,
        edge_k_limit=edge_k_limit,
        downsample_seed=downsample_seed,
        dark=dark,
        color_mode=color_mode,
    )

    if save is not None:
        save_path = Path(save)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_path, dpi=140, bbox_inches="tight", pad_inches=0.35)

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
        "--color-mode",
        choices=list(COLOR_MODES),
        default=COLOR_MODE_FINAL,
        help="Final CDS vs Algorithm roles coloring",
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
            color_mode=args.color_mode,
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
