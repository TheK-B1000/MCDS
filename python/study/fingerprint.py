"""Dataset fingerprints shared with the C++ harness.

``points_fingerprint`` reproduces ``mcds::bench::pointsFingerprint`` exactly:
FNV-1a 64 over n (uint64 LE), then each point's id (int64 LE) and x, y
(IEEE-754 binary64 LE) in file order. Python's ``float()`` and the C++ CSV
parser both round the decimal text correctly, so equal fingerprints prove the
solver saw the same coordinates Python wrote.
"""

from __future__ import annotations

import hashlib
import struct
from pathlib import Path

_FNV_OFFSET = 14695981039346656037
_FNV_PRIME = 1099511628211
_MASK = (1 << 64) - 1


def _fnv(h: int, data: bytes) -> int:
    for byte in data:
        h ^= byte
        h = (h * _FNV_PRIME) & _MASK
    return h


def points_fingerprint(points: list[tuple[int, float, float]]) -> str:
    h = _fnv(_FNV_OFFSET, struct.pack("<Q", len(points)))
    for pid, x, y in points:
        h = _fnv(h, struct.pack("<qdd", int(pid), float(x), float(y)))
    return f"{h:016x}"


def read_canonical_points(path: Path) -> list[tuple[int, float, float]]:
    """Reads the project CSV with the same leniency as the C++ loader."""
    rows: list[tuple[int, float, float]] = []
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_number, raw in enumerate(handle, start=1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            fields = [f.strip() for f in line.split(",")]
            if fields[:3] == ["id", "x", "y"] and not rows:
                continue
            if len(fields) != 3:
                raise ValueError(f"{path}:{line_number}: expected 3 fields")
            rows.append((int(fields[0]), float(fields[1]), float(fields[2])))
    return rows


def file_points_fingerprint(path: Path) -> str:
    return points_fingerprint(read_canonical_points(path))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def graph_id_for(dataset_sha256: str, radius: float) -> str:
    """A graph is (exact point bytes, radius). Same file + new radius = new graph."""
    text = f"{dataset_sha256}|{float(radius)!r}"
    return "g_" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
