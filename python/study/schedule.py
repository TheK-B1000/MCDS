"""Deterministic, balanced execution orders.

Running algorithms in a fixed order on every graph confounds algorithm with
position (cache state, thermal drift, allocator state). We use a Williams
design: a Latin square in which every algorithm occupies every position equally
often *and* (for an even number of algorithms) immediately follows every other
algorithm equally often. For an odd count the square and its mirror are used
(2k rows), which restores first-order carry-over balance.

Within a cell, replicate ``r`` uses row ``(r - 1 + offset(cell)) mod rows``,
where the offset is seeded per cell. Each cell is therefore exactly balanced
whenever its replicate count is a multiple of the number of rows, and the
offset stops every cell from starting on the same row.
Which algorithm plays which symbol is fixed by a seeded permutation of the study
seed, so the schedule is reproducible and recorded per trial.
"""

from __future__ import annotations

from .seeds import seeded_rng


def williams_rows(k: int) -> list[list[int]]:
    if k <= 0:
        return []
    if k == 1:
        return [[0]]
    first: list[int] = []
    lo, hi = 0, k - 1
    take_low = True
    # Standard construction: 0, 1, k-1, 2, k-2, ...
    first.append(lo)
    lo += 1
    while lo <= hi:
        if take_low:
            first.append(lo)
            lo += 1
        else:
            first.append(hi)
            hi -= 1
        take_low = not take_low
    rows = [[(x + r) % k for x in first] for r in range(k)]
    if k % 2 == 1:
        rows += [list(reversed(row)) for row in rows]
    return rows


def symbol_assignment(algorithms: list[str], study_seed: int) -> list[str]:
    algos = list(algorithms)
    seeded_rng("schedule-symbols", study_seed, tuple(algos)).shuffle(algos)
    return algos


def schedule_index(study_seed: int, planned: dict) -> int:
    """Index into the Williams rows for one planned dataset (see module doc)."""
    from .seeds import derive_seed  # noqa: PLC0415

    offset = derive_seed("schedule-offset", study_seed, planned["cell_id"]) % 1_000_003
    return int(planned["replicate"]) - 1 + offset


def execution_order(algorithms: list[str], study_seed: int, graph_index: int) -> tuple[list[str], int]:
    """Return (order, schedule_row) for the graph at ``graph_index``."""
    rows = williams_rows(len(algorithms))
    symbols = symbol_assignment(algorithms, study_seed)
    row = graph_index % len(rows)
    return [symbols[s] for s in rows[row]], row


def position_balance(orders: list[list[str]]) -> dict[str, dict[int, int]]:
    """Counts of how often each algorithm ran in each position."""
    table: dict[str, dict[int, int]] = {}
    for order in orders:
        for pos, algo in enumerate(order):
            table.setdefault(algo, {}).setdefault(pos, 0)
            table[algo][pos] += 1
    return table
