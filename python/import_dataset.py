"""CLI: convert external datasets into canonical MCDS PointSet CSV.

Examples:

    py -3 python/import_dataset.py --type csv --input data/raw/points.csv \\
        --x-column x --y-column y --coordinates planar \\
        --output datasets/real/points.csv

    py -3 python/import_dataset.py --type csv --input data/raw/locations.csv \\
        --x-column longitude --y-column latitude --coordinates geographic \\
        --output datasets/real/locations_projected.csv

    py -3 python/import_dataset.py --type geojson --input data/raw/buildings.geojson \\
        --feature-point centroid --coordinates geographic --limit 1000000 \\
        --output datasets/real/buildings_1m.csv
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
    import_csv_file,
    import_geojson_file,
    parse_bbox,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Import external point data into canonical MCDS CSV (id,x,y)."
    )
    parser.add_argument("--type", required=True, choices=("csv", "geojson", "latlon"))
    parser.add_argument("--input", required=True, help="source file path")
    parser.add_argument("--output", required=True, help="canonical CSV output path")
    parser.add_argument(
        "--coordinates",
        choices=("planar", "geographic"),
        default=None,
        help="planar = already Euclidean; geographic = lon/lat needing projection",
    )
    parser.add_argument("--x-column", default="x", help="CSV X / longitude column")
    parser.add_argument("--y-column", default="y", help="CSV Y / latitude column")
    parser.add_argument("--id-column", default=None, help="optional source ID column")
    parser.add_argument(
        "--feature-point",
        default="centroid",
        choices=("centroid",),
        help="representative point for Polygon/MultiPolygon (GeoJSON)",
    )
    parser.add_argument(
        "--bbox",
        default=None,
        help="minLon,minLat,maxLon,maxLat (or minX,minY,maxX,maxY for planar)",
    )
    parser.add_argument("--limit", type=int, default=None, help="max points to keep")
    parser.add_argument(
        "--sample",
        choices=("first", "random"),
        default="first",
        help="'first' may be spatially biased by file order; 'random' is seeded",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--target-crs",
        default=None,
        help="explicit projected CRS (e.g. EPSG:32617); recommended for large regions",
    )
    args = parser.parse_args(argv)

    repo = find_repo_root()
    input_path = Path(args.input)
    if not input_path.is_file():
        input_path = repo / args.input
    if not input_path.is_file():
        print(f"error: input not found: {args.input}", file=sys.stderr)
        return 1

    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = repo / output_path

    bbox = parse_bbox(args.bbox) if args.bbox else None
    source_type = args.type
    coordinates = args.coordinates
    if source_type == "latlon":
        source_type = "csv"
        if coordinates is None:
            coordinates = "geographic"
        if args.x_column == "x":
            args.x_column = "longitude"
        if args.y_column == "y":
            args.y_column = "latitude"
    if coordinates is None:
        coordinates = "geographic" if source_type == "geojson" else "planar"

    try:
        if source_type == "csv":
            result = import_csv_file(
                input_path,
                output_path,
                x_column=args.x_column,
                y_column=args.y_column,
                coordinates=coordinates,
                id_column=args.id_column,
                bbox=bbox,
                limit=args.limit,
                sample=args.sample,
                seed=args.seed,
                target_crs=args.target_crs,
                repo_root=repo,
            )
        else:
            result = import_geojson_file(
                input_path,
                output_path,
                coordinates=coordinates,
                feature_point=args.feature_point,
                bbox=bbox,
                limit=args.limit,
                sample=args.sample,
                seed=args.seed,
                target_crs=args.target_crs,
                repo_root=repo,
            )
    except ImportError_ as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"wrote {result.output_csv}")
    print(f"points {result.point_count}")
    print(f"sha256 {result.dataset_sha256}")
    print(f"meta   {result.meta_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
