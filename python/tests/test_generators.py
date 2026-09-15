"""Deterministic tests for python/generators.py.

Run from the repository root:

    python -m unittest python.tests.test_generators -v
"""

from __future__ import annotations

import math
import sys
import tempfile
import unittest
from pathlib import Path

# Allow `python -m unittest discover` and direct imports from repo root / this file.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_PYTHON_DIR = Path(__file__).resolve().parents[1]
for path in (_REPO_ROOT, _PYTHON_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from generators import (  # noqa: E402
    GENERATOR_TYPES,
    csv_bytes,
    generate,
    read_csv,
    write_csv,
)


class DeterminismTests(unittest.TestCase):
    def test_same_seed_byte_identical_for_every_type(self) -> None:
        for gen_type in GENERATOR_TYPES:
            with self.subTest(type=gen_type):
                a = csv_bytes(generate(gen_type, n=200, seed=42, clusters=4).points)
                b = csv_bytes(generate(gen_type, n=200, seed=42, clusters=4).points)
                self.assertEqual(a, b)

    def test_different_seed_normally_differs(self) -> None:
        for gen_type in GENERATOR_TYPES:
            with self.subTest(type=gen_type):
                a = csv_bytes(generate(gen_type, n=200, seed=1, clusters=4).points)
                b = csv_bytes(generate(gen_type, n=200, seed=2, clusters=4).points)
                self.assertNotEqual(a, b)


class SchemaAndIdTests(unittest.TestCase):
    def test_correct_count_unique_ids_and_numeric_coords(self) -> None:
        for gen_type in GENERATOR_TYPES:
            with self.subTest(type=gen_type):
                result = generate(gen_type, n=117, seed=9, clusters=3)
                self.assertEqual(len(result.points), 117)
                for x, y in result.points:
                    self.assertTrue(math.isfinite(x) and math.isfinite(y))

                with tempfile.TemporaryDirectory() as tmp:
                    path = Path(tmp) / "points.csv"
                    write_csv(str(path), result.points)
                    rows = read_csv(str(path))

                self.assertEqual(len(rows), 117)
                ids = [row[0] for row in rows]
                self.assertEqual(ids, list(range(117)))
                self.assertEqual(len(set(ids)), 117)

    def test_csv_schema_header_and_fields(self) -> None:
        result = generate("uniform", n=5, seed=0)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "out.csv"
            write_csv(str(path), result.points)
            lines = path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines[0], "id,x,y")
        self.assertEqual(len(lines), 6)
        for i, line in enumerate(lines[1:], start=0):
            fields = line.split(",")
            self.assertEqual(len(fields), 3)
            self.assertEqual(int(fields[0]), i)
            float(fields[1])
            float(fields[2])


class GeometricPropertyTests(unittest.TestCase):
    def test_corridor_bounding_box_is_elongated(self) -> None:
        result = generate("corridor", n=500, seed=3, corridor_width=2.0, density=2.0)
        min_x, max_x, min_y, max_y = result.bounding_box()
        length = max_x - min_x
        height = max_y - min_y
        self.assertGreater(length, 5.0 * height)
        self.assertLessEqual(height, 2.0 + 1e-6)

    def test_clustered_metadata_reflects_requested_cluster_count(self) -> None:
        result = generate("clustered", n=400, seed=11, clusters=5, spread=0.4)
        self.assertIsNotNone(result.centers)
        assert result.centers is not None
        self.assertEqual(len(result.centers), 5)
        self.assertEqual(result.parameters["clusters"], 5)

    def test_perturbed_grid_points_stay_near_base_positions(self) -> None:
        result = generate("perturbed_grid", n=100, seed=5, spacing=1.0, jitter=0.2)
        self.assertIsNotNone(result.base_positions)
        assert result.base_positions is not None
        absolute_jitter = result.parameters["absolute_jitter"]
        for (x, y), (bx, by) in zip(result.points, result.base_positions):
            self.assertLessEqual(abs(x - bx), absolute_jitter + 1e-12)
            self.assertLessEqual(abs(y - by), absolute_jitter + 1e-12)

    def test_uniform_respects_width_and_height(self) -> None:
        result = generate("uniform", n=300, seed=2, width=10.0, height=3.0)
        min_x, max_x, min_y, max_y = result.bounding_box()
        self.assertGreaterEqual(min_x, 0.0)
        self.assertLessEqual(max_x, 10.0)
        self.assertGreaterEqual(min_y, 0.0)
        self.assertLessEqual(max_y, 3.0)
        self.assertEqual(result.parameters["width"], 10.0)
        self.assertEqual(result.parameters["height"], 3.0)

    def test_cluster_bridge_returns_requested_centers(self) -> None:
        result = generate("cluster_bridge", n=300, seed=8, clusters=4, spread=0.3)
        self.assertIsNotNone(result.centers)
        assert result.centers is not None
        self.assertEqual(len(result.centers), 4)
        # Centres are laid out along x; consecutive gaps should be equal.
        xs = [c[0] for c in result.centers]
        gaps = [xs[i + 1] - xs[i] for i in range(len(xs) - 1)]
        self.assertTrue(all(abs(g - gaps[0]) < 1e-9 for g in gaps))


class CliSmokeTests(unittest.TestCase):
    def test_cli_writes_file(self) -> None:
        import generators as gen_mod

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cli.csv"
            rc = gen_mod.main(
                [
                    "--type",
                    "uniform",
                    "--n",
                    "50",
                    "--seed",
                    "1",
                    "--output",
                    str(path),
                ]
            )
            self.assertEqual(rc, 0)
            rows = read_csv(str(path))
            self.assertEqual(len(rows), 50)


if __name__ == "__main__":
    unittest.main()
