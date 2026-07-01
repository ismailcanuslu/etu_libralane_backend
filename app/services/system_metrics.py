"""Host sistem metrikleri (CPU, bellek, disk, GPU, ağ)."""

from __future__ import annotations

import os
import platform
import shutil
import socket
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psutil


def _in_container() -> bool:
    return os.path.exists("/.dockerenv") or os.environ.get(
        "LIBRELANE_IN_CONTAINER", ""
    ).strip().lower() in ("1", "true", "yes")


def _use_host_namespace() -> bool:
    """docker-compose pid:host → /proc host'un; init container init'i degil."""
    if not _in_container():
        return True
    if os.environ.get("LIBRELANE_METRICS_HOST", "").strip().lower() in (
        "1",
        "true",
        "yes",
    ):
        return True
    try:
        comm = Path("/proc/1/comm").read_text(encoding="utf-8", errors="replace").strip()
        return comm not in ("docker-init", "containerd-shim", "dumb-init", "tini", "sh")
    except OSError:
        return False


def _host_run(
    argv: list[str],
    *,
    capture_output: bool = True,
    text: bool = True,
    timeout: float | None = 8,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Privileged + pid:host ortaminda host mount/PID uzerinden calistir."""
    if _in_container() and _use_host_namespace() and shutil.which("nsenter"):
        cmd = ["nsenter", "-t", "1", "-m", "-u", "-n", "-p", "-i", "--", *argv]
        return subprocess.run(
            cmd,
            capture_output=capture_output,
            text=text,
            timeout=timeout,
            check=check,
        )
    return subprocess.run(
        argv,
        capture_output=capture_output,
        text=text,
        timeout=timeout,
        check=check,
    )


def _resolve_binary(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    if _in_container() and _use_host_namespace():
        try:
            proc = _host_run(
                ["sh", "-lc", f"command -v {name} 2>/dev/null || true"],
                timeout=3,
            )
            line = (proc.stdout or "").strip().splitlines()
            if line and line[0]:
                return line[0]
        except (OSError, subprocess.SubprocessError):
            pass
    return None


def _collect_runtime() -> dict[str, Any]:
    scope = "host" if _use_host_namespace() else "container"
    if _in_container() and scope == "host":
        scope_label = "Docker (privileged, pid:host) — fiziksel sunucu"
    elif _in_container():
        scope_label = "Docker container"
    else:
        scope_label = "Yerel makine"
    return {
        "in_docker": _in_container(),
        "host_namespace": _use_host_namespace(),
        "metrics_scope": scope,
        "metrics_scope_label": scope_label,
        "privileged_hint": _in_container() and _use_host_namespace(),
    }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _bytes_human(n: int | float | None) -> str | None:
    if n is None:
        return None
    value = float(n)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{value:.1f} TiB"


def _read_memory_dmi() -> tuple[str | None, int | None]:
    """DDR tipi ve hız (MHz) — dmidecode varsa; privileged host'ta calisir."""
    if _resolve_binary("dmidecode") is None:
        return None, None
    try:
        proc = _host_run(
            ["dmidecode", "-t", "17"],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None, None
    if proc.returncode != 0 or not proc.stdout:
        return None, None

    mem_type: str | None = None
    speed_mhz: int | None = None
    for line in proc.stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith("Type:") and "Unknown" not in stripped and "No Module" not in stripped:
            part = stripped.split(":", 1)[-1].strip()
            if part:
                mem_type = part
        if stripped.startswith("Speed:") and "Unknown" not in stripped:
            part = stripped.split(":", 1)[-1].strip()
            if part.endswith("MT/s"):
                try:
                    speed_mhz = int(part.replace("MT/s", "").strip())
                except ValueError:
                    pass
            elif part.endswith("MHz"):
                try:
                    speed_mhz = int(part.replace("MHz", "").strip())
                except ValueError:
                    pass
    return mem_type, speed_mhz


def _collect_cpu() -> dict[str, Any]:
    freq = psutil.cpu_freq()
    usage = psutil.cpu_percent(interval=0.35, percpu=False)
    per_cpu_raw = psutil.cpu_percent(interval=0.0, percpu=True)
    # Bazi ortamlarda percpu=True beklenmedik sekilde tekil deger dondurebiliyor; listeye normalize et.
    if isinstance(per_cpu_raw, (int, float)):
        per_cpu = [per_cpu_raw]
    else:
        per_cpu = list(per_cpu_raw or [])
    model = platform.processor() or "Bilinmiyor"
    if not model.strip() and platform.system() == "Darwin":
        try:
            proc = _host_run(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
            if proc.stdout.strip():
                model = proc.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            pass
    return {
        "model": model,
        "physical_cores": psutil.cpu_count(logical=False),
        "logical_cores": psutil.cpu_count(logical=True),
        "usage_percent": round(float(usage), 1),
        "per_cpu_percent": [round(float(x), 1) for x in per_cpu],
        "frequency_mhz": {
            "current": round(freq.current, 0) if freq and freq.current else None,
            "min": round(freq.min, 0) if freq and freq.min else None,
            "max": round(freq.max, 0) if freq and freq.max else None,
        },
    }


def _collect_memory() -> dict[str, Any]:
    vm = psutil.virtual_memory()
    swap = psutil.swap_memory()
    mem_type, speed_mhz = _read_memory_dmi()
    return {
        "total_bytes": vm.total,
        "used_bytes": vm.used,
        "available_bytes": vm.available,
        "usage_percent": round(vm.percent, 1),
        "total_human": _bytes_human(vm.total),
        "used_human": _bytes_human(vm.used),
        "type": mem_type,
        "speed_mhz": speed_mhz,
        "swap_total_bytes": swap.total,
        "swap_used_bytes": swap.used,
        "swap_usage_percent": round(swap.percent, 1) if swap.total else 0.0,
    }


def _collect_disks() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    skip_fstype = {"squashfs", "tmpfs", "devtmpfs", "overlay", "autofs", "rpc_pipefs"}
    for part in psutil.disk_partitions(all=True):
        fst = part.fstype.lower()
        if fst in skip_fstype:
            continue
        if part.mountpoint.startswith("/proc") or part.mountpoint.startswith("/sys"):
            continue
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except (PermissionError, OSError):
            continue
        rows.append(
            {
                "device": part.device,
                "mountpoint": part.mountpoint,
                "fstype": part.fstype,
                "total_bytes": usage.total,
                "used_bytes": usage.used,
                "free_bytes": usage.free,
                "usage_percent": round(usage.percent, 1),
                "total_human": _bytes_human(usage.total),
                "used_human": _bytes_human(usage.used),
            }
        )
    return rows


def _collect_gpus() -> list[dict[str, Any]]:
    gpus: list[dict[str, Any]] = []
    nvidia = _resolve_binary("nvidia-smi")
    if nvidia:
        try:
            proc = _host_run(
                [
                    nvidia,
                    "--query-gpu=name,memory.total,memory.used,utilization.gpu,temperature.gpu",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=8,
                check=False,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                for line in proc.stdout.strip().splitlines():
                    parts = [p.strip() for p in line.split(",")]
                    if len(parts) < 4:
                        continue
                    name = parts[0]
                    try:
                        mem_total_mib = float(parts[1])
                        mem_used_mib = float(parts[2])
                        util = float(parts[3])
                    except ValueError:
                        continue
                    temp = None
                    if len(parts) >= 5 and parts[4] not in ("", "N/A", "[N/A]"):
                        try:
                            temp = float(parts[4])
                        except ValueError:
                            pass
                    gpus.append(
                        {
                            "name": name,
                            "vendor": "NVIDIA",
                            "memory_total_bytes": int(mem_total_mib * 1024 * 1024),
                            "memory_used_bytes": int(mem_used_mib * 1024 * 1024),
                            "memory_total_human": f"{mem_total_mib:.0f} MiB",
                            "memory_used_human": f"{mem_used_mib:.0f} MiB",
                            "utilization_percent": round(util, 1),
                            "temperature_c": temp,
                        }
                    )
                return gpus
        except (OSError, subprocess.SubprocessError):
            pass

    if platform.system() == "Darwin":
        try:
            proc = subprocess.run(
                ["system_profiler", "SPDisplaysDataType"],
                capture_output=True,
                text=True,
                timeout=12,
                check=False,
            )
            if proc.returncode == 0:
                name: str | None = None
                for line in proc.stdout.splitlines():
                    if "Chipset Model:" in line:
                        name = line.split(":", 1)[-1].strip()
                        if name:
                            gpus.append({"name": name, "vendor": "Apple", "utilization_percent": None})
                            name = None
        except (OSError, subprocess.SubprocessError):
            pass
    return gpus


def _collect_network() -> dict[str, Any]:
    addrs = psutil.net_if_addrs()
    stats = psutil.net_if_stats()
    io = psutil.net_io_counters(pernic=False)
    pernic = psutil.net_io_counters(pernic=True)

    interfaces: list[dict[str, Any]] = []
    for name, addr_list in addrs.items():
        if name == "lo":
            continue
        st = stats.get(name)
        addresses: list[dict[str, str]] = []
        for addr in addr_list:
            if addr.family.name in ("AF_INET", "AF_INET6"):
                addresses.append(
                    {
                        "family": "IPv4" if addr.family.name == "AF_INET" else "IPv6",
                        "address": addr.address,
                    }
                )
        iface_io = pernic.get(name) if pernic else None
        interfaces.append(
            {
                "name": name,
                "is_up": bool(st.isup) if st else None,
                "speed_mbps": st.speed if st and st.speed > 0 else None,
                "addresses": addresses,
                "io": {
                    "bytes_sent": iface_io.bytes_sent if iface_io else 0,
                    "bytes_recv": iface_io.bytes_recv if iface_io else 0,
                    "bytes_sent_human": _bytes_human(iface_io.bytes_sent if iface_io else 0),
                    "bytes_recv_human": _bytes_human(iface_io.bytes_recv if iface_io else 0),
                },
            }
        )

    return {
        "hostname": socket.gethostname(),
        "interfaces": interfaces,
        "total_io": {
            "bytes_sent": io.bytes_sent if io else 0,
            "bytes_recv": io.bytes_recv if io else 0,
            "packets_sent": io.packets_sent if io else 0,
            "packets_recv": io.packets_recv if io else 0,
            "bytes_sent_human": _bytes_human(io.bytes_sent if io else 0),
            "bytes_recv_human": _bytes_human(io.bytes_recv if io else 0),
        },
    }


def collect_system_metrics() -> dict[str, Any]:
    """Tek çağrıda güncel metrikler (pid:host + privileged → fiziksel sunucu)."""
    boot = psutil.boot_time()
    return {
        "collected_at": _now_iso(),
        "hostname": socket.gethostname(),
        "runtime": _collect_runtime(),
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        },
        "uptime_seconds": int(time.time() - boot),
        "cpu": _collect_cpu(),
        "memory": _collect_memory(),
        "disks": _collect_disks(),
        "gpus": _collect_gpus(),
        "network": _collect_network(),
    }
