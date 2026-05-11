"""Workspace path contract and traversal guards.

Layout:
  {WORKSPACE_ROOT}/{project_id}/...           project sources
  {WORKSPACE_ROOT}/{project_id}/_jobs/...     job logs and artifacts
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from app.core.config import get_settings

PROJECT_ID_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


class WorkspacePathError(ValueError):
    pass


def workspace_root() -> Path:
    root = Path(get_settings().workspace_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def validate_project_id(project_id: str) -> str:
    project_id = (project_id or "").strip()
    if not project_id or "\x00" in project_id:
        raise WorkspacePathError("invalid project_id")
    if "/" in project_id or "\\" in project_id or ".." in project_id:
        raise WorkspacePathError("invalid project_id")
    if not PROJECT_ID_RE.match(project_id):
        raise WorkspacePathError("invalid project_id")
    return project_id


def validate_object_key(key: str) -> str:
    if key is None:
        raise WorkspacePathError("object key is required")
    normalized = key.replace("\\", "/").lstrip("/")
    if not normalized or "\x00" in normalized:
        raise WorkspacePathError("invalid object key")
    if normalized.startswith("..") or "/../" in f"/{normalized}/":
        raise WorkspacePathError("invalid object key")
    for part in normalized.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            raise WorkspacePathError("invalid object key")
    return normalized


def _is_within(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def project_dir(project_id: str, *, create: bool = False) -> Path:
    project_id = validate_project_id(project_id)
    root = workspace_root()
    path = (root / project_id).resolve()
    if not _is_within(path, root):
        raise WorkspacePathError("path escapes workspace")
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def object_path(project_id: str, key: str, *, create_parent: bool = False) -> Path:
    key = validate_object_key(key)
    base = project_dir(project_id)
    path = (base / key).resolve()
    if not _is_within(path, base):
        raise WorkspacePathError("path escapes project")
    if create_parent:
        path.parent.mkdir(parents=True, exist_ok=True)
    return path
