import json

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from app.services import jobs_repo
from app.services.pubsub import broker
from app.services.tool_runner import cancel_job, schedule_job
from app.tools_catalog import get_tool

router = APIRouter(prefix="/run", tags=["run"])


class RunRequest(BaseModel):
    project_id: str = Field(min_length=1, max_length=128)
    action: str = Field(min_length=1, max_length=64)


@router.post("")
def start_run(req: RunRequest):
    spec = get_tool(req.action)
    if spec is None:
        raise HTTPException(status_code=400, detail=f"unknown action: {req.action}")
    if not spec.enabled:
        raise HTTPException(status_code=400, detail=f"action '{req.action}' is not enabled in this build")

    job = jobs_repo.create_job(
        project_id=req.project_id,
        action=spec.id,
        image=spec.image,
        command=json.dumps(spec.cmd),
    )

    schedule_job(job.id)

    return {
        "job_id": job.id,
        "status": job.status.value,
        "action": job.action,
        "image": job.image,
    }


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
