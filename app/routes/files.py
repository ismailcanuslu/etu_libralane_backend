from __future__ import annotations

import mimetypes

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.core import storage
from app.core.workspace_paths import WorkspacePathError

router = APIRouter(prefix="/files", tags=["files"])


def _error(message: str, status_code: int) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": message})


@router.get("")
def list_projects():
    projects = storage.list_projects()
    serialized = [storage.serialize_project(project) for project in projects]
    return {
        "count": len(serialized),
        "projects": serialized,
    }


@router.post("/{project_id}")
def create_project(project_id: str):
    try:
        storage.ensure_project(project_id)
    except WorkspacePathError as exc:
        return _error(str(exc), 400)
    except OSError as exc:
        return _error(str(exc), 502)
    return JSONResponse(
        status_code=201,
        content={"project": project_id, "status": "ready"},
    )


@router.delete("/{project_id}")
def delete_project(project_id: str):
    try:
        storage.delete_project(project_id)
    except WorkspacePathError as exc:
        return _error(str(exc), 400)
    except OSError as exc:
        return _error(str(exc), 502)
    return {"project": project_id, "status": "deleted"}


@router.get("/{project_id}/objects")
def list_project_objects(project_id: str, request: Request):
    prefix = request.query_params.get("prefix", "")
    recursive = request.query_params.get("recursive", "true") != "false"
    try:
        objects = storage.list_objects(project_id, prefix, recursive=recursive)
    except WorkspacePathError as exc:
        return _error(str(exc), 400)
    except OSError as exc:
        return _error(str(exc), 502)

    serialized = [storage.serialize_object(obj) for obj in objects]
    return {
        "project": project_id,
        "prefix": prefix,
        "recursive": recursive,
        "count": len(serialized),
        "objects": serialized,
    }


@router.put("/{project_id}/objects/{key:path}")
async def put_project_object(project_id: str, key: str, request: Request):
    if not key:
        return _error("object key is required", 400)

    content_type = request.headers.get("content-type") or "application/octet-stream"
    if content_type == "application/octet-stream":
        guessed, _ = mimetypes.guess_type(key)
        if guessed:
            content_type = guessed

    try:
        data = await request.body()
        info = storage.write_bytes(project_id, key, data, content_type=content_type)
    except WorkspacePathError as exc:
        return _error(str(exc), 400)
    except OSError as exc:
        return _error(str(exc), 502)

    return JSONResponse(
        status_code=201,
        content={
            "project": project_id,
            "key": info.key,
            "etag": info.etag,
            "size": info.size,
            "contentType": info.content_type,
        },
    )


@router.get("/{project_id}/objects/{key:path}")
def get_project_object(project_id: str, key: str):
    if not key:
        return _error("object key is required", 400)
    try:
        info = storage.stat_object(project_id, key)
    except WorkspacePathError as exc:
        return _error(str(exc), 400)
    except FileNotFoundError as exc:
        return _error(str(exc), 404)
    except OSError as exc:
        return _error(str(exc), 502)

    headers = {
        "Content-Length": str(info.size),
        "ETag": info.etag,
        "Last-Modified": info.last_modified.strftime("%a, %d %b %Y %H:%M:%S GMT"),
    }
    if info.content_type:
        headers["Content-Type"] = info.content_type
    else:
        headers["Content-Type"] = "application/octet-stream"

    return StreamingResponse(
        storage.iter_object_chunks(project_id, key),
        media_type=headers["Content-Type"],
        headers=headers,
    )


@router.delete("/{project_id}/objects/{key:path}")
def delete_project_object(project_id: str, key: str):
    if not key:
        return _error("object key is required", 400)
    try:
        storage.delete_object(project_id, key)
    except WorkspacePathError as exc:
        return _error(str(exc), 400)
    except FileNotFoundError as exc:
        return _error(str(exc), 404)
    except OSError as exc:
        return _error(str(exc), 502)
    return {"project": project_id, "key": key, "status": "deleted"}


@router.get("/{project_id}/meta/{key:path}")
def get_project_object_meta(project_id: str, key: str):
    if not key:
        return _error("object key is required", 400)
    try:
        info = storage.stat_object(project_id, key)
    except WorkspacePathError as exc:
        return _error(str(exc), 400)
    except FileNotFoundError as exc:
        return _error(str(exc), 404)
    except OSError as exc:
        return _error(str(exc), 502)
    return storage.serialize_object(info)
