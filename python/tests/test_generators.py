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

    def test_clustered_background_zero_is_the_previous_blob_construction(self) -> None:
        import random
        res = generate("clustered", n=300, seed=21, density=5.0, clusters=4, spread=0.8, background_fraction=0.0)
        rng = random.Random(21)
        w = h = (300 / 5.0) ** 0.5
        centers = [(rng.uniform(0.0, w), rng.uniform(0.0, h)) for _ in range(4)]
        expected = [(centers[i % 4][0] + rng.gauss(0.0, 0.8), centers[i % 4][1] + rng.gauss(0.0, 0.8))
                    for i in range(300)]
        self.assertEqual(res.points, expected)

    def test_clustered_hotspots_on_uniform_background(self) -> None:
        import random
        res = generate("clustered", n=1000, seed=3, density=8.0, clusters=4, spread=0.8, background_fraction=0.5)
        self.assertEqual(res.parameters["background_fraction"], 0.5)
        self.assertEqual(len(res.points), 1000)
        w, h = res.parameters["width"], res.parameters["height"]
        # Reproduce the defined draw order: centres, 500 background, 500 hotspot points.
        rng = random.Random(3)
        centers = [(rng.uniform(0.0, w), rng.uniform(0.0, h)) for _ in range(4)]
        background = [(rng.uniform(0.0, w), rng.uniform(0.0, h)) for _ in range(500)]
        self.assertEqual(res.centers, centers)
        self.assertEqual(res.points[:500], background)
        self.assertTrue(all(0.0 <= x <= w and 0.0 <= y <= h for x, y in res.points[:500]))
        self.assertEqual(generate("clustered", n=1000, seed=3, density=8.0, clusters=4, spread=0.8).points,
                         res.points)  # 0.5 is the default; deterministic

    def test_clustered_rejects_bad_background_fraction(self) -> None:
        for bad in (-0.1, 1.0, 1.5):
            with self.assertRaises(ValueError):
                generate("clustered", n=50, seed=1, background_fraction=bad)

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


class FrozenV2GeneratorTests(unittest.TestCase):
    """Generators frozen by experiments/calibration/generator_freeze_v2.json."""

    def test_d3_v2_points_stay_in_window_and_sigma_scales_with_side(self) -> None:
        for n, density in ((500, 8.0), (5000, 12.0)):
            g = generate("clustered", n, 3, density=density, clusters=4, background_fraction=0.5,
                         spread_relative=0.05)
            side = math.sqrt(n / density)
            self.assertAlmostEqual(g.parameters["width"], side, places=9)
            self.assertTrue(all(0.0 <= x <= side and 0.0 <= y <= side for x, y in g.points))
            self.assertEqual(g.parameters["spread_relative"], 0.05)

    def test_d3_v2_rejects_nonpositive_spread_relative(self) -> None:
        with self.assertRaises(ValueError):
            generate("clustered", 100, 1, density=8.0, spread_relative=0.0)

    def test_dumbbell_domain_area_and_neck(self) -> None:
        for n, density in ((500, 8.0), (10000, 12.0)):
            g = generate("dumbbell", n, 5, density=density, neck_width=1.0, neck_length=3.0)
            a = g.parameters["square_side"]
            self.assertAlmostEqual(2 * a * a + 3.0, n / density, places=9)  # total area n / density
            self.assertEqual(len(g.points), n)
            self.assertEqual(g.parameters["neck_points"], round(n * 3.0 / (n / density)))
            self.assertLess(g.parameters["neck_share"], 0.10)
            y0 = a / 2 - 0.5
            in_neck = [p for p in g.points if a < p[0] < a + 3.0]
            self.assertEqual(len(in_neck), g.parameters["neck_points"])
            self.assertTrue(all(y0 <= y <= y0 + 1.0 for _x, y in in_neck))
            self.assertTrue(all(0 <= x <= 2 * a + 3.0 and 0 <= y <= a for x, y in g.points))

    def test_dumbbell_rejects_domain_smaller_than_neck(self) -> None:
        with self.assertRaises(ValueError):
            generate("dumbbell", 10, 1, density=8.0, neck_width=1.0, neck_length=3.0)


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
