"""Tests for GUI orchestration helpers (no Tkinter widget exercise)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PYTHON_DIR = Path(__file__).resolve().parents[1]
for path in (_REPO_ROOT, _PYTHON_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from gui_support import (  # noqa: E402
    DISTRIBUTION_FIELDS,
    SolverOutcome,
    build_solver_command,
    dataset_paths,
    friendly_solver_error,
    map_generation_kwargs,
    run_solver,
    write_dataset_with_metadata,
)


class GuiSupportTests(unittest.TestCase):
    def test_command_construction(self) -> None:
        inv = build_solver_command(
            Path("build/mcds.exe"),
            Path("datasets/a.csv"),
            Path("results/a.json"),
            algorithm="marathe",
            radius=1.0,
        )
        self.assertEqual(Path(inv.command[0]), Path("build/mcds.exe"))
        self.assertIn("--algorithm", inv.command)
        self.assertIn("marathe", inv.command)
        self.assertIn("--input", inv.command)
        self.assertIn("--output", inv.command)

        inv2 = build_solver_command(
            Path("build/mcds"),
            Path("in.csv"),
            Path("out.json"),
            check_connectivity_only=True,
        )
        self.assertIn("--check-connectivity", inv2.command)
        self.assertNotIn("--algorithm", inv2.command)

    def test_distribution_parameter_mapping(self) -> None:
        kwargs = map_generation_kwargs("clustered", 100, 1, clusters=5, spread=0.4, width=10.0)
        self.assertEqual(kwargs["type"], "clustered")
        self.assertEqual(kwargs["clusters"], 5)
        self.assertEqual(kwargs["spread"], 0.4)
        self.assertEqual(kwargs["width"], 10.0)
        self.assertIn("clusters", DISTRIBUTION_FIELDS["clustered"])
        self.assertIn("corridor_width", DISTRIBUTION_FIELDS["corridor"])

    def test_temporary_dataset_paths_and_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            csv_path, meta_path, result_path = dataset_paths(work, "trial")
            self.assertEqual(csv_path.name, "trial_points.csv")
            self.assertEqual(result_path.name, "trial_result.json")
            meta = write_dataset_with_metadata(
                csv_path, meta_path, distribution="uniform", n=20, seed=3, density=2.0
            )
            self.assertTrue(csv_path.is_file())
            self.assertTrue(meta_path.is_file())
            loaded = json.loads(meta_path.read_text(encoding="utf-8"))
            self.assertEqual(loaded["distribution"], "uniform")
            self.assertEqual(loaded["n"], 20)
            self.assertEqual(meta["seed"], 3)

    def test_result_json_loading_via_run_solver_mock(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out.json"
            payload = {"algorithm": "marathe", "n": 10, "valid_dominating": True, "selected_ids": [0]}
            out.write_text(json.dumps(payload), encoding="utf-8")
            inv = build_solver_command(Path("fake"), Path("in.csv"), out)

            fake = mock.Mock()
            fake.returncode = 0
            fake.stdout = "ok\n"
            fake.stderr = ""
            with mock.patch("gui_support.subprocess.run", return_value=fake):
                outcome = run_solver(inv)
            self.assertEqual(outcome.exit_code, 0)
            self.assertEqual(outcome.result["n"], 10)

    def test_solver_error_handling_messages(self) -> None:
        outcome = SolverOutcome(
            exit_code=1,
            stdout="",
            stderr="error: input UDG is disconnected (3 components); refusing to run marathe\n",
            duration_s=0.1,
            error=None,
        )
        msg = friendly_solver_error(outcome)
        self.assertIn("disconnected", msg.lower())

        missing = SolverOutcome(127, "", "", 0.0, error="executable not found: mcds")
        self.assertIn("not found", friendly_solver_error(missing).lower())


if __name__ == "__main__":
    unittest.main()
