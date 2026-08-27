"""Lightweight Raspberry Pi resource metrics for the local UI."""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Any


class SystemMetrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._previous: tuple[float, int, int, int] | None = None
        self._session_id: int | None = None
        self._run_cpu_total = 0.0
        self._run_cpu_samples = 0
        self._run_cpu_peak: float | None = None
        self._run_memory_peak_gib: float | None = None
        self._run_temperature_peak: float | None = None

    def snapshot(self, inference_active: bool = False, session_id: int | None = None) -> dict[str, Any]:
        now = time.monotonic()
        total_ticks, idle_ticks = self._system_cpu_ticks()
        process_ticks = self._process_cpu_ticks()
        memory = self._memory()

        with self._lock:
            pi_cpu = None
            process_cpu = None
            if self._previous is not None:
                previous_time, previous_total, previous_idle, previous_process = self._previous
                total_delta = total_ticks - previous_total
                elapsed = now - previous_time
                if total_delta > 0:
                    pi_cpu = 100.0 * (1.0 - (idle_ticks - previous_idle) / total_delta)
                if elapsed > 0:
                    ticks_per_second = os.sysconf("SC_CLK_TCK")
                    cores = os.cpu_count() or 1
                    process_cpu = 100.0 * (process_ticks - previous_process) / ticks_per_second / elapsed / cores
            self._previous = (now, total_ticks, idle_ticks, process_ticks)

            if session_id != self._session_id:
                self._session_id = session_id
                self._run_cpu_total = 0.0
                self._run_cpu_samples = 0
                self._run_cpu_peak = None
                self._run_memory_peak_gib = None
                self._run_temperature_peak = None

            temperature = self._temperature_celsius()
            if inference_active:
                if process_cpu is not None:
                    self._run_cpu_total += process_cpu
                    self._run_cpu_samples += 1
                if pi_cpu is not None:
                    self._run_cpu_peak = max(self._run_cpu_peak or pi_cpu, pi_cpu)
                self._run_memory_peak_gib = max(
                    self._run_memory_peak_gib or memory["used_gib"],
                    memory["used_gib"],
                )
                if temperature is not None:
                    self._run_temperature_peak = max(self._run_temperature_peak or temperature, temperature)

            run_cpu_average = (
                self._run_cpu_total / self._run_cpu_samples
                if self._run_cpu_samples
                else None
            )

        memory["run_peak_used_gib"] = self._run_memory_peak_gib
        memory["run_peak_percent"] = (
            self._percent(100 * self._run_memory_peak_gib / memory["total_gib"])
            if self._run_memory_peak_gib is not None
            else None
        )
        return {
            "cpu": {
                "pi_percent": self._percent(pi_cpu),
                "smolvla_percent": self._percent(process_cpu),
                "run_average_percent": self._percent(run_cpu_average),
                "run_peak_percent": self._percent(self._run_cpu_peak),
                "cores": os.cpu_count() or 1,
            },
            "memory": memory,
            "temperature": {
                "current_c": temperature,
                "run_peak_c": self._run_temperature_peak,
                "status": self._temperature_status(temperature),
            },
        }

    @staticmethod
    def _system_cpu_ticks() -> tuple[int, int]:
        fields = Path("/proc/stat").read_text().splitlines()[0].split()[1:]
        ticks = [int(value) for value in fields]
        total = sum(ticks)
        idle = ticks[3] + (ticks[4] if len(ticks) > 4 else 0)
        return total, idle

    @staticmethod
    def _process_cpu_ticks() -> int:
        fields = Path("/proc/self/stat").read_text().split()
        return int(fields[13]) + int(fields[14])

    @staticmethod
    def _memory() -> dict[str, float]:
        values: dict[str, int] = {}
        for line in Path("/proc/meminfo").read_text().splitlines():
            key, value = line.split(":", 1)
            values[key] = int(value.strip().split()[0]) * 1024

        total = values["MemTotal"]
        available = values.get("MemAvailable", values.get("MemFree", 0))
        used = max(total - available, 0)
        rss = 0
        for line in Path("/proc/self/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                rss = int(line.split()[1]) * 1024
                break

        gib = 1024 ** 3
        return {
            "total_gib": round(total / gib, 3),
            "used_gib": round(used / gib, 3),
            "available_gib": round(available / gib, 3),
            "smolvla_rss_gib": round(rss / gib, 3),
            "used_percent": round(100 * used / total, 1),
            "smolvla_percent": round(100 * rss / total, 1),
        }

    @staticmethod
    def _temperature_celsius() -> float | None:
        for path in (Path("/host_cpu_temp"), Path("/sys/class/thermal/thermal_zone0/temp")):
            try:
                value = float(path.read_text().strip())
                return round(value / 1000 if value > 200 else value, 1)
            except (OSError, ValueError):
                continue
        return None

    @staticmethod
    def _temperature_status(temperature: float | None) -> str:
        if temperature is None:
            return "UNAVAILABLE"
        if temperature >= 80:
            return "THROTTLING RISK"
        if temperature >= 70:
            return "WARM"
        return "NORMAL"

    @staticmethod
    def _percent(value: float | None) -> float | None:
        return None if value is None else round(min(max(value, 0.0), 100.0), 1)
