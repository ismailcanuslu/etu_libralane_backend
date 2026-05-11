from __future__ import annotations

import hashlib
import mimetypes
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO, Iterable, Iterator, List, Tuple

from app.core.workspace_paths import (
    WorkspacePathError,
    object_path,
    project_dir,
    validate_object_key,
    workspace_root,
)


@dataclass(frozen=True)
class ObjectInfo:
    key: str
    size: int
    etag: str
    last_modified: datetime
    content_type: str | None = None


@dataclass(frozen=True)
class ProjectInfo:
    name: str
    created_at: datetime


def _etag_for_file(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f'"{digest.hexdigest()}"'


def _stat_object(project_id: str, key: str) -> ObjectInfo:
    path = object_path(project_id, key)
    if not path.is_file():
        raise FileNotFoundError(key)
    stat = path.stat()
    content_type, _ = mimetypes.guess_type(path.name)
    return ObjectInfo(
        key=validate_object_key(key),
        size=stat.st_size,
        etag=_etag_for_file(path),
        last_modified=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
        content_type=content_type or "application/octet-stream",
    )


def ensure_project(project_id: str) -> None:
    project_dir(project_id, create=True)


def ensure_bucket(bucket: str) -> None:
    ensure_project(bucket)


def list_projects() -> List[ProjectInfo]:
    root = workspace_root()
    projects: List[ProjectInfo] = []
    for entry in sorted(root.iterdir(), key=lambda p: p.name):
        if not entry.is_dir():
            continue
        stat = entry.stat()
        projects.append(
            ProjectInfo(
                name=entry.name,
                created_at=datetime.fromtimestamp(stat.st_ctime, tz=timezone.utc),
            )
        )
    return projects


def list_objects(
    project_id: str,
    prefix: str = "",
    *,
    recursive: bool = True,
    exclude_prefixes: Iterable[str] = (),
) -> List[ObjectInfo]:
    base = project_dir(project_id)
    if not base.exists():
        return []

    normalized_prefix = validate_object_key(prefix) if prefix else ""
    excludes: Tuple[str, ...] = tuple(exclude_prefixes)
    objects: List[ObjectInfo] = []

    if recursive:
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(base).as_posix()
            if normalized_prefix and not rel.startswith(normalized_prefix):
                continue
            if any(rel.startswith(p) for p in excludes):
                continue
            stat = path.stat()
            content_type, _ = mimetypes.guess_type(path.name)
            objects.append(
                ObjectInfo(
                    key=rel,
                    size=stat.st_size,
                    etag=_etag_for_file(path),
                    last_modified=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                    content_type=content_type or "application/octet-stream",
                )
            )
        return objects

    scan_dir = base / normalized_prefix if normalized_prefix else base
    if normalized_prefix and not scan_dir.exists():
        return []
    if not scan_dir.is_dir():
        return []

    for path in sorted(scan_dir.iterdir(), key=lambda p: p.name):
        rel = path.relative_to(base).as_posix()
        if any(rel.startswith(p) for p in excludes):
            continue
        if path.is_file():
            stat = path.stat()
            content_type, _ = mimetypes.guess_type(path.name)
            objects.append(
                ObjectInfo(
                    key=rel,
                    size=stat.st_size,
                    etag=_etag_for_file(path),
                    last_modified=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                    content_type=content_type or "application/octet-stream",
                )
            )
    return objects


def read_bytes(project_id: str, key: str) -> bytes:
    path = object_path(project_id, key)
    if not path.is_file():
        raise FileNotFoundError(key)
    return path.read_bytes()


def write_bytes(
    project_id: str,
    key: str,
    data: bytes,
    content_type: str = "application/octet-stream",
) -> ObjectInfo:
    del content_type  # preserved for API compatibility; mime is inferred from key on read
    ensure_project(project_id)
    path = object_path(project_id, key, create_parent=True)
    path.write_bytes(data)
    return _stat_object(project_id, key)


def delete_object(project_id: str, key: str) -> None:
    path = object_path(project_id, key)
    if path.is_file():
        path.unlink()
        return
    if path.exists():
        raise IsADirectoryError(key)
    raise FileNotFoundError(key)


def delete_prefix(project_id: str, prefix: str) -> None:
    base = project_dir(project_id)
    normalized_prefix = validate_object_key(prefix) if prefix else ""
    target = (base / normalized_prefix).resolve() if normalized_prefix else base
    if not target.exists():
        return
    if target.is_file():
        target.unlink()
        return
    shutil.rmtree(target)


def delete_project(project_id: str) -> None:
    delete_prefix(project_id, "")


def copy_project_to_dir(
    project_id: str,
    prefix: str,
    dst_dir: str,
    exclude_prefixes: Iterable[str] = (),
) -> List[str]:
    base = project_dir(project_id)
    if not base.exists():
        return []

    normalized_prefix = validate_object_key(prefix) if prefix else ""
    excludes: Tuple[str, ...] = tuple(exclude_prefixes)
    written: List[str] = []
    for info in list_objects(project_id, normalized_prefix, recursive=True, exclude_prefixes=excludes):
        src = object_path(project_id, info.key)
        rel = info.key[len(normalized_prefix) :] if normalized_prefix else info.key
        rel = rel.lstrip("/")
        if not rel:
            continue
        dst_path = os.path.join(dst_dir, rel)
        os.makedirs(os.path.dirname(dst_path) or dst_dir, exist_ok=True)
        shutil.copy2(src, dst_path)
        written.append(dst_path)
    return written


def download_prefix(
    bucket: str,
    prefix: str,
    dst_dir: str,
    exclude_prefixes: Iterable[str] = (),
) -> List[str]:
    return copy_project_to_dir(bucket, prefix, dst_dir, exclude_prefixes=exclude_prefixes)


def upload_file(
    bucket: str,
    key: str,
    src_path: str,
    content_type: str = "application/octet-stream",
) -> str:
    ensure_project(bucket)
    data = Path(src_path).read_bytes()
    write_bytes(bucket, key, data, content_type=content_type)
    return key


def copy_dir_to_project(
    project_id: str,
    key_prefix: str,
    src_dir: str,
    exclude_names: Iterable[str] = (),
) -> List[str]:
    ensure_project(project_id)
    excludes = set(exclude_names)
    uploaded: List[str] = []
    src_root = os.path.abspath(src_dir)
    for root, _dirs, files in os.walk(src_root):
        for name in files:
            if name in excludes:
                continue
            full = os.path.join(root, name)
            rel = os.path.relpath(full, src_root).replace(os.sep, "/")
            key = f"{key_prefix.rstrip('/')}/{rel}"
            upload_file(project_id, key, full)
            uploaded.append(key)
    return uploaded


def upload_dir(
    bucket: str,
    key_prefix: str,
    src_dir: str,
    exclude_names: Iterable[str] = (),
) -> List[str]:
    return copy_dir_to_project(bucket, key_prefix, src_dir, exclude_names=exclude_names)


def get_object_text(project_id: str, key: str) -> str:
    return read_bytes(project_id, key).decode("utf-8", errors="replace")


def open_for_stream(project_id: str, key: str) -> BinaryIO:
    path = object_path(project_id, key)
    if not path.is_file():
        raise FileNotFoundError(key)
    return path.open("rb")


def stream_object(bucket: str, key: str) -> BinaryIO:
    return open_for_stream(bucket, key)


def iter_object_chunks(project_id: str, key: str, chunk_size: int = 64 * 1024) -> Iterator[bytes]:
    with open_for_stream(project_id, key) as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            yield chunk


def stat_object(project_id: str, key: str) -> ObjectInfo:
    return _stat_object(project_id, key)


def serialize_object(info: ObjectInfo) -> dict:
    return {
        "key": info.key,
        "size": info.size,
        "etag": info.etag,
        "lastModified": info.last_modified.isoformat(),
        "contentType": info.content_type,
    }


def serialize_project(info: ProjectInfo) -> dict:
    return {
        "name": info.name,
        "createdAt": info.created_at.isoformat(),
    }


__all__ = [
    "ObjectInfo",
    "ProjectInfo",
    "WorkspacePathError",
    "copy_dir_to_project",
    "copy_project_to_dir",
    "delete_object",
    "delete_prefix",
    "delete_project",
    "download_prefix",
    "ensure_bucket",
    "ensure_project",
    "get_object_text",
    "iter_object_chunks",
    "list_objects",
    "list_projects",
    "open_for_stream",
    "read_bytes",
    "serialize_object",
    "serialize_project",
    "stat_object",
    "stream_object",
    "upload_dir",
    "upload_file",
    "write_bytes",
]
