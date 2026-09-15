"""Tests for experiment_runner helpers."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PYTHON_DIR = Path(__file__).resolve().parents[1]
for path in (_REPO_ROOT, _PYTHON_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from experiment_runner import (  # noqa: E402
    DatasetSpec,
    dataset_basename,
    expand_dataset_specs,
    load_completed_run_ids,
    run_id_for,
    summarize,
)


class ExperimentRunnerTests(unittest.TestCase):
    def test_dataset_naming(self) -> None:
        spec = DatasetSpec("uniform", 100, 3, 1.0, {"density": 2.0})
        self.assertEqual(dataset_basename(spec, 3), "uniform_n100_seed3.csv")
        self.assertEqual(dataset_basename(spec, 5), "uniform_n100_seed3_eff5.csv")

    def test_expand_specs_count(self) -> None:
        config = {
            "distributions": ["uniform", "corridor"],
            "sizes": [100, 300],
            "seeds": [1, 2],
            "radius": 1.0,
            "density": 2.0,
            "distribution_parameters": {"corridor": {"corridor_width": 2.0}},
        }
        specs = expand_dataset_specs(config)
        self.assertEqual(len(specs), 8)

    def test_run_id_and_resume_set(self) -> None:
        rid = run_id_for("marathe", Path("datasets/generated/uniform_n100_seed1.csv"))
        self.assertEqual(rid, "marathe__uniform_n100_seed1")
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "experiments.csv"
            csv_path.write_text(
                "run_id,status\nmarathe__a,ok\nmarathe__b,solver_error\n",
                encoding="utf-8",
            )
            done = load_completed_run_ids(csv_path)
            self.assertEqual(done, {"marathe__a"})

    def test_summary_handles_empty_and_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing.csv"
            self.assertIn("No experiments", summarize(missing))
            path = Path(tmp) / "exp.csv"
            path.write_text(
                "distribution,n,status,cds_ratio,algorithm_ms,algorithm_neighbor_queries\n"
                "uniform,100,ok,0.2,1.5,10\n"
                "uniform,100,ok,0.4,2.5,30\n"
                "uniform,100,solver_error,,, \n",
                encoding="utf-8",
            )
            text = summarize(path)
            self.assertIn("uniform,100,3,2,1", text)


if __name__ == "__main__":
    unittest.main()
