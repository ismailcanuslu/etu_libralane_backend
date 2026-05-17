"""SkyWater 130 / OpenLane PDK yol bilgisi (UI ve önizleme)."""

from __future__ import annotations

import os
from pathlib import Path

from app.core.config import get_settings


def get_pdk_runtime_info() -> dict:
    settings = get_settings()
    host = (settings.openlane_pdk_host_path or "").strip()
    mount = settings.openlane_pdk_mount_path or "/openlane/pdk"

    if host:
        path = Path(host).expanduser()
        exists = path.is_dir()
        return {
            "pdk_family": "sky130",
            "source": "host_mount",
            "host_path": str(path.resolve()) if exists else host,
            "container_path": mount,
            "available": exists,
            "message": (
                "Host PDK mount edilecek."
                if exists
                else f"OPENLANE_PDK_HOST_PATH klasörü bulunamadı: {host}"
            ),
        }

    return {
        "pdk_family": "sky130",
        "source": "runner_image",
        "host_path": None,
        "container_path": mount,
        "available": True,
        "message": (
            "PDK runner imajı içinde (efabless/openlane). "
            f"Container içi yol: {mount}"
        ),
    }


def pdk_display_path() -> str:
    info = get_pdk_runtime_info()
    if info.get("host_path"):
        return str(info["host_path"])
    return str(info.get("container_path") or "/openlane/pdk")
