"""Deterministic, collision-resistant seed derivation.

The pre-upgrade runner used ``effective_seed = base_seed + attempt`` for
connectivity retries, so replicate 1's second attempt reused replicate 2's
first seed. In the early pilot 31 point sets were shared by more than one
"independent" replicate.

The runner now derives every seed by hashing *all* of its coordinates, so two
different (cell, replicate, attempt) triples cannot share a seed except by a
SHA-256 collision, and changing one factor level never shifts another's seeds.
The fairness checker additionally verifies that accepted datasets are unique.
"""

from __future__ import annotations

import hashlib
import random
from typing import Any

SEED_BITS = 63


def derive_seed(namespace: str, *parts: Any) -> int:
    """Stable 63-bit seed from a namespace and arbitrary JSON-like parts."""
    text = "\x1f".join([namespace, *(repr(p) for p in parts)])
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") & ((1 << SEED_BITS) - 1)


def graph_seed(study_seed: int, geometry: str, n: int, density: float, radius: float,
               replicate: int, attempt: int) -> int:
    return derive_seed("graph", study_seed, geometry, int(n), float(density), float(radius),
                       int(replicate), int(attempt))


def seeded_rng(namespace: str, *parts: Any) -> random.Random:
    return random.Random(derive_seed(namespace, *parts))
