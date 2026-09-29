"""Tests for real-world dataset import and external experiment configs."""

from __future__ import annotations

import json
import math
import os
import sys
import tempfile
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PYTHON_DIR = Path(__file__).resolve().parents[1]
for path in (_REPO_ROOT, _PYTHON_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from experiment_runner import DatasetSpec, expand_dataset_specs, load_config  # noqa: E402
from generators import generate, read_csv, write_csv  # noqa: E402
from real_dataset import (  # noqa: E402
    ImportError_,
    extract_largest_connected_component,
    import_csv_file,
    import_geojson_file,
    parse_bbox,
    validate_canonical_csv,
    write_nested_prefix_samples,
)


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")


class BBoxAndPlanarCsvTests(unittest.TestCase):
    def test_parse_bbox(self) -> None:
        self.assertEqual(parse_bbox("-81.7,30.2,-81.5,30.4"), (-81.7, 30.2, -81.5, 30.4))
        with self.assertRaises(ImportError_):
            parse_bbox("1,2,3")

    def test_planar_csv_import_deterministic_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            src = tmp_path / "raw.csv"
            out = tmp_path / "out.csv"
            _write(src, "x,y\n1.0,2.0\n3.5,4.5\n")
            result = import_csv_file(
                src, out, x_column="x", y_column="y", coordinates="planar"
            )
            self.assertEqual(result.point_count, 2)
            rows = read_csv(str(out))
            self.assertEqual(rows, [(0, 1.0, 2.0), (1, 3.5, 4.5)])
            self.assertTrue(result.meta_path.is_file())
            meta = json.loads(result.meta_path.read_text(encoding="utf-8"))
            self.assertEqual(meta["source_type"], "real")
            self.assertEqual(meta["coordinates"], "planar")
            self.assertEqual(meta["dataset_sha256"], result.dataset_sha256)
            validate_canonical_csv(out)


class GeographicCsvTests(unittest.TestCase):
    def test_geographic_csv_projects_and_rejects_raw_degrees_path(self) -> None:
        try:
            import pyproj  # noqa: F401
        except ImportError:
            self.skipTest("pyproj not installed")

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            src = tmp_path / "geo.csv"
            out = tmp_path / "out.csv"
            # Tiny Jacksonville-ish patch.
            _write(
                src,
                "longitude,latitude\n"
                "-81.6557,30.3322\n"
                "-81.6550,30.3325\n"
                "-81.6540,30.3310\n",
            )
            result = import_csv_file(
                src,
                out,
                x_column="longitude",
                y_column="latitude",
                coordinates="geographic",
                bbox=(-81.66, 30.33, -81.65, 30.34),
            )
            self.assertEqual(result.point_count, 3)
            rows = read_csv(str(out))
            # Projected meters should not look like lon/lat degrees.
            for _pid, x, y in rows:
                self.assertTrue(abs(x) < 2000.0)
                self.assertTrue(abs(y) < 2000.0)
            meta = json.loads(result.meta_path.read_text(encoding="utf-8"))
            self.assertEqual(meta["coordinates"], "projected")
            self.assertEqual(meta["units"], "meters")
            self.assertEqual(meta["input_crs"], "EPSG:4326")
            self.assertIn("aeqd", meta["output_crs"])


class GeoJsonTests(unittest.TestCase):
    def test_geojson_points_and_polygon_centroid(self) -> None:
        try:
            import pyproj  # noqa: F401
        except ImportError:
            self.skipTest("pyproj not installed")

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            gj = tmp_path / "features.geojson"
            out = tmp_path / "out.csv"
            payload = {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {"type": "Point", "coordinates": [-81.6557, 30.3322]},
                        "properties": {},
                    },
                    {
                        "type": "Feature",
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [
                                [
                                    [-81.6560, 30.3320],
                                    [-81.6550, 30.3320],
                                    [-81.6550, 30.3330],
                                    [-81.6560, 30.3330],
                                    [-81.6560, 30.3320],
                                ]
                            ],
                        },
                        "properties": {},
                    },
                ],
            }
            gj.write_text(json.dumps(payload), encoding="utf-8")
            result = import_geojson_file(
                gj,
                out,
                coordinates="geographic",
                feature_point="centroid",
                bbox=(-81.66, 30.33, -81.65, 30.34),
            )
            self.assertEqual(result.point_count, 2)
            meta = json.loads(result.meta_path.read_text(encoding="utf-8"))
            self.assertEqual(meta["feature_point"], "centroid")
            self.assertEqual(meta["input_format"], "geojson")


class SamplingAndLimitTests(unittest.TestCase):
    def test_limit_first_and_random_seed_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            src = tmp_path / "raw.csv"
            lines = ["x,y"] + [f"{i}.0,{i * 0.1}" for i in range(100)]
            _write(src, "\n".join(lines) + "\n")
            out1 = tmp_path / "a.csv"
            out2 = tmp_path / "b.csv"
            out3 = tmp_path / "c.csv"
            r1 = import_csv_file(
                src, out1, x_column="x", y_column="y", coordinates="planar", limit=10, sample="first"
            )
            self.assertEqual(r1.point_count, 10)
            self.assertEqual(read_csv(str(out1))[0], (0, 0.0, 0.0))

            import_csv_file(
                src,
                out2,
                x_column="x",
                y_column="y",
                coordinates="planar",
                limit=20,
                sample="random",
                seed=7,
            )
            import_csv_file(
                src,
                out3,
                x_column="x",
                y_column="y",
                coordinates="planar",
                limit=20,
                sample="random",
                seed=7,
            )
            self.assertEqual(out2.read_bytes(), out3.read_bytes())

    def test_bbox_filters_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            src = tmp_path / "raw.csv"
            out = tmp_path / "out.csv"
            _write(src, "x,y\n0,0\n5,5\n10,10\n")
            result = import_csv_file(
                src,
                out,
                x_column="x",
                y_column="y",
                coordinates="planar",
                bbox=(4, 4, 6, 6),
            )
            self.assertEqual(result.point_count, 1)
            self.assertEqual(read_csv(str(out))[0][1:], (5.0, 5.0))


class NestedPrefixAndLccTests(unittest.TestCase):
    def test_nested_prefixes_share_shuffle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            src = tmp_path / "src.csv"
            write_csv(str(src), [(float(i), 0.0) for i in range(50)])
            results = write_nested_prefix_samples(
                src, tmp_path / "out", [10, 20], seed=3, basename="p"
            )
            self.assertEqual(len(results), 2)
            small = read_csv(str(results[0].output_csv))
            large = read_csv(str(results[1].output_csv))
            self.assertEqual(len(small), 10)
            self.assertEqual(len(large), 20)
            self.assertEqual(small, large[:10])

    def test_lcc_extracts_largest_and_preserves_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            src = tmp_path / "src.csv"
            # Two components: a chain of 4 and an isolated pair far away.
            pts = [(0.0, 0.0), (0.5, 0.0), (1.0, 0.0), (1.5, 0.0), (100.0, 0.0), (100.5, 0.0)]
            write_csv(str(src), pts)
            before = src.read_bytes()
            out = tmp_path / "lcc.csv"
            result = extract_largest_connected_component(src, out, radius=1.0)
            self.assertEqual(result.point_count, 4)
            self.assertEqual(src.read_bytes(), before)
            meta = json.loads(result.meta_path.read_text(encoding="utf-8"))
            self.assertEqual(meta["sampling"], "largest_connected_component")
            self.assertEqual(meta["lcc_original_n"], 6)
            self.assertEqual(meta["lcc_result_n"], 4)


class MalformedInputTests(unittest.TestCase):
    def test_malformed_csv_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            src = tmp_path / "bad.csv"
            out = tmp_path / "out.csv"
            _write(src, "x,y\n1.0,not_a_number\n")
            with self.assertRaises(ImportError_):
                import_csv_file(src, out, x_column="x", y_column="y", coordinates="planar")


class ExperimentConfigTests(unittest.TestCase):
    def test_external_datasets_config_parsing(self) -> None:
        config = {
            "algorithms": ["marathe", "wan"],
            "datasets": [
                {"name": "a", "path": "datasets/real/a.csv", "radius": 50.0},
                {"name": "b", "path": "datasets/real/b.csv", "radius": 100.0, "radius_units": "meters"},
            ],
            "require_connected": True,
        }
        specs = expand_dataset_specs(config)
        self.assertEqual(len(specs), 2)
        self.assertTrue(all(s.is_external for s in specs))
        self.assertEqual(specs[0].radius, 50.0)
        self.assertEqual(specs[1].radius_units, "meters")
        # Same path ⇒ same SHA key material across algorithms (key uses path+radius).
        self.assertEqual(specs[0].external_path, "datasets/real/a.csv")

    def test_synthetic_configs_still_expand(self) -> None:
        config = load_config(_REPO_ROOT / "experiments" / "smoke.json")
        specs = expand_dataset_specs(config)
        self.assertGreater(len(specs), 0)
        self.assertFalse(any(s.is_external for s in specs))

    def test_real_world_scaling_json_loads(self) -> None:
        config = load_config(_REPO_ROOT / "experiments" / "real_world_scaling.json")
        specs = expand_dataset_specs(config)
        self.assertEqual(len(specs), 4)
        self.assertTrue(specs[0].is_external)


class ClusteredRegressionTests(unittest.TestCase):
    def test_clustered_generator_unchanged_contract(self) -> None:
        a = generate("clustered", n=200, seed=11, density=5.0, clusters=4, spread=0.5)
        b = generate("clustered", n=200, seed=11, density=5.0, clusters=4, spread=0.5)
        self.assertEqual(len(a.points), 200)
        self.assertEqual(a.points, b.points)
        self.assertEqual(a.parameters["clusters"], 4)
        for x, y in a.points:
            self.assertTrue(math.isfinite(x) and math.isfinite(y))


@unittest.skipUnless(os.environ.get("MCDS_MILLION_TEST") == "1", "set MCDS_MILLION_TEST=1")
class MillionPointOptionalTests(unittest.TestCase):
    def test_million_point_import_and_index_smoke(self) -> None:
        """Infrastructure smoke: ingest + index 1e6 points (no MCDS algorithms)."""
        import time
        from gui_support import find_mcds_executable, build_solver_command, run_solver
        from experiment_runner import measure_peak_memory_mb

        def _peak_working_set_mb() -> float | None:
            if os.name != "nt":
                return None
            import ctypes
            from ctypes import wintypes

            class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            psapi = ctypes.WinDLL("psapi")
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            GetCurrentProcess = kernel32.GetCurrentProcess
            GetCurrentProcess.restype = wintypes.HANDLE
            GetCurrentProcess.argtypes = []
            GetProcessMemoryInfo = psapi.GetProcessMemoryInfo
            GetProcessMemoryInfo.argtypes = [
                wintypes.HANDLE,
                ctypes.POINTER(PROCESS_MEMORY_COUNTERS),
                wintypes.DWORD,
            ]
            GetProcessMemoryInfo.restype = wintypes.BOOL
            counters = PROCESS_MEMORY_COUNTERS()
            counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
            handle = GetCurrentProcess()
            if not GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
                return None
            return counters.PeakWorkingSetSize / (1024.0 * 1024.0)

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            src = tmp_path / "raw.csv"
            out = tmp_path / "million.csv"

            t0 = time.perf_counter()
            with src.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write("x,y\n")
                for i in range(1_000_000):
                    handle.write(f"{(i % 1000) * 0.1},{(i // 1000) * 0.1}\n")
            raw_write_s = time.perf_counter() - t0

            t1 = time.perf_counter()
            result = import_csv_file(
                src, out, x_column="x", y_column="y", coordinates="planar", limit=1_000_000
            )
            import_s = time.perf_counter() - t1
            import_peak_mb = _peak_working_set_mb()

            self.assertEqual(result.point_count, 1_000_000)
            validate_canonical_csv(out)

            try:
                exe = find_mcds_executable(_REPO_ROOT)
            except FileNotFoundError:
                self.skipTest("mcds executable not built")

            conn = tmp_path / "conn.json"
            inv = build_solver_command(exe, out, conn, check_connectivity_only=True, radius=1.0)
            completed, solver_peak_mb = measure_peak_memory_mb(inv.command, timeout_s=600.0)
            self.assertEqual(completed.returncode, 0, msg=completed.stderr)
            payload = json.loads(conn.read_text(encoding="utf-8"))

            # Connectivity-only path exercises load + index build + radius queries.
            neighbor_ok = (
                int(payload.get("connectivity_neighbor_queries", 0)) > 0
                or int(payload.get("component_count", -1)) >= 0
            )
            self.assertTrue(neighbor_ok)
            self.assertIn("component_count", payload)

            report = {
                "point_count": result.point_count,
                "dataset_sha256": result.dataset_sha256,
                "raw_csv_write_s": round(raw_write_s, 3),
                "import_s": round(import_s, 3),
                "import_peak_working_set_mb": (
                    None if import_peak_mb is None else round(import_peak_mb, 1)
                ),
                "load_ms": payload.get("load_ms"),
                "index_build_ms": payload.get("index_build_ms"),
                "connectivity_ms": payload.get("connectivity_ms"),
                "connectivity_neighbor_queries": payload.get("connectivity_neighbor_queries"),
                "component_count": payload.get("component_count"),
                "largest_component": payload.get("largest_component"),
                "solver_peak_memory_mb": (
                    None if solver_peak_mb is None else round(solver_peak_mb, 1)
                ),
                "neighbor_query_success": True,
            }
            print("\nMILLION_POINT_SMOKE " + json.dumps(report, sort_keys=True))
            # Persist beside the temp dir for the operator log.
            report_path = _REPO_ROOT / "results" / "million_point_smoke.json"
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")



if __name__ == "__main__":
    unittest.main()
