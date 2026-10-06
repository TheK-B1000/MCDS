"""Progress bars for long study loops.

Uses tqdm when available and enabled. Logging goes through ``tqdm.write`` so
messages do not break the bar. Disable with ``show_progress=False`` or
``--no-progress`` on the CLI.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Callable, Iterable, Iterator, TypeVar

T = TypeVar("T")

try:
    from tqdm import tqdm as _tqdm
except ImportError:  # pragma: no cover - preflight requires tqdm
    _tqdm = None  # type: ignore[misc, assignment]


def make_logger(base: Callable[[str], None] | None = None) -> Callable[[str], None]:
    """Return a logger that is safe alongside an active tqdm bar.

    If ``base`` is provided (e.g. a test sink), it is used as-is. Otherwise
    messages go through ``tqdm.write`` when tqdm is installed.
    """
    if base is not None:
        return base

    def _log(msg: str) -> None:
        if _tqdm is not None:
            _tqdm.write(str(msg))
        else:
            print(str(msg))

    return _log


@contextmanager
def track(
    iterable: Iterable[T],
    *,
    total: int | None = None,
    desc: str,
    unit: str,
    enabled: bool = True,
    leave: bool = True,
) -> Iterator[Any]:
    """Yield a tqdm iterator when progress is enabled, else the raw iterable."""
    items = list(iterable) if total is None and not hasattr(iterable, "__len__") else iterable
    n = total if total is not None else (len(items) if hasattr(items, "__len__") else None)
    if not enabled or _tqdm is None or n == 0:
        yield items
        return
    bar = _tqdm(
        items,
        total=n,
        desc=desc,
        unit=unit,
        dynamic_ncols=True,
        leave=leave,
        mininterval=0.5,
    )
    try:
        yield bar
    finally:
        bar.close()
