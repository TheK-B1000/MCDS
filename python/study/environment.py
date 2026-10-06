"""Environment snapshot (provenance only — never used to alter behaviour)."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .fingerprint import sha256_file

ALGORITHM_SOURCES = {
    "marathe": ["cpp/src/algorithms/Marathe.cpp", "cpp/include/algorithms/Marathe.hpp"],
    "wan": ["cpp/src/algorithms/Wan.cpp", "cpp/include/algorithms/Wan.hpp"],
    "funke": ["cpp/src/algorithms/Funke.cpp", "cpp/include/algorithms/Funke.hpp"],
    "li": [
        "cpp/src/algorithms/LiSMIS.cpp",
        "cpp/include/algorithms/LiSMIS.hpp",
        "cpp/src/algorithms/WanLevelMis.cpp",
        "cpp/include/algorithms/WanLevelMis.hpp",
    ],
}

# Files whose semantics every algorithm shares; hashed so a study records them.
SHARED_SOURCES = [
    "cpp/src/GridSpatialIndex.cpp",
    "cpp/include/GridSpatialIndex.hpp",
    "cpp/include/SpatialIndex.hpp",
    "cpp/src/Validator.cpp",
    "cpp/src/Connectivity.cpp",
    "cpp/src/CsvIO.cpp",
    "cpp/src/PointSet.cpp",
    "python/generators.py",
]

TRACKED_PACKAGES = ("matplotlib", "tqdm", "pyproj", "ijson", "numpy")


def _run(cmd: list[str], cwd: Path | None = None) -> str | None:
    try:
        return subprocess.check_output(cmd, cwd=str(cwd) if cwd else None, text=True,
                                       stderr=subprocess.DEVNULL, timeout=30).strip()
    except Exception:  # noqa: BLE001
        return None


def git_snapshot(repo_root: Path) -> dict[str, Any]:
    status = _run(["git", "status", "--porcelain"], repo_root)
    return {
        "commit": _run(["git", "rev-parse", "HEAD"], repo_root),
        "branch": _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], repo_root),
        "describe": _run(["git", "describe", "--tags", "--always", "--dirty"], repo_root),
        "dirty": None if status is None else bool(status),
        "dirty_files": None if status is None else [line[3:] for line in status.splitlines()][:200],
    }


def cpu_name() -> str | None:
    system = platform.system()
    try:
        if system == "Windows":
            import winreg  # noqa: PLC0415

            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
            return str(winreg.QueryValueEx(key, "ProcessorNameString")[0]).strip()
        if system == "Linux":
            for line in Path("/proc/cpuinfo").read_text().splitlines():
                if line.lower().startswith("model name"):
                    return line.split(":", 1)[1].strip()
        if system == "Darwin":
            return _run(["sysctl", "-n", "machdep.cpu.brand_string"])
    except Exception:  # noqa: BLE001
        pass
    return platform.processor() or None


def physical_cores() -> int | None:
    try:
        import psutil  # type: ignore  # noqa: PLC0415

        return psutil.cpu_count(logical=False)
    except Exception:  # noqa: BLE001
        pass
    system = platform.system()
    if system == "Windows":
        out = _run(["powershell", "-NoProfile", "-Command",
                    "(Get-CimInstance Win32_Processor | Measure-Object -Property NumberOfCores -Sum).Sum"])
        return int(out) if out and out.isdigit() else None
    if system == "Linux":
        try:
            cores = set()
            phys = core = None
            for line in Path("/proc/cpuinfo").read_text().splitlines():
                if line.startswith("physical id"):
                    phys = line.split(":")[1].strip()
                elif line.startswith("core id"):
                    core = line.split(":")[1].strip()
                    cores.add((phys, core))
            return len(cores) or None
        except Exception:  # noqa: BLE001
            return None
    if system == "Darwin":
        out = _run(["sysctl", "-n", "hw.physicalcpu"])
        return int(out) if out and out.isdigit() else None
    return None


def total_ram_bytes() -> int | None:
    try:
        if platform.system() == "Windows":
            import ctypes  # noqa: PLC0415

            class MemoryStatusEx(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            stat = MemoryStatusEx()
            stat.dwLength = ctypes.sizeof(MemoryStatusEx)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):  # type: ignore[attr-defined]
                return int(stat.ullTotalPhys)
        else:
            return int(os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE"))
    except Exception:  # noqa: BLE001
        pass
    return None


def power_plan() -> str | None:
    if platform.system() == "Windows":
        return _run(["powercfg", "/getactivescheme"])
    gov = Path("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor")
    try:
        return gov.read_text().strip() if gov.exists() else None
    except OSError:
        return None


def package_versions() -> dict[str, str | None]:
    from importlib import metadata  # noqa: PLC0415

    out: dict[str, str | None] = {}
    for name in TRACKED_PACKAGES:
        try:
            out[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            out[name] = None
    return out


def source_hashes(repo_root: Path) -> dict[str, Any]:
    def combined(paths: list[str]) -> str | None:
        digest = hashlib.sha256()
        for rel in paths:
            p = repo_root / rel
            if not p.is_file():
                return None
            digest.update(rel.encode("utf-8") + b"\0" + p.read_bytes() + b"\0")
        return digest.hexdigest()

    return {
        "algorithms": {a: combined(paths) for a, paths in ALGORITHM_SOURCES.items()},
        "shared": {rel: (sha256_file(repo_root / rel) if (repo_root / rel).is_file() else None)
                   for rel in SHARED_SOURCES},
    }


def machine_id(snapshot: dict[str, Any]) -> str:
    """Stable identifier of the hardware/OS used; hostname is hashed, not stored."""
    parts = [
        snapshot["cpu"]["name"] or "",
        str(snapshot["cpu"]["logical_cores"]),
        str(snapshot["memory"]["total_ram_bytes"]),
        snapshot["os"]["system"],
        snapshot["os"]["release"],
        hashlib.sha256(platform.node().encode("utf-8")).hexdigest(),
    ]
    return "m_" + hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]


def snapshot(repo_root: Path, solvers: dict[str, Path], build_info: dict[str, Any] | None) -> dict[str, Any]:
    snap: dict[str, Any] = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "os": {
            "platform": platform.platform(),
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
        },
        "cpu": {
            "name": cpu_name(),
            "logical_cores": os.cpu_count(),
            "physical_cores": physical_cores(),
        },
        "memory": {"total_ram_bytes": total_ram_bytes()},
        "power_plan": power_plan(),
        "python": {"version": sys.version.split()[0], "implementation": platform.python_implementation(),
                   "executable": sys.executable},
        "python_packages": package_versions(),
        "solver_build": build_info,
        "solvers": {name: {"path": str(p), "sha256": sha256_file(p)} for name, p in solvers.items()},
        "cgal": {
            "available": (build_info or {}).get("cgal_available"),
            "version": (build_info or {}).get("cgal_version"),
            "boost_version": (build_info or {}).get("boost_version"),
            "data_structure": "CGAL::Kd_tree + CGAL::Fuzzy_iso_box (dD Spatial Searching), "
                              "exact predicate distanceSquared <= r^2 applied to the box candidates",
        },
        "git": git_snapshot(repo_root),
        "sources": source_hashes(repo_root),
    }
    snap["machine_id"] = machine_id(snap)
    return snap


def write(path: Path, snap: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snap, indent=2) + "\n", encoding="utf-8")
