"""Tests for python/visualization.py (headless matplotlib)."""

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
    VisualizationError,
    cds_edges,
    downsample_ordinary_indices,
    load_metadata_sidecar,
    load_result_json,
    prepare_plot_data,
    render,
)


def _write_points(path: Path, coords: list[tuple[float, float]]) -> None:
    write_csv(str(path), coords)


def _write_result(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


class VisualizationTests(unittest.TestCase):
    def test_csv_and_json_loading_and_selected_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            points = tmp_path / "points.csv"
            result = tmp_path / "result.json"
            _write_points(points, [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0)])
            _write_result(
                result,
                {
                    "algorithm": "marathe",
                    "n": 3,
                    "radius": 1.0,
                    "cds_size": 1,
                    "cds_ratio": 1.0 / 3.0,
                    "algorithm_ms": 0.1,
                    "algorithm_neighbor_queries": 4,
                    "valid_dominating": True,
                    "valid_connected": True,
                    "selected_ids": [1],
                },
            )
            data = prepare_plot_data(points, result)
            self.assertEqual(data.point_ids, [0, 1, 2])
            self.assertEqual(data.selected_ids, [1])
            self.assertEqual(data.radius, 1.0)

    def test_missing_selected_id_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            points = tmp_path / "points.csv"
            result = tmp_path / "result.json"
            _write_points(points, [(0.0, 0.0), (1.0, 0.0)])
            _write_result(result, {"radius": 1.0, "selected_ids": [0, 99]})
            with self.assertRaises(VisualizationError):
                prepare_plot_data(points, result)

    def test_radius_parsing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            points = tmp_path / "points.csv"
            result = tmp_path / "result.json"
            _write_points(points, [(0.0, 0.0)])
            _write_result(result, {"radius": "1.5", "selected_ids": [0]})
            data = prepare_plot_data(points, result)
            self.assertEqual(data.radius, 1.5)

            _write_result(result, {"radius": "nope", "selected_ids": [0]})
            with self.assertRaises(VisualizationError):
                prepare_plot_data(points, result)

    def test_metadata_sidecar_parsing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            points = tmp_path / "points.csv"
            meta = tmp_path / "points.meta.json"
            _write_points(points, [(0.0, 0.0)])
            meta.write_text(
                json.dumps(
                    {
                        "distribution": "uniform",
                        "seed": 42,
                        "generator_parameters": {"width": 10, "height": 5},
                    }
                ),
                encoding="utf-8",
            )
            loaded = load_metadata_sidecar(points)
            self.assertEqual(loaded["distribution"], "uniform")
            self.assertEqual(loaded["generator_parameters"]["width"], 10)

            # Visualization still works with no sidecar.
            other = tmp_path / "other.csv"
            _write_points(other, [(1.0, 1.0)])
            self.assertEqual(load_metadata_sidecar(other), {})

    def test_headless_png_creation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            points = tmp_path / "points.csv"
            result = tmp_path / "result.json"
            png = tmp_path / "out.png"
            _write_points(points, [(0.0, 0.0), (0.5, 0.0), (1.0, 0.0), (10.0, 10.0)])
            _write_result(
                result,
                {
                    "algorithm": "marathe",
                    "n": 4,
                    "radius": 1.0,
                    "cds_size": 2,
                    "cds_ratio": 0.5,
                    "algorithm_ms": 0.2,
                    "valid_dominating": True,
                    "valid_connected": True,
                    "selected_ids": [0, 1],
                },
            )
            render(points, result, save=png, show=False, show_cds_edges=True)
            self.assertTrue(png.is_file())
            self.assertGreater(png.stat().st_size, 1000)

    def test_cds_edges_only_within_radius(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            points = tmp_path / "points.csv"
            result = tmp_path / "result.json"
            _write_points(points, [(0.0, 0.0), (1.0, 0.0), (3.0, 0.0)])
            _write_result(result, {"radius": 1.0, "selected_ids": [0, 1, 2]})
            data = prepare_plot_data(points, result)
            edges = cds_edges(data, enabled=True)
            # Only 0-1 is within radius 1.
            self.assertEqual(len(edges), 1)

    def test_large_n_downsampling_determinism(self) -> None:
        n = 5000
        selected = {0, 10, 100}
        point_ids = list(range(n))
        a = downsample_ordinary_indices(n, selected, point_ids, max_render_points=200, seed=7)
        b = downsample_ordinary_indices(n, selected, point_ids, max_render_points=200, seed=7)
        c = downsample_ordinary_indices(n, selected, point_ids, max_render_points=200, seed=8)
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)
        # Selected indices are not required in the ordinary sample list; the
        # ordinary budget excludes them. Ensure sample size respects budget.
        self.assertLessEqual(len(a), 200)

    def test_invalid_json_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            path.write_text("{not json", encoding="utf-8")
            with self.assertRaises(VisualizationError):
                load_result_json(path)


if __name__ == "__main__":
    unittest.main()
