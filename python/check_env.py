"""Verify the documented Python environment for tests / plots / GUI."""

from __future__ import annotations

import importlib
import sys


REQUIRED = (
    ("matplotlib", "matplotlib"),
    ("tqdm", "tqdm"),
)


def main() -> int:
    print(f"python,{sys.executable}")
    print(f"version,{sys.version.split()[0]}")
    missing: list[str] = []
    for mod, pip_name in REQUIRED:
        try:
            m = importlib.import_module(mod)
            ver = getattr(m, "__version__", "?")
            print(f"ok,{mod},{ver}")
        except ImportError:
            print(f"missing,{mod}")
            missing.append(pip_name)
    if missing:
        print("Install dependencies with the *same* interpreter:")
        print(f'  "{sys.executable}" -m pip install -r python/requirements.txt')
        print("Documented environment: CPython 3.10+ with matplotlib (see README).")
        return 1
    print("environment_ok,1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
