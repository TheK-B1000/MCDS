"""Point-set generators for MCDS experiments on implicit unit disk graphs.

Every generator writes the project's shared CSV format:

    id,x,y
    0,1.250000,4.700000
    1,1.800000,4.320000

Determinism: each generator draws from a private ``random.Random(seed)``, so a
given ``(type, n, seed, parameters)`` tuple always produces byte-identical
output. This matters because experimental comparisons between algorithms are
only meaningful on identical inputs.

Dependencies: the standard library only. NumPy is not installed in this
environment and is not needed at these sizes.

Example:

    python generators.py --type uniform --n 1000 --seed 42 \
        --output datasets/uniform_1000.csv
"""

from __future__ import annotations

import argparse
import math
import os
import random
import sys

# The unit disk graph radius the whole project uses.
UNIT_RADIUS = 1.0

# Coordinates are written with this many decimals. Enough to keep distances well
# clear of the radius-1 boundary while staying human-readable.
COORD_DECIMALS = 6


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
    cluster_sigma: float,
) -> list[tuple[float, float]]:
    """``clusters`` Gaussian blobs of points scattered over the region.

    Cluster centres are uniform in the region; members are Gaussian around their
    centre with standard deviation ``cluster_sigma``. The resulting UDG usually
    has dense cliques joined weakly or not at all, which stresses connectivity.
    """
    if clusters < 1:
        raise ValueError("clusters must be at least 1")
    centers = [(rng.uniform(0.0, width), rng.uniform(0.0, height)) for _ in range(clusters)]
    points = []
    for i in range(n):
        cx, cy = centers[i % clusters]
        points.append((cx + rng.gauss(0.0, cluster_sigma), cy + rng.gauss(0.0, cluster_sigma)))
    return points


def gen_perturbed_grid(
    n: int,
    rng: random.Random,
    spacing: float,
    jitter: float,
) -> list[tuple[float, float]]:
    """A near-square lattice of ``spacing`` with each point offset by up to ``jitter``.

    With ``spacing < 1.0`` this gives a highly regular, reliably connected UDG,
    which is the easiest case for any CDS heuristic and therefore a useful
    baseline.
    """
    cols = max(1, math.ceil(math.sqrt(n)))
    points = []
    for i in range(n):
        gx = i % cols
        gy = i // cols
        points.append(
            (
                gx * spacing + rng.uniform(-jitter, jitter),
                gy * spacing + rng.uniform(-jitter, jitter),
            )
        )
    return points


def gen_corridor(
    n: int,
    rng: random.Random,
    corridor_width: float,
    density: float,
) -> list[tuple[float, float]]:
    """Points uniform inside a long narrow strip of height ``corridor_width``.

    Length is chosen so the strip holds ``n`` points at the requested density.
    A corridor forces any connected dominating set into a long path, so the CDS
    is a large fraction of ``n`` -- close to the worst case for solution size.
    """
    if corridor_width <= 0.0:
        raise ValueError("corridor-width must be positive")
    length = max(corridor_width, n / (density * corridor_width))
    return [(rng.uniform(0.0, length), rng.uniform(0.0, corridor_width)) for _ in range(n)]


def gen_cluster_bridge(
    n: int,
    rng: random.Random,
    clusters: int,
    cluster_sigma: float,
    bridge_fraction: float,
    bridge_width: float,
) -> list[tuple[float, float]]:
    """Dense blobs laid out in a row and linked by thin chains of points.

    ``bridge_fraction`` of the points are spent on the chains that join
    consecutive cluster centres; the rest are split evenly among the clusters.
    Bridge points are spaced to stay within the unit radius so the whole instance
    is connected, which makes this the interesting adversarial case: a correct
    CDS must include the bridges, and a greedy heuristic that only chases
    coverage may fail to.
    """
    if clusters < 2:
        raise ValueError("cluster-bridge needs at least 2 clusters")
    if not 0.0 <= bridge_fraction < 1.0:
        raise ValueError("bridge-fraction must be in [0, 1)")

    # Space centres far enough apart that the blobs do not merge on their own.
    center_gap = max(6.0 * cluster_sigma, 8.0 * UNIT_RADIUS)
    centers = [(i * center_gap, 0.0) for i in range(clusters)]

    n_bridge_total = int(round(n * bridge_fraction))
    n_cluster_total = n - n_bridge_total

    points: list[tuple[float, float]] = []
    for i in range(n_cluster_total):
        cx, cy = centers[i % clusters]
        points.append((cx + rng.gauss(0.0, cluster_sigma), cy + rng.gauss(0.0, cluster_sigma)))

    # Distribute bridge points over the (clusters - 1) gaps.
    gaps = clusters - 1
    for gap_index in range(gaps):
        share = n_bridge_total // gaps + (1 if gap_index < n_bridge_total % gaps else 0)
        if share == 0:
            continue
        x0, y0 = centers[gap_index]
        x1, y1 = centers[gap_index + 1]
        for k in range(share):
            # Evenly spaced along the segment, jittered across it.
            t = (k + 0.5) / share
            points.append(
                (
                    x0 + t * (x1 - x0) + rng.uniform(-0.1, 0.1),
                    y0 + t * (y1 - y0) + rng.uniform(-bridge_width / 2.0, bridge_width / 2.0),
                )
            )
    return points


# ---------------------------------------------------------------------------
# CSV output
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


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

GENERATOR_TYPES = ("uniform", "clustered", "perturbed_grid", "corridor", "cluster_bridge")


def build_points(args: argparse.Namespace) -> list[tuple[float, float]]:
    rng = random.Random(args.seed)

    if args.type == "uniform":
        side = args.region if args.region is not None else side_for_density(args.n, args.density)
        return gen_uniform(args.n, rng, side, side)

    if args.type == "clustered":
        side = args.region if args.region is not None else side_for_density(args.n, args.density)
        return gen_clustered(args.n, rng, side, side, args.clusters, args.cluster_sigma)

    if args.type == "perturbed_grid":
        # Default spacing packs the lattice at the requested density.
        spacing = args.spacing if args.spacing is not None else 1.0 / math.sqrt(args.density)
        return gen_perturbed_grid(args.n, rng, spacing, args.jitter * spacing)

    if args.type == "corridor":
        return gen_corridor(args.n, rng, args.corridor_width, args.density)

    if args.type == "cluster_bridge":
        return gen_cluster_bridge(
            args.n, rng, args.clusters, args.cluster_sigma, args.bridge_fraction, args.bridge_width
        )

    raise ValueError(f"unknown generator type {args.type!r}")


def main(argv: list[str] | None = None) -> int:
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
        help="explicit square side length, overriding --density",
    )

    parser.add_argument("--clusters", type=int, default=8, help="clustered / cluster_bridge only")
    parser.add_argument("--cluster-sigma", type=float, default=0.5, help="cluster spread")

    parser.add_argument("--spacing", type=float, default=None, help="perturbed_grid lattice spacing")
    parser.add_argument(
        "--jitter",
        type=float,
        default=0.2,
        help="perturbed_grid offset, as a fraction of spacing",
    )

    parser.add_argument("--corridor-width", type=float, default=2.0, help="corridor only")

    parser.add_argument("--bridge-fraction", type=float, default=0.15, help="cluster_bridge only")
    parser.add_argument("--bridge-width", type=float, default=0.5, help="cluster_bridge only")

    args = parser.parse_args(argv)

    if args.n <= 0:
        parser.error("--n must be positive")

    points = build_points(args)
    write_csv(args.output, points)

    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    print(
        f"wrote {len(points)} points to {args.output}\n"
        f"  type={args.type} seed={args.seed}\n"
        f"  x range [{min(xs):.3f}, {max(xs):.3f}]  y range [{min(ys):.3f}, {max(ys):.3f}]"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
