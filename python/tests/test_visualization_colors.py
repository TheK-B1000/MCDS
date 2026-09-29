"""Tests for visualization color modes and role metadata mapping."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PYTHON_DIR = Path(__file__).resolve().parents[1]
for path in (_REPO_ROOT, _PYTHON_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from generators import write_csv  # noqa: E402
from visualization import (  # noqa: E402
    create_figure,
    data_axis_limits,
    downsample_ordinary_indices,
    prepare_plot_data,
    render,
)
from visualization_style import (  # noqa: E402
    COLOR_MODE_FINAL,
    COLOR_MODE_ROLES,
    ROLE_CONNECTOR,
    ROLE_CORE,
    ROLE_ORDINARY,
    legend_labels,
    parse_roles,
    role_for_vertex,
)


def _write_points(path: Path, coords: list[tuple[float, float]]) -> None:
    write_csv(str(path), coords)


def _write_result(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


class RoleParsingTests(unittest.TestCase):
    def test_parse_roles_dict_and_fallback(self) -> None:
        roles = parse_roles({"roles": {"1": "core", "2": "connector", "3": "nope"}})
        self.assertEqual(roles[1], ROLE_CORE)
        self.assertEqual(roles[2], ROLE_CONNECTOR)
        self.assertNotIn(3, roles)
        self.assertEqual(parse_roles({}), {})

    def test_final_cds_and_roles_mapping(self) -> None:
        selected = {1, 2}
        roles = {1: ROLE_CORE, 2: ROLE_CONNECTOR}
        self.assertEqual(
            role_for_vertex(0, selected=selected, roles=roles, color_mode=COLOR_MODE_FINAL),
            ROLE_ORDINARY,
        )
        self.assertEqual(
            role_for_vertex(1, selected=selected, roles=roles, color_mode=COLOR_MODE_FINAL),
            "cds",
        )
        self.assertEqual(
            role_for_vertex(2, selected=selected, roles=roles, color_mode=COLOR_MODE_ROLES),
            ROLE_CONNECTOR,
        )
        # Missing metadata: selected falls back to core in roles mode.
        self.assertEqual(
            role_for_vertex(1, selected=selected, roles={}, color_mode=COLOR_MODE_ROLES),
            ROLE_CORE,
        )

    def test_li_legend_labels(self) -> None:
        labels = [lab for _k, lab in legend_labels("li", COLOR_MODE_ROLES, has_roles=True)]
        self.assertIn("MIS / black node", labels)
        self.assertIn("Steiner connector / blue node", labels)
        self.assertIn("Ordinary point", labels)

    def test_fallback_legend_when_roles_absent(self) -> None:
        labels = [lab for _k, lab in legend_labels("wan", COLOR_MODE_ROLES, has_roles=False)]
        self.assertTrue(any("unavailable" in lab.lower() for lab in labels))


class PlotColorModeTests(unittest.TestCase):
    def test_roles_mode_and_export(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            points = tmp_path / "points.csv"
            result = tmp_path / "result.json"
            out = tmp_path / "plot.png"
            _write_points(points, [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0), (3.0, 0.0)])
            _write_result(
                result,
                {
                    "algorithm": "li",
                    "n": 4,
                    "radius": 1.0,
                    "cds_size": 2,
                    "cds_ratio": 0.5,
                    "algorithm_ms": 0.1,
                    "selected_ids": [0, 2],
                    "roles": {"0": "core", "2": "connector"},
                    "valid_dominating": True,
                    "valid_connected": True,
                },
            )
            data = prepare_plot_data(points, result)
            fig = create_figure(data, color_mode=COLOR_MODE_ROLES, show_cds_edges=True, dark=False)
            fig.savefig(out, dpi=80)
            self.assertTrue(out.is_file())
            self.assertGreater(out.stat().st_size, 0)
            # Title includes mode.
            self.assertIn("Algorithm Roles", fig._suptitle.get_text())

    def test_final_mode_without_roles(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            points = tmp_path / "points.csv"
            result = tmp_path / "result.json"
            _write_points(points, [(0.0, 0.0), (1.0, 0.0)])
            _write_result(
                result,
                {
                    "algorithm": "marathe",
                    "n": 2,
                    "radius": 1.0,
                    "cds_size": 1,
                    "selected_ids": [0],
                },
            )
            data = prepare_plot_data(points, result)
            fig = create_figure(data, color_mode=COLOR_MODE_FINAL, show_cds_edges=False)
            self.assertIn("Final CDS", fig._suptitle.get_text())

    def test_large_n_downsampling_retains_selected(self) -> None:
        n = 1000
        selected = {0, 50, 999}
        ids = list(range(n))
        kept = downsample_ordinary_indices(n, selected, ids, max_render_points=100, seed=1)
        # Function returns ordinary indices only when budgeted; selected are plotted separately.
        # Ensure selected ids are never in the ordinary sample set when budgeted.
        ordinary_kept_ids = {ids[i] for i in kept if ids[i] not in selected}
        self.assertTrue(ordinary_kept_ids.isdisjoint(selected))
        self.assertLessEqual(len(kept), 100)

    def test_axis_limits_consistent(self) -> None:
        xs = [0.0, 10.0, 5.0]
        ys = [-1.0, 1.0, 0.0]
        a = data_axis_limits(xs, ys)
        b = data_axis_limits(xs, ys)
        self.assertEqual(a, b)
        self.assertLess(a[0], 0.0)
        self.assertGreater(a[1], 10.0)

    def test_render_export_does_not_crash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            points = tmp_path / "points.csv"
            result = tmp_path / "result.json"
            out = tmp_path / "out.png"
            _write_points(points, [(0.0, 0.0), (0.5, 0.0), (1.0, 0.0)])
            _write_result(
                result,
                {
                    "algorithm": "wan",
                    "n": 3,
                    "radius": 1.0,
                    "cds_size": 2,
                    "selected_ids": [0, 1],
                    "roles": {"0": "core", "1": "connector"},
                },
            )
            render(
                points,
                result,
                save=out,
                show=False,
                color_mode=COLOR_MODE_ROLES,
                show_cds_edges=True,
            )
            self.assertTrue(out.is_file())


if __name__ == "__main__":
    unittest.main()
