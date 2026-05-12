from fastapi import APIRouter

from app.tools_catalog import list_tools

router = APIRouter(prefix="/tools", tags=["tools"])


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
