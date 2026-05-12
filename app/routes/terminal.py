import asyncio
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, WebSocket
from pydantic import BaseModel, Field
from starlette.websockets import WebSocketDisconnect

from app.services.host_shell import host_terminal_status, registry, relay_master_to_websocket, relay_websocket_to_master

router = APIRouter(prefix="/terminal", tags=["terminal"])


class CreateShellSessionRequest(BaseModel):
    project_id: str = Field(min_length=1, max_length=128)


@router.get("/status")
def terminal_status():
    return host_terminal_status()


@router.post("/sessions")
def create_shell_session(req: CreateShellSessionRequest):
    try:
        session = registry.create(req.project_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "session_id": session.session_id,
        "project_id": session.project_id,
        "cwd": session.cwd,
        "created_at": session.created_at.isoformat(),
    }


@router.get("/sessions")
def list_shell_sessions(project_id: Optional[str] = Query(default=None)):
    sessions = registry.list_open(project_id=project_id)
    return {
        "sessions": [
            {
                "session_id": session.session_id,
                "project_id": session.project_id,
                "cwd": session.cwd,
                "created_at": session.created_at.isoformat(),
            }
            for session in sessions
        ]
    }


@router.delete("/sessions/{session_id}")
def close_shell_session(session_id: str):
    if not registry.close(session_id):
        raise HTTPException(status_code=404, detail="shell session not found")
    return {"session_id": session_id, "closed": True}


@router.websocket("/ws/{session_id}")
async def shell_websocket(websocket: WebSocket, session_id: str):
    session = registry.get(session_id)
    if session is None or session.closed_at is not None:
        await websocket.close(code=4404)
        return

    await websocket.accept()
    reader = asyncio.create_task(relay_master_to_websocket(session, websocket))
    try:
        await relay_websocket_to_master(session, websocket)
    except WebSocketDisconnect:
        pass
    finally:
        reader.cancel()
        registry.close(session_id)
