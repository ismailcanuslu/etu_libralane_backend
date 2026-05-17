import asyncio
import json

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from app.services import jobs_repo
from app.services.pubsub import broker
from app.services.terminal_tabs import registry as terminal_registry
from app.services.openlane_layout import resolve_design_name
from app.services.tool_runner import cancel_job, execute_job
from app.tools_catalog import build_tool_command, get_tool

router = APIRouter(prefix="/run", tags=["run"])


class RunRequest(BaseModel):
    project_id: str = Field(min_length=1, max_length=128)
    action: str = Field(min_length=1, max_length=64)
    design_name: Optional[str] = Field(default=None, max_length=128)
    args: Optional[List[str]] = None


@router.post("")
async def start_run(req: RunRequest):
    spec = get_tool(req.action)
    if spec is None:
        raise HTTPException(status_code=400, detail=f"unknown action: {req.action}")
    if not spec.enabled:
        raise HTTPException(status_code=400, detail=f"action '{req.action}' is not enabled in this build")

    design_name = req.design_name.strip() if req.design_name else None
    if spec.kind == "flow":
        design_name = resolve_design_name(req.project_id, design_name)

    try:
        command = build_tool_command(spec, design_name=design_name, extra_args=req.args)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    job = jobs_repo.create_job(
        project_id=req.project_id,
        action=spec.id,
        image=spec.image,
        command=json.dumps(command),
    )
    terminal_registry.open(job.id, req.project_id, spec.id)

    asyncio.create_task(execute_job(job.id))

    return {
        "job_id": job.id,
        "status": job.status.value,
        "action": job.action,
        "image": job.image,
    }


@router.post("/terminals/{job_id}")
def open_terminal_tab(job_id: str):
    job = jobs_repo.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    record = terminal_registry.open(job.id, job.project_id, job.action)
    return {
        "job_id": job.id,
        "project_id": job.project_id,
        "action": job.action,
        "opened_at": record.opened_at.isoformat(),
    }


@router.get("/terminals")
def list_terminal_tabs(project_id: Optional[str] = None):
    tabs = []
    for record in terminal_registry.list_open(project_id=project_id):
        job = jobs_repo.get_job(record.job_id)
        if not job:
            continue
        tabs.append(
            {
                "job_id": job.id,
                "project_id": job.project_id,
                "action": job.action,
                "status": job.status.value if hasattr(job.status, "value") else job.status,
                "exit_code": job.exit_code,
                "opened_at": record.opened_at.isoformat(),
                "started_at": job.started_at.isoformat() if job.started_at else None,
                "finished_at": job.finished_at.isoformat() if job.finished_at else None,
            }
        )
    return {"tabs": tabs}


@router.delete("/terminals/{job_id}")
def close_terminal_tab(job_id: str):
    if not terminal_registry.close(job_id):
        raise HTTPException(status_code=404, detail="terminal tab not found")
    return {"job_id": job_id, "closed": True}


@router.get("/{job_id}")
def get_run(job_id: str):
    job = jobs_repo.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return {
        "job_id": job.id,
        "status": job.status.value if hasattr(job.status, "value") else job.status,
        "exit_code": job.exit_code,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }


@router.get("/{job_id}/stream")
async def stream_run(job_id: str, request: Request):
    job = jobs_repo.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")

    # EventSource auto-reconnect: tarayıcı son aldığı event id'yi gönderir.
    last_event_id_raw = request.headers.get("last-event-id")
    try:
        after_seq = int(last_event_id_raw) if last_event_id_raw else 0
    except ValueError:
        after_seq = 0

    async def event_generator():
        # Snapshot sadece ilk bağlantıda; reconnect sırasında istenmez (after_seq>0).
        if after_seq == 0:
            snapshot = jobs_repo.get_job(job_id)
            if snapshot:
                yield {
                    "event": "snapshot",
                    "data": json.dumps(
                        {
                            "status": snapshot.status.value,
                            "exit_code": snapshot.exit_code,
                            "action": snapshot.action,
                            "image": snapshot.image,
                        }
                    ),
                }

        async for event in broker.subscribe(job_id, after_seq=after_seq):
            if await request.is_disconnected():
                break
            yield event.to_sse()

    return EventSourceResponse(event_generator())


@router.post("/{job_id}/cancel")
async def cancel_run(job_id: str):
    job = jobs_repo.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    ok = await cancel_job(job_id)
    return {"job_id": job_id, "cancelled": ok}
