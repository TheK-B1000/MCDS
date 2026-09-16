"""Shared helpers for experiment laboratory upgrades (hashing, provenance, I/O)."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def sha256_file(path: Path, chunk_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonicalize_config(config: dict[str, Any]) -> str:
    """Stable JSON for config hashing (sorted keys, no whitespace variance)."""
    return json.dumps(config, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def config_sha256(config: dict[str, Any]) -> str:
    return sha256_bytes(canonicalize_config(config).encode("utf-8"))


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, ensure_ascii=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def git_info(repo_root: Path) -> dict[str, Any]:
    info: dict[str, Any] = {"commit": None, "dirty": None, "branch": None}
    try:
        info["commit"] = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(repo_root), text=True, stderr=subprocess.DEVNULL
        ).strip()
        status = subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=str(repo_root), text=True, stderr=subprocess.DEVNULL
        )
        info["dirty"] = bool(status.strip())
        info["branch"] = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(repo_root),
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:  # noqa: BLE001
        pass
    return info


def detect_build_type(executable: Path) -> str:
    """Best-effort Release/Debug guess from path/name."""
    text = str(executable).lower()
    if "debug" in text:
        return "Debug"
    if "release" in text:
        return "Release"
    # MinGW single-config builds default to Release in our CMakeLists.
    return "unknown"


def machine_provenance(repo_root: Path, executable: Path) -> dict[str, Any]:
    total_ram_mb = None
    try:
        if platform.system() == "Windows":
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                total_ram_mb = round(stat.ullTotalPhys / (1024.0 * 1024.0), 1)
        else:
            pages = os.sysconf("SC_PHYS_PAGES")
            page_size = os.sysconf("SC_PAGE_SIZE")
            total_ram_mb = round(pages * page_size / (1024.0 * 1024.0), 1)
    except Exception:  # noqa: BLE001
        total_ram_mb = None

    exe_hash = None
    try:
        exe_hash = sha256_file(executable)
    except OSError:
        pass

    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "os": platform.platform(),
        "cpu": platform.processor() or platform.machine(),
        "total_ram_mb": total_ram_mb,
        "python_version": sys.version.split()[0],
        "python_executable": sys.executable,
        "solver_path": str(executable),
        "solver_sha256": exe_hash,
        "build_type": detect_build_type(executable),
        "compiler": "unknown",
        "compiler_version": "unknown",
        "git": git_info(repo_root),
    }


def log_line(msg: str, *, progress: bool, verbose: bool = True) -> None:
    """Write a line without breaking an active tqdm bar when progress is on."""
    if not verbose and progress:
        return
    if progress:
        try:
            from tqdm import tqdm

            tqdm.write(msg)
            return
        except Exception:  # noqa: BLE001
            pass
    print(msg)
