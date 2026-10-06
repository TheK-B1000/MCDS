"""Point-set generators for MCDS experiments on implicit unit disk graphs.

Every generator writes the project's shared CSV format:

    id,x,y
    0,1.250000,4.700000
    1,1.800000,4.320000

Determinism: each generator draws from a private ``random.Random(seed)``, so a
given ``(type, n, seed, parameters)`` tuple always produces byte-identical
output. This matters because experimental comparisons between algorithms are
only meaningful on identical inputs.

Dependencies: the standard library only.

Example:

    python python/generators.py --type clustered --n 5000 --seed 42 \\
        --clusters 5 --output datasets/clustered_5000.csv
"""

from __future__ import annotations

import argparse
import math
import os
import random
import sys
from dataclasses import dataclass, field
from typing import Any

# The unit disk graph radius the whole project uses.
UNIT_RADIUS = 1.0

# Coordinates are written with this many decimals. Enough to keep distances well
# clear of the radius-1 boundary while staying human-readable.
COORD_DECIMALS = 6

GENERATOR_TYPES = ("uniform", "clustered", "perturbed_grid", "corridor", "cluster_bridge", "dumbbell")


# ---------------------------------------------------------------------------
# Region sizing
# ---------------------------------------------------------------------------


def side_for_density(n: int, density: float) -> float:
    """Side of the square region holding ``n`` points at ``density`` per unit area.

    Density is the natural knob for unit disk graphs: the expected degree of an
    interior point is ``density * pi * R^2``, so ``density`` controls how dense
    the implicit graph is independently of ``n``.
    """
    if density <= 0.0:
        raise ValueError("density must be positive")
    return math.sqrt(n / density)


def resolve_region(
    n: int,
    density: float,
    width: float | None,
    height: float | None,
    region: float | None,
) -> tuple[float, float]:
    """Resolve the rectangular region for uniform / clustered generators.

    Precedence:
      1. ``--width`` / ``--height`` (either alone implies a square)
      2. ``--region`` (square side)
      3. side inferred from ``n`` and ``--density``
    """
    if width is not None or height is not None:
        w = width if width is not None else height
        h = height if height is not None else width
        assert w is not None and h is not None
        if w <= 0.0 or h <= 0.0:
            raise ValueError("width and height must be positive")
        return float(w), float(h)
    if region is not None:
        if region <= 0.0:
            raise ValueError("region must be positive")
        return float(region), float(region)
    side = side_for_density(n, density)
    return side, side


# ---------------------------------------------------------------------------
# Generators. Each returns a list of (x, y) tuples.
# ---------------------------------------------------------------------------


def gen_uniform(n: int, rng: random.Random, width: float, height: float) -> list[tuple[float, float]]:
    """Points spread uniformly at random over a ``width`` x ``height`` rectangle."""
    return [(rng.uniform(0.0, width), rng.uniform(0.0, height)) for _ in range(n)]


def gen_clustered(
    n: int,
    rng: random.Random,
    width: float,
    height: float,
    clusters: int,
    spread: float,
    background_fraction: float = 0.5,
    spread_relative: float | None = None,
) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
    """Gaussian hotspots on a uniform background field.

    ``spread_relative = None`` (D3 v1): hotspot sigma = ``spread`` (absolute) and
    hotspot points may fall outside the window.
    ``spread_relative = s`` (D3 v2, scale-invariant, finite window): sigma =
    s * L with L = sqrt(width * height), and every hotspot point is redrawn
    (same rng stream) until it lies inside the window. Local density then
    depends on the declared density, not on n (thermodynamic scaling).

    Returns ``(points, centers)``. Draw order (fixed, part of the definition):
    ``clusters`` centres uniform in the region; then
    ``round(background_fraction * n)`` background points uniform in the region;
    then the remaining points assigned round-robin to the hotspots, Gaussian
    around their centre with standard deviation ``spread``.

    With ``background_fraction = 0`` this is exactly the pre-v1-lock "blobs
    only" construction, whose connectivity collapses with n (the blobs drift
    apart as the region grows); the background field keeps the graph
    connectable at every n while the point set stays clearly clustered. See
    docs/methodology_audit.md (clustered redesign) for the calibration evidence.
    """
    if clusters < 1:
        raise ValueError("clusters must be at least 1")
    if spread <= 0.0:
        raise ValueError("spread must be positive")
    if not 0.0 <= background_fraction < 1.0:
        raise ValueError("background-fraction must be in [0, 1)")
    if spread_relative is not None and spread_relative <= 0.0:
        raise ValueError("spread-relative must be positive")
    centers = [(rng.uniform(0.0, width), rng.uniform(0.0, height)) for _ in range(clusters)]
    n_background = int(round(background_fraction * n))
    points = [(rng.uniform(0.0, width), rng.uniform(0.0, height)) for _ in range(n_background)]
    sigma = spread if spread_relative is None else spread_relative * math.sqrt(width * height)
    for i in range(n - n_background):
        cx, cy = centers[i % clusters]
        while True:
            x = cx + rng.gauss(0.0, sigma)
            y = cy + rng.gauss(0.0, sigma)
            if spread_relative is None or (0.0 <= x <= width and 0.0 <= y <= height):
                break
        points.append((x, y))
    return points, centers


def gen_dumbbell(
    n: int,
    rng: random.Random,
    density: float,
    neck_width: float,
    neck_length: float,
) -> tuple[list[tuple[float, float]], dict[str, float]]:
    """Bottleneck domain: two squares joined by a narrow corridor (neck).

    Total area n / density; points uniform over the domain at that intensity.
    Squares of side a = sqrt((n/density - w*l)/2) grow with n; the neck keeps a
    fixed width w and length l in units of the communication radius, so the
    bottleneck character does not drift with scale. Neck points =
    round(n * w * l / A); the rest are split equally between the squares (the
    left square gets the extra one). Draw order: left square, neck, right square.
    """
    if neck_width <= 0.0 or neck_length <= 0.0:
        raise ValueError("neck width and length must be positive")
    area = n / density
    if area <= neck_width * neck_length:
        raise ValueError("domain too small for the neck at this n and density")
    a = math.sqrt((area - neck_width * neck_length) / 2.0)
    n_neck = int(round(n * neck_width * neck_length / area))
    n_right = (n - n_neck) // 2
    n_left = n - n_neck - n_right
    y0 = a / 2.0 - neck_width / 2.0
    points = [(rng.uniform(0.0, a), rng.uniform(0.0, a)) for _ in range(n_left)]
    points += [(rng.uniform(a, a + neck_length), rng.uniform(y0, y0 + neck_width)) for _ in range(n_neck)]
    points += [(rng.uniform(a + neck_length, 2 * a + neck_length), rng.uniform(0.0, a)) for _ in range(n_right)]
    return points, {"square_side": a, "neck_points": n_neck, "neck_share": n_neck / n}


def gen_perturbed_grid(
    n: int,
    rng: random.Random,
    spacing: float,
    jitter: float,
) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
    """A near-square lattice of ``spacing`` with each point offset by up to ``jitter``.

    Returns ``(points, base_grid_positions)``. With ``spacing < 1.0`` this gives a
    highly regular, reliably connected UDG.
    """
    if spacing <= 0.0:
        raise ValueError("spacing must be positive")
    if jitter < 0.0:
        raise ValueError("jitter must be non-negative")
    cols = max(1, math.ceil(math.sqrt(n)))
    bases: list[tuple[float, float]] = []
    points: list[tuple[float, float]] = []
    for i in range(n):
        gx = i % cols
        gy = i // cols
        base = (gx * spacing, gy * spacing)
        bases.append(base)
        points.append(
            (
                base[0] + rng.uniform(-jitter, jitter),
                base[1] + rng.uniform(-jitter, jitter),
            )
        )
    return points, bases


def gen_corridor(
    n: int,
    rng: random.Random,
    corridor_width: float,
    density: float,
    length: float | None = None,
) -> list[tuple[float, float]]:
    """Points uniform inside a long narrow strip of height ``corridor_width``.

    Length defaults so the strip holds ``n`` points at the requested density.
    A corridor forces any connected dominating set into a long path.
    """
    if corridor_width <= 0.0:
        raise ValueError("corridor-width must be positive")
    if length is None:
        length = max(corridor_width, n / (density * corridor_width))
    if length <= 0.0:
        raise ValueError("corridor length must be positive")
    return [(rng.uniform(0.0, length), rng.uniform(0.0, corridor_width)) for _ in range(n)]


def gen_cluster_bridge(
    n: int,
    rng: random.Random,
    clusters: int,
    spread: float,
    bridge_fraction: float,
    bridge_width: float,
) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
    """Dense blobs laid out in a row and linked by thin chains of points.

    Returns ``(points, centers)``. ``bridge_fraction`` of the points are spent on
    the chains; the rest are split among the clusters.
    """
    if clusters < 2:
        raise ValueError("cluster-bridge needs at least 2 clusters")
    if spread <= 0.0:
        raise ValueError("spread must be positive")
    if not 0.0 <= bridge_fraction < 1.0:
        raise ValueError("bridge-fraction must be in [0, 1)")
    if bridge_width <= 0.0:
        raise ValueError("bridge-width must be positive")

    # Space centres far enough apart that the blobs do not merge on their own.
    center_gap = max(6.0 * spread, 8.0 * UNIT_RADIUS)
    centers = [(i * center_gap, 0.0) for i in range(clusters)]

    n_bridge_total = int(round(n * bridge_fraction))
    n_cluster_total = n - n_bridge_total

    points: list[tuple[float, float]] = []
    for i in range(n_cluster_total):
        cx, cy = centers[i % clusters]
        points.append((cx + rng.gauss(0.0, spread), cy + rng.gauss(0.0, spread)))

    gaps = clusters - 1
    for gap_index in range(gaps):
        share = n_bridge_total // gaps + (1 if gap_index < n_bridge_total % gaps else 0)
        if share == 0:
            continue
        x0, y0 = centers[gap_index]
        x1, y1 = centers[gap_index + 1]
        for k in range(share):
            t = (k + 0.5) / share
            points.append(
                (
                    x0 + t * (x1 - x0) + rng.uniform(-0.1, 0.1),
                    y0 + t * (y1 - y0) + rng.uniform(-bridge_width / 2.0, bridge_width / 2.0),
                )
            )
    return points, centers


# ---------------------------------------------------------------------------
# Library API
# ---------------------------------------------------------------------------


@dataclass
class GenerationResult:
    """Points plus the metadata needed for diagnostics and tests."""

    points: list[tuple[float, float]]
    type: str
    n: int
    seed: int
    parameters: dict[str, Any] = field(default_factory=dict)
    centers: list[tuple[float, float]] | None = None
    base_positions: list[tuple[float, float]] | None = None

    def bounding_box(self) -> tuple[float, float, float, float]:
        xs = [p[0] for p in self.points]
        ys = [p[1] for p in self.points]
        return min(xs), max(xs), min(ys), max(ys)

    def metadata_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "n": self.n,
            "seed": self.seed,
            "parameters": dict(self.parameters),
            "centers": self.centers,
        }


def generate(
    type: str,
    n: int,
    seed: int = 0,
    *,
    density: float = 2.0,
    width: float | None = None,
    height: float | None = None,
    region: float | None = None,
    clusters: int = 8,
    spread: float = 0.5,
    spacing: float | None = None,
    jitter: float = 0.2,
    corridor_width: float = 2.0,
    bridge_fraction: float = 0.15,
    bridge_width: float = 0.5,
    background_fraction: float = 0.5,
    spread_relative: float | None = None,
    neck_width: float = 1.0,
    neck_length: float = 3.0,
) -> GenerationResult:
    """Generate a point set. Pure library entry point used by tests and later runners."""
    if type not in GENERATOR_TYPES:
        raise ValueError(f"unknown generator type {type!r}")
    if n <= 0:
        raise ValueError("n must be positive")

    rng = random.Random(seed)
    params: dict[str, Any] = {"density": density}

    if type == "uniform":
        w, h = resolve_region(n, density, width, height, region)
        params.update({"width": w, "height": h})
        points = gen_uniform(n, rng, w, h)
        return GenerationResult(points=points, type=type, n=n, seed=seed, parameters=params)

    if type == "clustered":
        w, h = resolve_region(n, density, width, height, region)
        params.update({"width": w, "height": h, "clusters": clusters, "spread": spread,
                       "background_fraction": background_fraction, "spread_relative": spread_relative})
        points, centers = gen_clustered(n, rng, w, h, clusters, spread, background_fraction, spread_relative)
        return GenerationResult(
            points=points, type=type, n=n, seed=seed, parameters=params, centers=centers
        )

    if type == "perturbed_grid":
        resolved_spacing = spacing if spacing is not None else 1.0 / math.sqrt(density)
        absolute_jitter = jitter * resolved_spacing
        params.update({"spacing": resolved_spacing, "jitter": jitter, "absolute_jitter": absolute_jitter})
        points, bases = gen_perturbed_grid(n, rng, resolved_spacing, absolute_jitter)
        return GenerationResult(
            points=points, type=type, n=n, seed=seed, parameters=params, base_positions=bases
        )

    if type == "corridor":
        length = max(corridor_width, n / (density * corridor_width))
        params.update({"corridor_width": corridor_width, "length": length})
        points = gen_corridor(n, rng, corridor_width, density, length=length)
        return GenerationResult(points=points, type=type, n=n, seed=seed, parameters=params)

    if type == "dumbbell":
        points, info = gen_dumbbell(n, rng, density, neck_width, neck_length)
        params.update({"neck_width": neck_width, "neck_length": neck_length, **info})
        return GenerationResult(points=points, type=type, n=n, seed=seed, parameters=params)

    if type == "cluster_bridge":
        params.update(
            {
                "clusters": clusters,
                "spread": spread,
                "bridge_fraction": bridge_fraction,
                "bridge_width": bridge_width,
            }
        )
        points, centers = gen_cluster_bridge(
            n, rng, clusters, spread, bridge_fraction, bridge_width
        )
        return GenerationResult(
            points=points, type=type, n=n, seed=seed, parameters=params, centers=centers
        )

    raise ValueError(f"unknown generator type {type!r}")


# ---------------------------------------------------------------------------
# CSV I/O
# ---------------------------------------------------------------------------


def write_csv(path: str, points: list[tuple[float, float]]) -> None:
    """Writes points with ids 0..n-1 in list order.

    Ids are the identity permutation, which lets the C++ side skip its id lookup
    table entirely.
    """
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("id,x,y\n")
        for i, (x, y) in enumerate(points):
            handle.write(f"{i},{x:.{COORD_DECIMALS}f},{y:.{COORD_DECIMALS}f}\n")


def read_csv(path: str) -> list[tuple[int, float, float]]:
    """Reads back the shared format. Used by visualization and by tests."""
    rows = []
    with open(path, "r", encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, start=1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            fields = [f.strip() for f in line.split(",")]
            if line_number == 1 and fields[:3] == ["id", "x", "y"]:
                continue
            if len(fields) != 3:
                raise ValueError(f"{path}:{line_number}: expected 3 fields, got {len(fields)}")
            rows.append((int(fields[0]), float(fields[1]), float(fields[2])))
    return rows


def csv_bytes(points: list[tuple[float, float]]) -> bytes:
    """Canonical CSV bytes for a point set (used by determinism tests)."""
    lines = ["id,x,y\n"]
    for i, (x, y) in enumerate(points):
        lines.append(f"{i},{x:.{COORD_DECIMALS}f},{y:.{COORD_DECIMALS}f}\n")
    return "".join(lines).encode("utf-8")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate 2D point sets for implicit-UDG MCDS experiments.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--type", required=True, choices=GENERATOR_TYPES)
    parser.add_argument("--n", type=int, required=True, help="number of points")
    parser.add_argument("--seed", type=int, default=0, help="RNG seed; fixes the output exactly")
    parser.add_argument("--output", required=True, help="destination CSV path")

    parser.add_argument(
        "--density",
        type=float,
        default=2.0,
        help="points per unit area; expected degree is about density * pi * R^2",
    )
    parser.add_argument(
        "--region",
        type=float,
        default=None,
        help="explicit square side length (legacy); prefer --width/--height",
    )
    parser.add_argument("--width", type=float, default=None, help="region width")
    parser.add_argument("--height", type=float, default=None, help="region height")

    parser.add_argument("--clusters", type=int, default=8, help="clustered / cluster_bridge")
    parser.add_argument(
        "--spread",
        type=float,
        default=0.5,
        help="Gaussian cluster standard deviation (alias: --cluster-sigma)",
    )
    parser.add_argument(
        "--cluster-sigma",
        type=float,
        default=None,
        dest="cluster_sigma",
        help=argparse.SUPPRESS,  # backward-compatible alias for --spread
    )

    parser.add_argument("--spacing", type=float, default=None, help="perturbed_grid lattice spacing")
    parser.add_argument(
        "--jitter",
        type=float,
        default=0.2,
        help="perturbed_grid offset as a fraction of spacing",
    )

    parser.add_argument("--corridor-width", type=float, default=2.0, dest="corridor_width")
    parser.add_argument("--bridge-fraction", type=float, default=0.15, dest="bridge_fraction")
    parser.add_argument("--bridge-width", type=float, default=0.5, dest="bridge_width")
    parser.add_argument("--spread-relative", type=float, default=None, dest="spread_relative",
                        help="clustered v2: hotspot sigma = s * L, hotspots restricted to the window")
    parser.add_argument("--neck-width", type=float, default=1.0, dest="neck_width", help="dumbbell neck width")
    parser.add_argument("--neck-length", type=float, default=3.0, dest="neck_length", help="dumbbell neck length")
    parser.add_argument(
        "--background-fraction",
        type=float,
        default=0.5,
        dest="background_fraction",
        help="clustered: share of points on the uniform background field (rest in hotspots)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if args.n <= 0:
        parser.error("--n must be positive")

    spread = args.cluster_sigma if args.cluster_sigma is not None else args.spread

    result = generate(
        type=args.type,
        n=args.n,
        seed=args.seed,
        density=args.density,
        width=args.width,
        height=args.height,
        region=args.region,
        clusters=args.clusters,
        spread=spread,
        spacing=args.spacing,
        jitter=args.jitter,
        corridor_width=args.corridor_width,
        bridge_fraction=args.bridge_fraction,
        bridge_width=args.bridge_width,
        background_fraction=args.background_fraction,
        spread_relative=args.spread_relative,
        neck_width=args.neck_width,
        neck_length=args.neck_length,
    )
    write_csv(args.output, result.points)

    min_x, max_x, min_y, max_y = result.bounding_box()
    print(
        f"wrote {len(result.points)} points to {args.output}\n"
        f"  type={result.type} seed={result.seed}\n"
        f"  parameters={result.parameters}\n"
        f"  x range [{min_x:.3f}, {max_x:.3f}]  y range [{min_y:.3f}, {max_y:.3f}]"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
