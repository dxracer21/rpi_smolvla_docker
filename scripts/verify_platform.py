#!/usr/bin/env python3
import json
import os
import platform
from pathlib import Path


def read_text(path: str) -> str:
    try:
        return Path(path).read_text().strip()
    except (FileNotFoundError, PermissionError):
        return "unavailable"


result = {
    "machine": platform.machine(),
    "platform": platform.platform(),
    "python": platform.python_version(),
    "cpu_count_visible": os.cpu_count(),
    "memory_limit_bytes": read_text("/sys/fs/cgroup/memory.max"),
    "cpu_limit": read_text("/sys/fs/cgroup/cpu.max"),
}

print(json.dumps(result, indent=2))

if platform.machine() not in {"aarch64", "arm64"}:
    raise SystemExit("ERROR: container is not running as ARM64")

print("PASS: Linux ARM64 base container is ready.")

