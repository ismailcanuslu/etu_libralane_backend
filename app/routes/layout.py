"""Layout önizleme API (GDS bytes / KLayout PNG)."""

from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse, Response

from app.core.workspace_paths import WorkspacePathError
from app.services import layout_preview

router = APIRouter(prefix="/layout", tags=["layout"])


def _error(message: str, status_code: int) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": message})


@router.get("/capabilities")
def layout_capabilities():
    return {
        "engines": [
            {
                "id": "browser",
                "label": "Tarayıcı (hızlı)",
                "description": "GDS poligon önizlemesi; katman detayı sınırlı.",
            },
            {
                "id": "klayout",
                "label": "KLayout (backend)",
                "description": "OpenLane imajında KLayout ile PNG render.",
                "available": layout_preview.klayout_available(),
            },
        ]
    }


@router.get("/preview/{project_id}")
async def layout_preview_route(
    project_id: str,
    key: str = Query(..., min_length=1),
    engine: str = Query("browser", pattern="^(browser|klayout)$"),
    width: int = Query(layout_preview.KLAYOUT_DEFAULT_WIDTH, ge=200, le=8192),
    height: int = Query(layout_preview.KLAYOUT_DEFAULT_HEIGHT, ge=200, le=8192),
):
    try:
        if engine == "browser":
            data = layout_preview.read_gds_bytes(project_id, key)
            return Response(
                content=data,
                media_type="application/octet-stream",
                headers={"X-Layout-Engine": "browser"},
            )
        png = await layout_preview.render_klayout_png(
            project_id, key, width=width, height=height
        )
        return Response(
            content=png,
            media_type="image/png",
            headers={"X-Layout-Engine": "klayout"},
        )
    except FileNotFoundError:
        return _error("GDS dosyası bulunamadı", 404)
    except WorkspacePathError as exc:
        return _error(str(exc), 400)
    except RuntimeError as exc:
        return _error(str(exc), 502)
    except OSError as exc:
        return _error(str(exc), 502)
