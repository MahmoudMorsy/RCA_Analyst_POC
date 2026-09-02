from __future__ import annotations

import os
import platform
import shutil
import socket
import subprocess
from pathlib import Path
from typing import Any, Optional

import psutil


def _gpus() -> list[dict[str, Any]]:
    exe = shutil.which("nvidia-smi")
    if not exe:
        return []
    query = "name,memory.total,memory.used,utilization.gpu,temperature.gpu,power.draw"
    try:
        cp = subprocess.run(
            [exe, f"--query-gpu={query}", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        if cp.returncode != 0:
            return []
        rows = []
        for raw in cp.stdout.splitlines():
            cols = [x.strip() for x in raw.split(",")]
            if len(cols) < 6:
                continue
            def num(v):
                try: return float(v)
                except Exception: return None
            rows.append({
                "name": cols[0],
                "vram_total_mb": num(cols[1]),
                "vram_used_mb": num(cols[2]),
                "utilization_percent": num(cols[3]),
                "temperature_c": num(cols[4]),
                "power_w": num(cols[5]),
            })
        return rows
    except Exception:
        return []


class SystemInfoService:
    def snapshot(self, storage_root: Optional[Path] = None) -> dict[str, Any]:
        vm = psutil.virtual_memory()
        disk_path = storage_root if storage_root and storage_root.exists() else Path.cwd()
        try:
            disk = psutil.disk_usage(str(disk_path))
            disk_info = {"total_gb": round(disk.total / 2**30, 2), "used_gb": round(disk.used / 2**30, 2), "percent": disk.percent}
        except Exception:
            disk_info = {}
        gpus = _gpus()
        return {
            "hostname": socket.gethostname(),
            "os": platform.platform(),
            "python": platform.python_version(),
            "cpu": platform.processor() or platform.machine(),
            "cpu_count_logical": psutil.cpu_count(logical=True),
            "cpu_count_physical": psutil.cpu_count(logical=False),
            "cpu_utilization_percent": psutil.cpu_percent(interval=None),
            "ram_total_gb": round(vm.total / 2**30, 2),
            "ram_used_gb": round(vm.used / 2**30, 2),
            "ram_percent": vm.percent,
            "gpus": gpus,
            "gpu_count": len(gpus),
            "disk": disk_info,
        }
