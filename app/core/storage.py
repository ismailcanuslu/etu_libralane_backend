import os
from functools import lru_cache
from typing import Iterable, List, Tuple

from minio import Minio
from minio.error import S3Error

from app.core.config import get_settings


@lru_cache(maxsize=1)
def get_client() -> Minio:
    s = get_settings()
    return Minio(
        s.minio_endpoint,
        access_key=s.minio_root_user,
        secret_key=s.minio_root_password,
        secure=s.minio_secure,
    )


def ensure_bucket(bucket: str) -> None:
    client = get_client()
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)


def download_prefix(
    bucket: str,
    prefix: str,
    dst_dir: str,
    exclude_prefixes: Iterable[str] = (),
) -> List[str]:
    """Bir bucket altındaki (prefix dahil) tüm objeleri dst_dir altına kopyalar.

    Bucket yoksa boş liste döner. exclude_prefixes ile başlayan key'ler atlanır.
    """
    client = get_client()
    if not client.bucket_exists(bucket):
        return []

    written: List[str] = []
    excludes: Tuple[str, ...] = tuple(exclude_prefixes)
    for obj in client.list_objects(bucket, prefix=prefix or None, recursive=True):
        key = obj.object_name
        if not key:
            continue
        if any(key.startswith(p) for p in excludes):
            continue
        rel = key[len(prefix):] if prefix else key
        rel = rel.lstrip("/")
        if not rel:
            continue
        dst_path = os.path.join(dst_dir, rel)
        os.makedirs(os.path.dirname(dst_path) or dst_dir, exist_ok=True)
        try:
            client.fget_object(bucket, key, dst_path)
            written.append(dst_path)
        except S3Error:
            continue
    return written


def upload_file(bucket: str, key: str, src_path: str, content_type: str = "application/octet-stream") -> str:
    ensure_bucket(bucket)
    client = get_client()
    client.fput_object(bucket, key, src_path, content_type=content_type)
    return key


def upload_dir(bucket: str, key_prefix: str, src_dir: str, exclude_names: Iterable[str] = ()) -> List[str]:
    """src_dir altındaki tüm dosyaları bucket altında key_prefix'e yükler."""
    ensure_bucket(bucket)
    client = get_client()
    excludes = set(exclude_names)
    uploaded: List[str] = []
    src_dir = os.path.abspath(src_dir)
    for root, _dirs, files in os.walk(src_dir):
        for name in files:
            if name in excludes:
                continue
            full = os.path.join(root, name)
            rel = os.path.relpath(full, src_dir).replace(os.sep, "/")
            key = f"{key_prefix.rstrip('/')}/{rel}"
            try:
                client.fput_object(bucket, key, full)
                uploaded.append(key)
            except S3Error:
                continue
    return uploaded


def get_object_text(bucket: str, key: str) -> str:
    client = get_client()
    response = client.get_object(bucket, key)
    try:
        return response.read().decode("utf-8", errors="replace")
    finally:
        response.close()
        response.release_conn()


def stream_object(bucket: str, key: str):
    """Tarayıcıya stream'lemek için byte chunk iterator döner.

    Kullanım: response.close() / release_conn() ile kapatılmalı.
    """
    return get_client().get_object(bucket, key)
