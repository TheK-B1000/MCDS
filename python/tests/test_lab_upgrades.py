"""Tests for experiment laboratory upgrades."""

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

from experiment_runner import (  # noqa: E402
    DatasetSpec,
    expand_dataset_specs,
    load_completed_run_ids,
    paired_comparison,
    study_preview,
)
from lab_utils import (  # noqa: E402
    atomic_write_json,
    canonicalize_config,
    config_sha256,
    sha256_bytes,
    sha256_file,
)
from study_report import write_batch_summary, write_failures_csv  # noqa: E402


class LabUtilsTests(unittest.TestCase):
    def test_config_hash_stable(self) -> None:
        a = {"sizes": [1, 2], "algorithms": ["marathe", "wan"]}
        b = {"algorithms": ["marathe", "wan"], "sizes": [1, 2]}
        self.assertEqual(canonicalize_config(a), canonicalize_config(b))
        self.assertEqual(config_sha256(a), config_sha256(b))

    def test_sha256_file_and_atomic_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            f = root / "x.bin"
            f.write_bytes(b"abc")
            self.assertEqual(sha256_file(f), sha256_bytes(b"abc"))
            out = root / "state.json"
            atomic_write_json(out, {"ok": True})
            self.assertTrue(out.is_file())
            self.assertEqual(json.loads(out.read_text(encoding="utf-8"))["ok"], True)


class DensityExpandTests(unittest.TestCase):
    def test_densities_cartesian(self) -> None:
        config = {
            "distributions": ["uniform"],
            "sizes": [100],
            "seeds": [1, 2],
            "densities": [3.0, 5.0],
            "radius": 1.0,
        }
        specs = expand_dataset_specs(config)
        self.assertEqual(len(specs), 4)
        dens = sorted({s.density for s in specs})
        self.assertEqual(dens, [3.0, 5.0])

    def test_preview_mentions_counts(self) -> None:
        config = {
            "distributions": ["uniform", "corridor"],
            "sizes": [100, 200],
            "seeds": [1],
            "density": 5.0,
        }
        specs = expand_dataset_specs(config)
        text = study_preview(config, specs, ["marathe", "wan"])
        self.assertIn("STUDY PREVIEW", text)
        self.assertIn("Unique datasets:         4", text)
        self.assertIn("Logical algorithm runs:  8", text)
        self.assertIn("Total solver launches:   8", text)


class PairedShaTests(unittest.TestCase):
    def test_pair_by_dataset_sha(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "exp.csv"
            path.write_text(
                "algorithm,status,cds_size,algorithm_ms,algorithm_neighbor_queries,"
                "dataset_sha256,dataset_csv\n"
                "marathe,ok,10,1.0,100,abc,a.csv\n"
                "wan,ok,8,2.0,200,abc,a.csv\n"
                "marathe,ok,12,1.0,100,def,b.csv\n"
                "wan,ok,12,2.0,200,def,b.csv\n",
                encoding="utf-8",
            )
            text = paired_comparison(path, left="marathe", right="wan")
            self.assertIn("paired_datasets,2", text)
            self.assertIn("wan_cds_smaller,1", text)
            self.assertIn("same_cds_size,1", text)


class StudyReportTests(unittest.TestCase):
    def test_failures_and_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            exp = root / "experiments.csv"
            exp.write_text(
                "run_id,algorithm,distribution,density,n,base_seed,dataset_sha256,"
                "status,exit_code,error,algorithm_ms,peak_memory_mb,"
                "cds_ratio,valid_dominating,valid_connected,algorithm_neighbor_queries\n"
                "a,marathe,uniform,5,100,1,abc,ok,0,,1.0,4.0,0.2,True,True,10\n"
                "b,wan,uniform,5,100,1,abc,timeout,124,timed out,2.0,5.0,,,,\n",
                encoding="utf-8",
            )
            fails = root / "failures.csv"
            n = write_failures_csv(exp, fails)
            self.assertEqual(n, 1)
            self.assertIn("timeout", fails.read_text(encoding="utf-8"))
            write_batch_summary(exp, root / "missing.json", root / "missing2.json", root / "summary.md")
            self.assertTrue((root / "summary.md").is_file())
            self.assertIn("# Study Summary", (root / "summary.md").read_text(encoding="utf-8"))


class ResumeCountTests(unittest.TestCase):
    def test_completed_only_ok(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "e.csv"
            path.write_text(
                "run_id,status\nok1,ok\nbad,timeout\nok2,ok\n",
                encoding="utf-8",
            )
            self.assertEqual(load_completed_run_ids(path), {"ok1", "ok2"})


class BatchStateAccountingTests(unittest.TestCase):
    def test_successful_runs_are_cumulative(self) -> None:
        from experiment_runner import write_batch_state

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "batch_state.json"
            write_batch_state(
                path,
                config_path=Path("cfg.json"),
                stats={"runs_ok": 2, "runs_failed": 1, "runs_skipped": 5, "datasets_failed": 0},
                completed_run_ids={"a", "b", "c", "d", "e", "f", "g"},
                interrupted=False,
                planned_runs=10,
            )
            state = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(state["successful_runs"], 7)
            self.assertEqual(state["successful_this_invocation"], 2)
            self.assertEqual(state["failed_this_invocation"], 1)
            self.assertEqual(state["skipped_existing"], 5)
            self.assertEqual(state["completed_runs"], 7)


class DryRunLaunchCountTests(unittest.TestCase):
    def test_preview_counts_warmup_and_reps(self) -> None:
        config = {
            "distributions": ["uniform"],
            "sizes": [100],
            "seeds": [1],
            "density": 5.0,
            "timing_repetitions": 3,
            "warmup_runs": 1,
        }
        specs = expand_dataset_specs(config)
        text = study_preview(config, specs, ["marathe", "wan"])
        self.assertIn("Logical algorithm runs:  2", text)
        self.assertIn("Measured repetitions:    3 per run", text)
        self.assertIn("Warmups:                 1 per run", text)
        self.assertIn("Total solver launches:   8", text)


if __name__ == "__main__":
    unittest.main()
