"""Centralized plot colors and role/legend helpers for MCDS visualization.

Algorithms are not consulted here except via optional ``roles`` metadata in the
result JSON. Styling values live in one place so GUI and CLI plots stay consistent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

COLOR_MODE_FINAL = "Final CDS"
COLOR_MODE_ROLES = "Algorithm roles"
COLOR_MODES = (COLOR_MODE_FINAL, COLOR_MODE_ROLES)

ROLE_CORE = "core"
ROLE_CONNECTOR = "connector"
ROLE_ORDINARY = "ordinary"


@dataclass(frozen=True)
class VisualizationColors:
    """Palette for one theme (light or dark)."""

    background: str
    axis_background: str
    ordinary: str
    cds: str  # Final CDS selected color (blue)
    cds_edge_marker: str
    core: str  # dark / black
    connector: str  # blue
    text: str
    muted: str
    spine: str


LIGHT = VisualizationColors(
    background="#ffffff",
    axis_background="#ffffff",
    ordinary="#b0b8c1",
    cds="#2563eb",
    cds_edge_marker="#1e3a8a",
    core="#111827",
    connector="#2563eb",
    text="#1f2933",
    muted="#4a5560",
    spine="#cbd2d9",
)

DARK = VisualizationColors(
    background="#1e1e1e",
    axis_background="#252526",
    ordinary="#8b949e",
    cds="#60a5fa",
    cds_edge_marker="#1d4ed8",
    core="#e5e7eb",
    connector="#60a5fa",
    text="#e6edf3",
    muted="#9da7b3",
    spine="#3c4048",
)


def palette(dark: bool = False) -> VisualizationColors:
    return DARK if dark else LIGHT


def parse_roles(result: Mapping[str, Any]) -> dict[int, str]:
    """Extract optional ``roles`` map from a result JSON object.

    Accepts ``{"12": "core", ...}`` or a list of ``{"id": 12, "role": "core"}``.
    Unknown / malformed entries are skipped.
    """
    raw = result.get("roles")
    out: dict[int, str] = {}
    if isinstance(raw, dict):
        for key, value in raw.items():
            try:
                vid = int(key)
            except (TypeError, ValueError):
                continue
            role = str(value).strip().lower()
            if role in {ROLE_CORE, ROLE_CONNECTOR}:
                out[vid] = role
        return out
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            try:
                vid = int(item.get("id"))
            except (TypeError, ValueError):
                continue
            role = str(item.get("role", "")).strip().lower()
            if role in {ROLE_CORE, ROLE_CONNECTOR}:
                out[vid] = role
    return out


def roles_available(result: Mapping[str, Any]) -> bool:
    return bool(parse_roles(result))


def role_for_vertex(
    vertex_id: int,
    *,
    selected: set[int],
    roles: Mapping[int, str],
    color_mode: str,
) -> str:
    """Return ordinary / core / connector for coloring one vertex."""
    if vertex_id not in selected:
        return ROLE_ORDINARY
    if color_mode == COLOR_MODE_ROLES and roles:
        return roles.get(vertex_id, ROLE_CORE)
    # Final CDS mode, or roles mode without metadata: treat all selected alike.
    return ROLE_CORE if color_mode == COLOR_MODE_ROLES else "cds"


def legend_labels(algorithm: str, color_mode: str, *, has_roles: bool) -> list[tuple[str, str]]:
    """Return ``(role_key, display_label)`` pairs for the legend.

    ``role_key`` is one of ordinary / cds / core / connector (points only; no edges are drawn).
    """
    algo = (algorithm or "").strip().lower()
    if color_mode == COLOR_MODE_FINAL or not has_roles:
        items = [
            (ROLE_ORDINARY, "Ordinary point"),
            ("cds", "CDS node"),
        ]
        if color_mode == COLOR_MODE_ROLES and not has_roles:
            items = [
                (ROLE_ORDINARY, "Ordinary point"),
                (ROLE_CORE, "Selected (roles unavailable)"),
            ]
        return items

    if algo in {"li", "li_smis", "s-mis", "smis"}:
        return [
            (ROLE_ORDINARY, "Ordinary point"),
            (ROLE_CORE, "MIS / black node"),
            (ROLE_CONNECTOR, "Steiner connector / blue node"),
        ]
    return [
        (ROLE_ORDINARY, "Ordinary point"),
        (ROLE_CORE, "Core selected node"),
        (ROLE_CONNECTOR, "Connector node"),
    ]


def color_mode_title_suffix(color_mode: str) -> str:
    if color_mode == COLOR_MODE_ROLES:
        return "Algorithm Roles"
    return "Final CDS"


FIGURE_SIZE = (8.0, 8.0)
ORDINARY_POINT_SIZE = 8
SELECTED_POINT_SIZE = 36
AXIS_PAD_FRACTION = 0.04
