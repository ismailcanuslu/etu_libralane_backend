"""GDS layout önizleme — tarayıcı için ham bytes, KLayout için PNG render."""

from __future__ import annotations

import asyncio
import hashlib
import os
import subprocess
from pathlib import Path

from app.core.config import get_settings
from app.core import storage
from app.core.workspace_paths import object_path, project_dir, validate_object_key

_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "klayout_export_png.rb"

# 1440p (QHD) — sunucu KLayout PNG önizleme varsayılanı
KLAYOUT_DEFAULT_WIDTH = 2560
KLAYOUT_DEFAULT_HEIGHT = 1440
FLOW_LAYOUT_PNG_NAME = "layout_klayout_1440p.png"


def _preview_cache_path(project_id: str, key: str) -> Path:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    return project_dir(project_id, create=True) / "_layout_preview" / f"{digest}.png"


def read_gds_bytes(project_id: str, key: str) -> bytes:
    validate_object_key(key)
    return storage.read_bytes(project_id, key)


def klayout_available() -> bool:
    settings = get_settings()
    try:
        result = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                settings.runner_image_openlane,
                "bash",
                "-lc",
                "command -v klayout >/dev/null 2>&1",
            ],
            capture_output=True,
            timeout=120,
            check=False,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _render_klayout_png_sync(project_id: str, key: str, width: int, height: int) -> bytes:
    validate_object_key(key)
    gds_path = object_path(project_id, key)
    if not gds_path.is_file():
        raise FileNotFoundError(key)

    settings = get_settings()
    out_path = _preview_cache_path(project_id, key)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.is_file() and out_path.stat().st_mtime >= gds_path.stat().st_mtime:
        return out_path.read_bytes()

    host_root = str(project_dir(project_id).resolve())
    rel_gds = key.replace("\\", "/")
    rel_out = out_path.relative_to(project_dir(project_id)).as_posix()

    cmd = [
        "docker",
        "run",
        "--rm",
        "--platform",
        os.environ.get("OPENLANE1_PLATFORM", "linux/amd64"),
        "-v",
        f"{host_root}:/work",
        "-v",
        f"{_SCRIPT_PATH.resolve()}:/scripts/klayout_export_png.rb:ro",
        "-w",
        "/work",
        settings.runner_image_openlane,
        "klayout",
        "-zz",
        "-b",
        "-r",
        "/scripts/klayout_export_png.rb",
        f"-rd-input=/work/{rel_gds}",
        f"-rd-output=/work/{rel_out}",
        f"-rd-width={width}",
        f"-rd-height={height}",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "klayout failed").strip()
        raise RuntimeError(detail[:500])

    if not out_path.is_file():
        raise RuntimeError("KLayout PNG üretilmedi")
    return out_path.read_bytes()


async def render_klayout_png(
    project_id: str,
    key: str,
    *,
    width: int = KLAYOUT_DEFAULT_WIDTH,
    height: int = KLAYOUT_DEFAULT_HEIGHT,
) -> bytes:
    return await asyncio.to_thread(_render_klayout_png_sync, project_id, key, width, height)


def find_first_gds_in_tree(root: Path) -> Path | None:
    if not root.is_dir():
        return None
    gds_files = sorted(root.rglob("*.gds")) + sorted(root.rglob("*.gdsii"))
    return gds_files[0] if gds_files else None


def job_layout_png_object_key(job_id: str) -> str:
    settings = get_settings()
    return f"{settings.jobs_artifacts_prefix}/{job_id}/{FLOW_LAYOUT_PNG_NAME}"


async def generate_flow_layout_png_preview(
    project_id: str,
    *,
    job_id: str,
    workdir: str,
    uploaded_artifacts_prefix: str | None,
) -> str | None:
    """
    OpenLane Flow bittikten sonra ilk GDS için KLayout PNG üretir ve job artefaktına yazar.
    Dönüş: workspace object key veya None.
    """
    if not uploaded_artifacts_prefix:
        return None
    gds_path = find_first_gds_in_tree(Path(workdir))
    if gds_path is None:
        return None
    rel = gds_path.relative_to(Path(workdir)).as_posix()
    workspace_gds_key = f"{uploaded_artifacts_prefix}/{rel}"
    try:
        png_bytes = await render_klayout_png(project_id, workspace_gds_key)
        png_key = job_layout_png_object_key(job_id)
        storage.write_bytes(project_id, png_key, png_bytes, content_type="image/png")
        return png_key
    except (OSError, RuntimeError, FileNotFoundError):
        return None
