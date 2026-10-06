"""The project's experiment runner (single entry point).

    py -3 python/run_study.py reproduce --config experiments/smoke.json
    py -3 python/run_study.py run       --config ...   # datasets + executions + raw CSVs + fairness
    py -3 python/run_study.py analyze   --config ...   # summary / paired / validity CSVs
    py -3 python/run_study.py figures   --config ...
    py -3 python/run_study.py rebuild   --config ...   # re-derive CSVs from stored artifacts
    py -3 python/run_study.py manifest  --config ...
    py -3 python/run_study.py plan      --config ...   # print the design, run nothing

`reproduce` = run + analyze + figures + manifest, and exits non-zero if the
fairness check fails. Re-running the same command resumes an interrupted study.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from study import analysis, config as config_mod, datasets, figures, manifest  # noqa: E402
from study.runner import Study, StudyError  # noqa: E402
from study.schedule import execution_order, schedule_index  # noqa: E402

REPO_ROOT = _HERE.parent


def _study(args) -> Study:
    show = not getattr(args, "no_progress", False)
    return Study(Path(args.config), REPO_ROOT, allow_dirty=args.allow_dirty,
                 allow_environment_change=args.allow_environment_change,
                 show_progress=show)


def cmd_plan(args) -> int:
    cfg = config_mod.load(Path(args.config))
    planned = datasets.plan(cfg)
    t = cfg["timing"]
    print(f"study_id      {cfg['study_id']}  (config sha256 {config_mod.config_sha256(cfg)[:12]})")
    print(f"algorithms    {cfg['algorithms']}")
    print(f"datasets      {len(planned)} planned graphs in {len({p.cell_id for p in planned})} cells")
    print(f"connectivity  {cfg['connectivity_rule']}")
    print(f"timing        reps={t['repetitions']} warmups={t['warmups']} instrumentation={t['instrumentation']} "
          f"mode={t['process_mode']}")
    execs = len(planned) * len(cfg["algorithms"]) * (t["repetitions"] + t["warmups"])
    print(f"executions    {execs} timed+warmup algorithm executions (+ memory probes / counter pass)")
    for p in planned[: min(8, len(planned))]:
        order, row = execution_order(cfg["algorithms"], cfg["study_seed"], schedule_index(cfg["study_seed"], p.__dict__))
        print(f"  [{p.plan_index}] {p.dataset_id}  order={'>'.join(order)} (row {row})")
    if len(planned) > 8:
        print(f"  ... {len(planned) - 8} more")
    return 0


def cmd_run(args) -> int:
    study = _study(args)
    result = study.run(datasets_only=args.datasets_only, skip_preflight=args.skip_preflight)
    print(json.dumps({"out": result["out"], "rows": result["rows"], "fairness_passed": result["fairness"]["passed"]},
                     indent=2))
    return 0 if result["fairness"]["passed"] else 3


def cmd_rebuild(args) -> int:
    study = _study(args)
    result = study.rebuild()
    print(json.dumps({"rows": result["rows"], "fairness_passed": result["fairness"]["passed"]}, indent=2))
    return 0 if result["fairness"]["passed"] else 3


def _out_dir(args) -> tuple[Path, dict]:
    cfg = config_mod.load(Path(args.config))
    out = Path(cfg["output_dir"])
    return (out if out.is_absolute() else REPO_ROOT / out), cfg


def cmd_analyze(args) -> int:
    out, cfg = _out_dir(args)
    print(json.dumps(analysis.analyze(out, cfg["algorithms"]), indent=2))
    return 0


def cmd_figures(args) -> int:
    out, _ = _out_dir(args)
    written = figures.make_all(out)
    print(f"{len(written)} figure(s) written to {out / 'figures'}")
    return 0


def cmd_manifest(args) -> int:
    out, _ = _out_dir(args)
    print(manifest.write(out))
    return 0


def cmd_reproduce(args) -> int:
    code = cmd_run(args)
    if code != 0:
        print("fairness check FAILED; see fairness_report.json. Analysis not produced.", file=sys.stderr)
        return code
    cmd_analyze(args)
    cmd_figures(args)
    cmd_manifest(args)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    handlers = {"plan": cmd_plan, "run": cmd_run, "rebuild": cmd_rebuild, "analyze": cmd_analyze,
                "figures": cmd_figures, "manifest": cmd_manifest, "reproduce": cmd_reproduce}
    for name in handlers:
        p = sub.add_parser(name)
        p.add_argument("--config", required=True)
        p.add_argument("--allow-dirty", action="store_true", help="permit a final study on a dirty git tree")
        p.add_argument("--allow-environment-change", action="store_true",
                       help="permit resuming after the machine/solver/commit changed (recorded per row)")
        if name in ("run", "reproduce"):
            p.add_argument("--datasets-only", action="store_true")
            p.add_argument("--skip-preflight", action="store_true",
                           help="skip the small all-algorithms validity check before a campaign")
            p.add_argument("--no-progress", action="store_true",
                           help="disable tqdm progress bars on dataset and execution loops")
        else:
            p.set_defaults(datasets_only=False, skip_preflight=False, no_progress=False)
    args = parser.parse_args(argv)
    try:
        return handlers[args.command](args)
    except (StudyError, config_mod.ConfigError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
