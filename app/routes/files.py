from __future__ import annotations

import mimetypes
from typing import Literal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.core import storage
from app.core.workspace_paths import WorkspacePathError

router = APIRouter(prefix="/files", tags=["files"])

ProjectTemplate = Literal["caravel", "verilog"]


class CreateProjectRequest(BaseModel):
    name: str = Field(min_length=1)
    template: ProjectTemplate = "caravel"


def _error(message: str, status_code: int) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": message})


def _normalize_template(template: str) -> str:
    return template if template == "verilog" else "caravel"


def _create_project(project_id: str, template: str = "caravel") -> JSONResponse:
    try:
        storage.ensure_project(project_id, template=_normalize_template(template))
    except WorkspacePathError as exc:
        return _error(str(exc), 400)
    except OSError as exc:
        return _error(str(exc), 502)
    return JSONResponse(
        status_code=201,
        content={"project": project_id, "status": "ready", "template": _normalize_template(template)},
    )


@router.get("")
def list_projects():
    projects = storage.list_projects()
    serialized = [storage.serialize_project(project) for project in projects]
    return {
        "count": len(serialized),
        "projects": serialized,
    }


@router.post("")
def create_project_from_body(req: CreateProjectRequest):
    """Next.js BFF /api/files POST gövdesi ile uyumlu."""
    return _create_project(req.name.strip(), req.template)


@router.post("/{project_id}")
def create_project(project_id: str, template: str = "caravel"):
    return _create_project(project_id, template)


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


@router.get("/{project_id}")
def list_project_objects_alias(project_id: str, request: Request):
    """Nginx /api öneki düşünce: GET /files/{project_id}?prefix=..."""
    return list_project_objects(project_id, request)


@router.put("/{project_id}/objects/{key:path}")
async def put_project_object(project_id: str, key: str, request: Request):
    if not key:
        return _error("object key is required", 400)

    content_type = (
        request.headers.get("x-content-type")
        or request.headers.get("content-type")
        or "application/octet-stream"
    )
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


@router.post("/{project_id}/upload")
async def upload_project_object(project_id: str, request: Request):
    """Next.js BFF /api/files/{projectId}/upload?key=... ile uyumlu."""
    key = request.query_params.get("key")
    if not key:
        return _error("key query param is required", 400)
    return await put_project_object(project_id, key, request)


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


@router.get("/{project_id}/{key:path}")
def get_project_object_alias(project_id: str, key: str):
    return get_project_object(project_id, key)


@router.delete("/{project_id}/{key:path}")
def delete_project_object_alias(project_id: str, key: str):
    return delete_project_object(project_id, key)
