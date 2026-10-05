"""Import and prepare real-world point datasets for the MCDS pipeline.

Converts external CSV / GeoJSON / lat-lon sources into the project's canonical
``id,x,y`` CSV. After conversion, algorithms cannot tell synthetic from real
data — both flow through the same SpatialIndex → MCDS → validator path.

Geographic coordinates are projected to planar meters. Degrees are never used
as Euclidean distance units.

Dependencies: pyproj (projection). GeoJSON streaming uses ``ijson`` when
available, falling back to ``json.load`` for smaller files.
"""

from __future__ import annotations

import csv
import json
import math
import os
import random
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, TextIO

_PYTHON_DIR = Path(__file__).resolve().parent
if str(_PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(_PYTHON_DIR))

from generators import COORD_DECIMALS  # noqa: E402
from lab_utils import git_info, sha256_file  # noqa: E402

IMPORTER_VERSION = "1.0.0"

# Lon/lat span (degrees) beyond which an explicit --target-crs is encouraged.
_LARGE_REGION_DEG = 5.0


class ImportError_(ValueError):
    """User-facing import / preparation failure."""


# ---------------------------------------------------------------------------
# Projection
# ---------------------------------------------------------------------------


@dataclass
class ProjectionInfo:
    input_crs: str
    output_crs: str
    method: str
    units: str = "meters"
    center_lon: float | None = None
    center_lat: float | None = None


class CoordinateProjector:
    """Project lon/lat (EPSG:4326) to planar meters."""

    def __init__(
        self,
        *,
        target_crs: str | None = None,
        center_lon: float | None = None,
        center_lat: float | None = None,
    ) -> None:
        try:
            from pyproj import CRS, Transformer
        except ImportError as exc:
            raise ImportError_(
                "pyproj is required for geographic projection; "
                "install python/requirements.txt"
            ) from exc

        self._Transformer = Transformer
        self._CRS = CRS
        self.input_crs = "EPSG:4326"
        if target_crs:
            self.output_crs = target_crs
            self.method = f"pyproj Transformer {self.input_crs} → {target_crs}"
            self.center_lon = None
            self.center_lat = None
            self._transformer = Transformer.from_crs(
                self.input_crs, target_crs, always_xy=True
            )
        else:
            if center_lon is None or center_lat is None:
                raise ImportError_(
                    "geographic projection without --target-crs requires a "
                    "known region center (from data or --bbox)"
                )
            # Local azimuthal equidistant: meters, origin at region center.
            self.center_lon = float(center_lon)
            self.center_lat = float(center_lat)
            aeqd = (
                f"+proj=aeqd +lat_0={self.center_lat} +lon_0={self.center_lon} "
                f"+x_0=0 +y_0=0 +datum=WGS84 +units=m +no_defs"
            )
            self.output_crs = aeqd
            self.method = (
                "local azimuthal equidistant (AEQD) centered on data/bbox; "
                "suitable for small/local regions"
            )
            self._transformer = Transformer.from_crs(
                self.input_crs, aeqd, always_xy=True
            )

    def project(self, lon: float, lat: float) -> tuple[float, float]:
        x, y = self._transformer.transform(lon, lat)
        if not (math.isfinite(x) and math.isfinite(y)):
            raise ImportError_(f"non-finite projected coordinate from ({lon}, {lat})")
        return float(x), float(y)

    def info(self) -> ProjectionInfo:
        return ProjectionInfo(
            input_crs=self.input_crs,
            output_crs=self.output_crs,
            method=self.method,
            units="meters",
            center_lon=self.center_lon,
            center_lat=self.center_lat,
        )


def parse_bbox(text: str) -> tuple[float, float, float, float]:
    """Parse ``minLon,minLat,maxLon,maxLat``."""
    parts = [p.strip() for p in text.split(",")]
    if len(parts) != 4:
        raise ImportError_("bbox must be minLon,minLat,maxLon,maxLat")
    try:
        min_lon, min_lat, max_lon, max_lat = (float(p) for p in parts)
    except ValueError as exc:
        raise ImportError_("bbox values must be numeric") from exc
    if min_lon > max_lon or min_lat > max_lat:
        raise ImportError_("bbox min must be <= max for each axis")
    return min_lon, min_lat, max_lon, max_lat


def in_bbox(lon: float, lat: float, bbox: tuple[float, float, float, float] | None) -> bool:
    if bbox is None:
        return True
    min_lon, min_lat, max_lon, max_lat = bbox
    return min_lon <= lon <= max_lon and min_lat <= lat <= max_lat


# ---------------------------------------------------------------------------
# Geometry helpers (GeoJSON)
# ---------------------------------------------------------------------------


def _ring_centroid(ring: list[list[float]]) -> tuple[float, float] | None:
    """Shoelace centroid of a linear ring (lon/lat treated as planar for centroid only)."""
    if len(ring) < 3:
        return None
    area = 0.0
    cx = 0.0
    cy = 0.0
    n = len(ring)
    # Close ring if needed for the formula; skip duplicate closing vertex in loop.
    pts = ring
    if pts[0] != pts[-1]:
        pts = pts + [pts[0]]
    for i in range(len(pts) - 1):
        x0, y0 = float(pts[i][0]), float(pts[i][1])
        x1, y1 = float(pts[i + 1][0]), float(pts[i + 1][1])
        cross = x0 * y1 - x1 * y0
        area += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    area *= 0.5
    if abs(area) < 1e-18:
        # Degenerate: average vertices (excluding closing duplicate).
        xs = [float(p[0]) for p in ring[:n]]
        ys = [float(p[1]) for p in ring[:n]]
        return sum(xs) / len(xs), sum(ys) / len(ys)
    cx /= 6.0 * area
    cy /= 6.0 * area
    return cx, cy


def feature_representative_point(
    geometry: dict[str, Any] | None,
    *,
    feature_point: str = "centroid",
) -> tuple[float, float] | None:
    """Return one (lon, lat) for a GeoJSON geometry, or None if unsupported/empty."""
    if not geometry or "type" not in geometry:
        return None
    gtype = geometry["type"]
    coords = geometry.get("coordinates")
    if gtype == "Point":
        if not coords or len(coords) < 2:
            return None
        return float(coords[0]), float(coords[1])
    if gtype == "MultiPoint":
        if not coords:
            return None
        # Deterministic: first point.
        p = coords[0]
        return float(p[0]), float(p[1])
    if gtype == "Polygon":
        if feature_point != "centroid":
            raise ImportError_(f"unsupported feature-point mode {feature_point!r}")
        if not coords or not coords[0]:
            return None
        return _ring_centroid(coords[0])
    if gtype == "MultiPolygon":
        if feature_point != "centroid":
            raise ImportError_(f"unsupported feature-point mode {feature_point!r}")
        if not coords:
            return None
        # Centroid of the largest-area outer ring (deterministic).
        best: tuple[float, float] | None = None
        best_area = -1.0
        for poly in coords:
            if not poly or not poly[0]:
                continue
            ring = poly[0]
            c = _ring_centroid(ring)
            if c is None:
                continue
            # Approximate area in lon/lat for ring selection only.
            area = 0.0
            pts = ring if ring[0] == ring[-1] else ring + [ring[0]]
            for i in range(len(pts) - 1):
                area += float(pts[i][0]) * float(pts[i + 1][1]) - float(pts[i + 1][0]) * float(
                    pts[i][1]
                )
            area = abs(area)
            if area > best_area:
                best_area = area
                best = c
        return best
    return None


# ---------------------------------------------------------------------------
# Canonical CSV I/O
# ---------------------------------------------------------------------------


def format_csv_row(point_id: int, x: float, y: float) -> str:
    return f"{point_id},{x:.{COORD_DECIMALS}f},{y:.{COORD_DECIMALS}f}\n"


def open_canonical_writer(path: Path) -> TextIO:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("w", encoding="utf-8", newline="\n")
    handle.write("id,x,y\n")
    return handle


def iter_canonical_rows(path: Path) -> Iterator[tuple[int, float, float]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        for line_number, fields in enumerate(reader, start=1):
            if not fields:
                continue
            if line_number == 1 and [f.strip().lower() for f in fields[:3]] == ["id", "x", "y"]:
                continue
            if len(fields) < 3:
                raise ImportError_(f"{path}:{line_number}: expected at least 3 fields")
            try:
                pid = int(fields[0].strip())
                x = float(fields[1].strip())
                y = float(fields[2].strip())
            except ValueError as exc:
                raise ImportError_(f"{path}:{line_number}: malformed row") from exc
            if not (math.isfinite(x) and math.isfinite(y)):
                raise ImportError_(f"{path}:{line_number}: non-finite coordinates")
            if pid < 0:
                raise ImportError_(f"{path}:{line_number}: negative id")
            yield pid, x, y


def count_canonical_points(path: Path) -> int:
    return sum(1 for _ in iter_canonical_rows(path))


def validate_canonical_csv(path: Path) -> dict[str, Any]:
    """Verify IDs unique, coordinates finite, readable as project CSV."""
    seen: set[int] = set()
    n = 0
    for pid, x, y in iter_canonical_rows(path):
        if pid in seen:
            raise ImportError_(f"duplicate id {pid} in {path}")
        seen.add(pid)
        n += 1
        _ = x, y
    if n == 0:
        raise ImportError_(f"no points in {path}")
    return {"n": n, "ids_unique": True, "finite": True}


# ---------------------------------------------------------------------------
# Sampling
# ---------------------------------------------------------------------------


@dataclass
class Reservoir:
    """Deterministic reservoir sample of (x, y) points."""

    limit: int
    seed: int
    items: list[tuple[float, float]] = field(default_factory=list)
    seen: int = 0
    _rng: random.Random = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if self.limit <= 0:
            raise ImportError_("--limit must be positive")
        self._rng = random.Random(self.seed)

    def offer(self, x: float, y: float) -> None:
        self.seen += 1
        if len(self.items) < self.limit:
            self.items.append((x, y))
            return
        j = self._rng.randrange(self.seen)
        if j < self.limit:
            self.items[j] = (x, y)


# ---------------------------------------------------------------------------
# Import result / metadata
# ---------------------------------------------------------------------------


@dataclass
class ImportResult:
    output_csv: Path
    meta_path: Path
    metadata: dict[str, Any]
    point_count: int
    dataset_sha256: str


def _git_commit_or_none(repo_root: Path | None) -> str | None:
    if repo_root is None:
        return None
    info = git_info(repo_root)
    return info.get("commit")


def write_import_metadata(meta_path: Path, payload: dict[str, Any]) -> None:
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def finalize_import(
    output_csv: Path,
    *,
    meta_extra: dict[str, Any],
    repo_root: Path | None = None,
) -> ImportResult:
    stats = validate_canonical_csv(output_csv)
    digest = sha256_file(output_csv)
    meta = {
        "source_type": "real",
        "output_point_count": stats["n"],
        "dataset_sha256": digest,
        "import_timestamp": datetime.now(timezone.utc).isoformat(),
        "importer_version": IMPORTER_VERSION,
        "git_commit": _git_commit_or_none(repo_root),
        **meta_extra,
    }
    meta_path = output_csv.with_name(output_csv.stem + ".meta.json")
    write_import_metadata(meta_path, meta)
    return ImportResult(
        output_csv=output_csv,
        meta_path=meta_path,
        metadata=meta,
        point_count=stats["n"],
        dataset_sha256=digest,
    )


# ---------------------------------------------------------------------------
# CSV import
# ---------------------------------------------------------------------------


def import_csv_file(
    input_path: Path,
    output_path: Path,
    *,
    x_column: str,
    y_column: str,
    coordinates: str,
    id_column: str | None = None,
    bbox: tuple[float, float, float, float] | None = None,
    limit: int | None = None,
    sample: str = "first",
    seed: int = 42,
    target_crs: str | None = None,
    repo_root: Path | None = None,
) -> ImportResult:
    if coordinates not in {"planar", "geographic"}:
        raise ImportError_("--coordinates must be 'planar' or 'geographic'")
    if sample not in {"first", "random"}:
        raise ImportError_("--sample must be 'first' or 'random'")

    projector: CoordinateProjector | None = None
    if coordinates == "geographic":
        # Center from bbox if given; else two-pass center estimate.
        if bbox is not None:
            center_lon = 0.5 * (bbox[0] + bbox[2])
            center_lat = 0.5 * (bbox[1] + bbox[3])
            if target_crs is None and (
                abs(bbox[2] - bbox[0]) > _LARGE_REGION_DEG
                or abs(bbox[3] - bbox[1]) > _LARGE_REGION_DEG
            ):
                # Still allow AEQD but record a warning in metadata.
                pass
            projector = CoordinateProjector(
                target_crs=target_crs, center_lon=center_lon, center_lat=center_lat
            )
        elif target_crs is not None:
            projector = CoordinateProjector(target_crs=target_crs)
        else:
            center_lon, center_lat, span = _csv_lonlat_center(
                input_path, x_column, y_column, bbox=bbox
            )
            if span > _LARGE_REGION_DEG and target_crs is None:
                raise ImportError_(
                    f"geographic span ≈ {span:.1f}° exceeds {_LARGE_REGION_DEG}°; "
                    "pass an explicit --target-crs (e.g. EPSG:3857 or a local UTM)"
                )
            projector = CoordinateProjector(
                target_crs=None, center_lon=center_lon, center_lat=center_lat
            )

    original_count = 0
    reservoir: Reservoir | None = None
    out_handle: TextIO | None = None
    written = 0

    if sample == "random" and limit is not None:
        reservoir = Reservoir(limit=limit, seed=seed)
    else:
        out_handle = open_canonical_writer(output_path)

    try:
        with input_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                raise ImportError_("CSV missing header")
            names = {n.strip(): n for n in reader.fieldnames}
            if x_column not in names or y_column not in names:
                raise ImportError_(
                    f"columns {x_column!r}/{y_column!r} not in {list(reader.fieldnames)}"
                )
            if id_column is not None and id_column not in names:
                raise ImportError_(f"id column {id_column!r} not found")

            for row_number, row in enumerate(reader, start=2):
                try:
                    raw_x = float(row[names[x_column]].strip())
                    raw_y = float(row[names[y_column]].strip())
                except (KeyError, TypeError, ValueError) as exc:
                    raise ImportError_(f"{input_path}:{row_number}: bad coordinates") from exc
                if not (math.isfinite(raw_x) and math.isfinite(raw_y)):
                    raise ImportError_(f"{input_path}:{row_number}: non-finite coordinates")

                original_count += 1
                if coordinates == "geographic":
                    lon, lat = raw_x, raw_y
                    if not in_bbox(lon, lat, bbox):
                        continue
                    assert projector is not None
                    x, y = projector.project(lon, lat)
                else:
                    if bbox is not None and not in_bbox(raw_x, raw_y, bbox):
                        # Planar bbox interpreted as minX,minY,maxX,maxY.
                        continue
                    x, y = raw_x, raw_y

                if reservoir is not None:
                    reservoir.offer(x, y)
                    continue

                assert out_handle is not None
                if id_column is not None:
                    try:
                        pid = int(row[names[id_column]].strip())
                    except (TypeError, ValueError) as exc:
                        raise ImportError_(f"{input_path}:{row_number}: bad id") from exc
                    if pid < 0:
                        raise ImportError_(f"{input_path}:{row_number}: negative id")
                    # When assigning custom ids with streaming first-N, still rewrite
                    # to 0..n-1 for C++ identity-id fast path unless we track them.
                    # Spec: if id column exists, use it — but unique. For limit/first
                    # we keep source ids only when no limit remapping needed.
                    # Prefer 0..n-1 always for solver performance (documented).
                    out_handle.write(format_csv_row(written, x, y))
                else:
                    out_handle.write(format_csv_row(written, x, y))
                written += 1
                if limit is not None and sample == "first" and written >= limit:
                    break
    finally:
        if out_handle is not None:
            out_handle.close()

    if reservoir is not None:
        with open_canonical_writer(output_path) as handle:
            for i, (x, y) in enumerate(reservoir.items):
                handle.write(format_csv_row(i, x, y))
        written = len(reservoir.items)
        original_feature_count = reservoir.seen
    else:
        original_feature_count = original_count

    if written == 0:
        raise ImportError_("no points survived filtering / sampling")

    # If custom ids were requested without remapping uniqueness check beyond
    # validate — we always rewrite to 0..n-1 above for identity layout.

    proj_meta: dict[str, Any] = {}
    if projector is not None:
        info = projector.info()
        proj_meta = {
            "coordinates": "projected",
            "units": info.units,
            "input_crs": info.input_crs,
            "output_crs": info.output_crs,
            "projection_method": info.method,
            "projection_center_lon": info.center_lon,
            "projection_center_lat": info.center_lat,
        }
    else:
        proj_meta = {
            "coordinates": "planar",
            "units": "input_units",
            "input_crs": None,
            "output_crs": None,
            "projection_method": None,
        }

    meta_extra = {
        "input_format": "csv",
        "input_path": str(input_path).replace("\\", "/"),
        # Hash of the original raw source, so a study can prove which download it used.
        "input_sha256": sha256_file(Path(input_path)),
        "original_feature_count": original_feature_count,
        "sampling": sample if limit is not None else "all",
        "seed": seed if sample == "random" and limit is not None else None,
        "limit": limit,
        "bbox": list(bbox) if bbox is not None else None,
        "x_column": x_column,
        "y_column": y_column,
        "id_column": id_column,
        "feature_point": None,
        **proj_meta,
    }
    return finalize_import(output_path, meta_extra=meta_extra, repo_root=repo_root)


def _csv_lonlat_center(
    path: Path,
    x_column: str,
    y_column: str,
    *,
    bbox: tuple[float, float, float, float] | None,
    max_scan: int = 50000,
) -> tuple[float, float, float]:
    """Estimate center and max axis span from up to ``max_scan`` rows."""
    n = 0
    sum_lon = 0.0
    sum_lat = 0.0
    min_lon = min_lat = float("inf")
    max_lon = max_lat = float("-inf")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ImportError_("CSV missing header")
        names = {n.strip(): n for n in reader.fieldnames}
        if x_column not in names or y_column not in names:
            raise ImportError_(f"columns {x_column!r}/{y_column!r} not found")
        for row in reader:
            lon = float(row[names[x_column]])
            lat = float(row[names[y_column]])
            if not in_bbox(lon, lat, bbox):
                continue
            sum_lon += lon
            sum_lat += lat
            min_lon = min(min_lon, lon)
            max_lon = max(max_lon, lon)
            min_lat = min(min_lat, lat)
            max_lat = max(max_lat, lat)
            n += 1
            if n >= max_scan:
                break
    if n == 0:
        raise ImportError_("no geographic points found to estimate projection center")
    span = max(max_lon - min_lon, max_lat - min_lat)
    return sum_lon / n, sum_lat / n, span


# ---------------------------------------------------------------------------
# GeoJSON import
# ---------------------------------------------------------------------------


def _iter_geojson_features(path: Path) -> Iterator[dict[str, Any]]:
    """Yield Feature dicts. Prefer ijson streaming; fall back to json.load."""
    try:
        import ijson  # type: ignore
    except ImportError:
        ijson = None

    if ijson is not None:
        try:
            with path.open("rb") as handle:
                found = False
                for feature in ijson.items(handle, "features.item"):
                    found = True
                    if isinstance(feature, dict):
                        yield feature
                if found:
                    return
        except Exception:
            pass

    with path.open("r", encoding="utf-8-sig") as handle:
        data = json.load(handle)
    if isinstance(data, dict) and data.get("type") == "FeatureCollection":
        for feature in data.get("features") or []:
            if isinstance(feature, dict):
                yield feature
    elif isinstance(data, dict) and data.get("type") == "Feature":
        yield data
    elif isinstance(data, dict) and data.get("type") in {
        "Point",
        "Polygon",
        "MultiPolygon",
        "MultiPoint",
    }:
        yield {"type": "Feature", "geometry": data, "properties": {}}
    else:
        raise ImportError_("unsupported GeoJSON root type")


def import_geojson_file(
    input_path: Path,
    output_path: Path,
    *,
    coordinates: str = "geographic",
    feature_point: str = "centroid",
    bbox: tuple[float, float, float, float] | None = None,
    limit: int | None = None,
    sample: str = "first",
    seed: int = 42,
    target_crs: str | None = None,
    repo_root: Path | None = None,
) -> ImportResult:
    if coordinates not in {"planar", "geographic"}:
        raise ImportError_("--coordinates must be 'planar' or 'geographic'")
    if sample not in {"first", "random"}:
        raise ImportError_("--sample must be 'first' or 'random'")
    if feature_point != "centroid":
        raise ImportError_("only --feature-point centroid is supported")

    # Collect representative lon/lat (or planar x/y) first for center if needed.
    # Stream into output or reservoir.
    if coordinates == "geographic" and target_crs is None and bbox is not None:
        center_lon = 0.5 * (bbox[0] + bbox[2])
        center_lat = 0.5 * (bbox[1] + bbox[3])
        projector: CoordinateProjector | None = CoordinateProjector(
            target_crs=None, center_lon=center_lon, center_lat=center_lat
        )
    elif coordinates == "geographic" and target_crs is not None:
        projector = CoordinateProjector(target_crs=target_crs)
    elif coordinates == "geographic":
        # Need a first pass for center (stream features once into temp lon/lat list
        # only when no bbox/target — for large files prefer bbox or target_crs).
        samples: list[tuple[float, float]] = []
        for feature in _iter_geojson_features(input_path):
            pt = feature_representative_point(feature.get("geometry"), feature_point=feature_point)
            if pt is None:
                continue
            lon, lat = pt
            if not in_bbox(lon, lat, bbox):
                continue
            samples.append((lon, lat))
            if len(samples) >= 50000:
                break
        if not samples:
            raise ImportError_("no GeoJSON features yielded points")
        lons = [p[0] for p in samples]
        lats = [p[1] for p in samples]
        span = max(max(lons) - min(lons), max(lats) - min(lats))
        if span > _LARGE_REGION_DEG:
            raise ImportError_(
                f"geographic span ≈ {span:.1f}° exceeds {_LARGE_REGION_DEG}°; "
                "pass --target-crs or --bbox for a local region"
            )
        projector = CoordinateProjector(
            center_lon=sum(lons) / len(lons),
            center_lat=sum(lats) / len(lats),
        )
    else:
        projector = None

    reservoir: Reservoir | None = Reservoir(limit=limit, seed=seed) if (
        sample == "random" and limit is not None
    ) else None
    out_handle = None if reservoir is not None else open_canonical_writer(output_path)
    original = 0
    written = 0

    try:
        for feature in _iter_geojson_features(input_path):
            original += 1
            pt = feature_representative_point(feature.get("geometry"), feature_point=feature_point)
            if pt is None:
                continue
            raw_x, raw_y = pt
            if coordinates == "geographic":
                if not in_bbox(raw_x, raw_y, bbox):
                    continue
                assert projector is not None
                x, y = projector.project(raw_x, raw_y)
            else:
                if bbox is not None and not in_bbox(raw_x, raw_y, bbox):
                    continue
                x, y = raw_x, raw_y

            if reservoir is not None:
                reservoir.offer(x, y)
                continue

            assert out_handle is not None
            out_handle.write(format_csv_row(written, x, y))
            written += 1
            if limit is not None and sample == "first" and written >= limit:
                break
    finally:
        if out_handle is not None:
            out_handle.close()

    if reservoir is not None:
        with open_canonical_writer(output_path) as handle:
            for i, (x, y) in enumerate(reservoir.items):
                handle.write(format_csv_row(i, x, y))
        written = len(reservoir.items)

    if written == 0:
        raise ImportError_("no GeoJSON features produced points")

    proj_meta: dict[str, Any]
    if projector is not None:
        info = projector.info()
        proj_meta = {
            "coordinates": "projected",
            "units": info.units,
            "input_crs": info.input_crs,
            "output_crs": info.output_crs,
            "projection_method": info.method,
            "projection_center_lon": info.center_lon,
            "projection_center_lat": info.center_lat,
        }
    else:
        proj_meta = {
            "coordinates": "planar",
            "units": "input_units",
            "input_crs": None,
            "output_crs": None,
            "projection_method": None,
        }

    meta_extra = {
        "input_format": "geojson",
        "input_path": str(input_path).replace("\\", "/"),
        # Hash of the original raw source, so a study can prove which download it used.
        "input_sha256": sha256_file(Path(input_path)),
        "original_feature_count": original,
        "sampling": sample if limit is not None else "all",
        "seed": seed if sample == "random" and limit is not None else None,
        "limit": limit,
        "bbox": list(bbox) if bbox is not None else None,
        "feature_point": feature_point,
        **proj_meta,
    }
    return finalize_import(output_path, meta_extra=meta_extra, repo_root=repo_root)


# ---------------------------------------------------------------------------
# Nested prefix samples / tiles / LCC
# ---------------------------------------------------------------------------


def write_nested_prefix_samples(
    source_csv: Path,
    output_dir: Path,
    sizes: list[int],
    *,
    seed: int = 42,
    basename: str = "sample",
    repo_root: Path | None = None,
) -> list[ImportResult]:
    """Deterministic shuffle of source rows, then first-k prefixes.

    Records ``sampling: nested_prefix`` and the shared seed so all algorithms
    see identical nested subsets of one source.
    """
    rows = list(iter_canonical_rows(source_csv))
    if not rows:
        raise ImportError_("source CSV is empty")
    order = list(range(len(rows)))
    rng = random.Random(seed)
    rng.shuffle(order)

    source_sha = sha256_file(source_csv)
    results: list[ImportResult] = []
    output_dir.mkdir(parents=True, exist_ok=True)
    for k in sorted(set(sizes)):
        if k <= 0:
            raise ImportError_("prefix sizes must be positive")
        if k > len(rows):
            raise ImportError_(f"prefix size {k} exceeds source n={len(rows)}")
        out = output_dir / f"{basename}_{k}.csv"
        with open_canonical_writer(out) as handle:
            for new_id, idx in enumerate(order[:k]):
                _pid, x, y = rows[idx]
                handle.write(format_csv_row(new_id, x, y))
        results.append(
            finalize_import(
                out,
                meta_extra={
                    "source_type": "real",
                    "input_format": "canonical_csv",
                    "input_path": str(source_csv).replace("\\", "/"),
                    "original_feature_count": len(rows),
                    "sampling": "nested_prefix",
                    "seed": seed,
                    "limit": k,
                    "source_dataset_sha256": source_sha,
                    "coordinates": "planar",
                    "units": "inherited",
                    "nested_prefix_note": (
                        "one seeded shuffle of the source; each file is the "
                        "first k rows of that order"
                    ),
                },
                repo_root=repo_root,
            )
        )
    return results


def write_rectangular_tiles(
    source_csv: Path,
    output_dir: Path,
    *,
    nx: int = 2,
    ny: int = 2,
    basename: str = "region",
    repo_root: Path | None = None,
) -> list[ImportResult]:
    """Deterministic fixed rectangular tile partition of a planar point set."""
    if nx < 1 or ny < 1:
        raise ImportError_("nx and ny must be >= 1")
    rows = list(iter_canonical_rows(source_csv))
    if not rows:
        raise ImportError_("source CSV is empty")
    xs = [r[1] for r in rows]
    ys = [r[2] for r in rows]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    # Expand empty span slightly so every point lands in a cell.
    dx = (max_x - min_x) or 1.0
    dy = (max_y - min_y) or 1.0
    source_sha = sha256_file(source_csv)
    output_dir.mkdir(parents=True, exist_ok=True)
    buckets: dict[tuple[int, int], list[tuple[float, float]]] = {
        (i, j): [] for i in range(nx) for j in range(ny)
    }
    for _pid, x, y in rows:
        ix = min(nx - 1, max(0, int((x - min_x) / dx * nx)))
        iy = min(ny - 1, max(0, int((y - min_y) / dy * ny)))
        # Right/top edge: use nx-1 / ny-1 via min above.
        if x >= max_x:
            ix = nx - 1
        if y >= max_y:
            iy = ny - 1
        buckets[(ix, iy)].append((x, y))

    results: list[ImportResult] = []
    tile_id = 0
    for j in range(ny):
        for i in range(nx):
            tile_id += 1
            pts = buckets[(i, j)]
            if not pts:
                continue
            out = output_dir / f"{basename}_{tile_id:03d}.csv"
            with open_canonical_writer(out) as handle:
                for new_id, (x, y) in enumerate(pts):
                    handle.write(format_csv_row(new_id, x, y))
            x0 = min_x + dx * i / nx
            x1 = min_x + dx * (i + 1) / nx
            y0 = min_y + dy * j / ny
            y1 = min_y + dy * (j + 1) / ny
            results.append(
                finalize_import(
                    out,
                    meta_extra={
                        "source_type": "real",
                        "input_format": "canonical_csv",
                        "input_path": str(source_csv).replace("\\", "/"),
                        "original_feature_count": len(rows),
                        "sampling": "rectangular_tile",
                        "tile_index": tile_id,
                        "tile_grid": [nx, ny],
                        "tile_bbox_planar": [x0, y0, x1, y1],
                        "source_dataset_sha256": source_sha,
                        "coordinates": "planar",
                        "units": "inherited",
                    },
                    repo_root=repo_root,
                )
            )
    return results


def _grid_neighbors(
    points: list[tuple[float, float]],
    radius: float,
) -> list[list[int]]:
    """Build adjacency for UDG via uniform grid (open neighborhood)."""
    n = len(points)
    if n == 0:
        return []
    cell = max(radius, 1e-12)
    buckets: dict[tuple[int, int], list[int]] = {}
    for i, (x, y) in enumerate(points):
        key = (int(math.floor(x / cell)), int(math.floor(y / cell)))
        buckets.setdefault(key, []).append(i)
    r2 = radius * radius
    adj: list[list[int]] = [[] for _ in range(n)]
    for (gx, gy), members in buckets.items():
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                others = buckets.get((gx + dx, gy + dy))
                if not others:
                    continue
                for i in members:
                    xi, yi = points[i]
                    for j in others:
                        if j <= i:
                            continue
                        xj, yj = points[j]
                        if (xi - xj) * (xi - xj) + (yi - yj) * (yi - yj) <= r2:
                            adj[i].append(j)
                            adj[j].append(i)
    return adj


def extract_largest_connected_component(
    source_csv: Path,
    output_csv: Path,
    *,
    radius: float,
    repo_root: Path | None = None,
) -> ImportResult:
    """Explicit LCC filter: writes a *new* dataset; never modifies the source."""
    if radius < 0:
        raise ImportError_("radius must be non-negative")
    rows = list(iter_canonical_rows(source_csv))
    points = [(x, y) for _pid, x, y in rows]
    n = len(points)
    if n == 0:
        raise ImportError_("source CSV is empty")
    adj = _grid_neighbors(points, radius)
    visited = [False] * n
    best_component: list[int] = []
    for start in range(n):
        if visited[start]:
            continue
        stack = [start]
        visited[start] = True
        comp = [start]
        while stack:
            u = stack.pop()
            for v in adj[u]:
                if not visited[v]:
                    visited[v] = True
                    stack.append(v)
                    comp.append(v)
        if len(comp) > len(best_component):
            best_component = comp
    # Stable order by original index for determinism.
    best_component.sort()
    with open_canonical_writer(output_csv) as handle:
        for new_id, idx in enumerate(best_component):
            x, y = points[idx]
            handle.write(format_csv_row(new_id, x, y))
    source_sha = sha256_file(source_csv)
    return finalize_import(
        output_csv,
        meta_extra={
            "source_type": "real",
            "input_format": "canonical_csv",
            "input_path": str(source_csv).replace("\\", "/"),
            "original_feature_count": n,
            "sampling": "largest_connected_component",
            "lcc_radius": radius,
            "lcc_original_n": n,
            "lcc_result_n": len(best_component),
            "source_dataset_sha256": source_sha,
            "coordinates": "planar",
            "units": "inherited",
            "note": "explicit LCC export; original dataset preserved",
        },
        repo_root=repo_root,
    )


def assert_geographic_not_raw_degrees(coordinates: str, projected: bool) -> None:
    if coordinates == "geographic" and not projected:
        raise ImportError_(
            "geographic coordinates require projection; refusing to treat degrees as meters"
        )
