from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.workspace_paths import WorkspacePathError
from app.services.pdk_info import get_pdk_runtime_info
from app.services.run_preview import build_run_preview
from app.services.openlane_config_catalog import load_catalog, search_variables
from app.tools_catalog import list_tools

router = APIRouter(prefix="/tools", tags=["tools"])


class RunPreviewRequest(BaseModel):
    project_id: str = Field(min_length=1)
    action: str = Field(min_length=1)
    design_name: str | None = None


@router.get("/runtime")
def get_eda_runtime():
    """Sky130 PDK yolu ve runner bilgisi (UI)."""
    from app.core.config import get_settings

    settings = get_settings()
    return {
        "pdk": get_pdk_runtime_info(),
        "workspace_root": settings.workspace_root,
        "jobs_host_dir": settings.jobs_host_dir,
        "runner_image_openlane": settings.runner_image_openlane,
    }


@router.get("/preview")
def get_run_preview_query(
    project_id: str = Query(min_length=1),
    action: str = Query(min_length=1),
    design_name: str | None = Query(default=None),
):
    try:
        return build_run_preview(project_id, action, design_name=design_name)
    except WorkspacePathError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/preview")
def post_run_preview(req: RunPreviewRequest):
    try:
        return build_run_preview(req.project_id, req.action, design_name=req.design_name)
    except WorkspacePathError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/openlane-config-catalog")
def get_openlane_config_catalog(
    q: str | None = Query(default=None, min_length=0),
    category: str | None = Query(default=None),
):
    """OpenLane config bayrak kataloğu (TR açıklamalar)."""
    catalog = load_catalog()
    if q and len(q.strip()) >= 2:
        keys = search_variables(catalog, q, category=category)
        variables = {k: catalog["variables"][k] for k in keys if k in catalog.get("variables", {})}
        return {
            **{k: catalog[k] for k in ("version", "generated_at", "source_url", "required_keys", "scaffold_recommended_keys", "categories") if k in catalog},
            "variables": variables,
        }
    return catalog


@router.get("")
def get_tools():
    return {
        "tools": [
            {
                "id": t.id,
                "label": t.label,
                "description": t.description,
                "image": t.image,
                "group": t.group,
                "badge": t.badge,
                "enabled": t.enabled,
                "kind": t.kind,
                "requires_verilog": t.requires_verilog,
                "requires_config": t.requires_config,
                "requires_pdk": t.requires_pdk,
            }
            for t in list_tools()
        ]
    }
