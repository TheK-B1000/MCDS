"""Prepare real canonical CSVs: LCC export, nested prefixes, rectangular tiles.

These operations are always explicit and write *new* datasets. The solver never
silently filters disconnected inputs.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_PYTHON_DIR = Path(__file__).resolve().parent
if str(_PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(_PYTHON_DIR))

from gui_support import find_repo_root  # noqa: E402
from real_dataset import (  # noqa: E402
    ImportError_,
    extract_largest_connected_component,
    write_nested_prefix_samples,
    write_rectangular_tiles,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare real-world canonical datasets.")
    parser.add_argument("--input", required=True, help="canonical CSV")
    parser.add_argument("--output", default=None, help="output CSV (LCC mode)")
    parser.add_argument("--output-dir", default=None, help="directory for prefixes/tiles")
    parser.add_argument("--radius", type=float, default=None, help="UDG radius for LCC")
    parser.add_argument(
        "--largest-connected-component",
        action="store_true",
        help="export largest connected component at --radius (explicit only)",
    )
    parser.add_argument(
        "--nested-prefixes",
        default=None,
        help="comma-separated sizes, e.g. 100000,250000,500000,1000000",
    )
    parser.add_argument("--seed", type=int, default=42, help="shuffle seed for nested prefixes")
    parser.add_argument("--basename", default="sample", help="output basename")
    parser.add_argument("--tiles", default=None, help="nx,ny rectangular tile grid, e.g. 2,3")
    args = parser.parse_args(argv)

    repo = find_repo_root()
    input_path = Path(args.input)
    if not input_path.is_file():
        input_path = repo / args.input
    if not input_path.is_file():
        print(f"error: input not found: {args.input}", file=sys.stderr)
        return 1

    modes = sum(
        [
            bool(args.largest_connected_component),
            bool(args.nested_prefixes),
            bool(args.tiles),
        ]
    )
    if modes != 1:
        print(
            "error: choose exactly one of --largest-connected-component, "
            "--nested-prefixes, --tiles",
            file=sys.stderr,
        )
        return 1

    try:
        if args.largest_connected_component:
            if args.radius is None:
                raise ImportError_("--radius is required with --largest-connected-component")
            if not args.output:
                raise ImportError_("--output is required with --largest-connected-component")
            out = Path(args.output)
            if not out.is_absolute():
                out = repo / out
            result = extract_largest_connected_component(
                input_path, out, radius=float(args.radius), repo_root=repo
            )
            print(f"wrote {result.output_csv}  n={result.point_count}  sha={result.dataset_sha256}")
            print(f"meta  {result.meta_path}")
            return 0

        out_dir = Path(args.output_dir or "datasets/real")
        if not out_dir.is_absolute():
            out_dir = repo / out_dir

        if args.nested_prefixes:
            sizes = [int(x.strip()) for x in args.nested_prefixes.split(",") if x.strip()]
            results = write_nested_prefix_samples(
                input_path,
                out_dir,
                sizes,
                seed=args.seed,
                basename=args.basename,
                repo_root=repo,
            )
            for result in results:
                print(f"wrote {result.output_csv}  n={result.point_count}  sha={result.dataset_sha256}")
            return 0

        assert args.tiles is not None
        parts = [p.strip() for p in args.tiles.split(",")]
        if len(parts) != 2:
            raise ImportError_("--tiles must be nx,ny")
        nx, ny = int(parts[0]), int(parts[1])
        results = write_rectangular_tiles(
            input_path,
            out_dir,
            nx=nx,
            ny=ny,
            basename=args.basename,
            repo_root=repo,
        )
        for result in results:
            print(f"wrote {result.output_csv}  n={result.point_count}  sha={result.dataset_sha256}")
        return 0
    except ImportError_ as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
