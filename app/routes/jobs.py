from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.core import storage
from app.services import jobs_repo

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _serialize(job) -> dict:
    return {
        "id": job.id,
        "project_id": job.project_id,
        "action": job.action,
        "image": job.image,
        "command": job.command,
        "status": job.status.value if hasattr(job.status, "value") else job.status,
        "exit_code": job.exit_code,
        "log_object_key": job.log_object_key,
        "artifacts_prefix": job.artifacts_prefix,
        "error_message": job.error_message,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }


@router.get("/")
def list_jobs(
    project_id: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    jobs = jobs_repo.list_jobs(project_id=project_id, limit=limit, offset=offset)
    return {
        "count": len(jobs),
        "jobs": [_serialize(j) for j in jobs],
    }


@router.get("/{job_id}")
def get_job(job_id: str):
    job = jobs_repo.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return _serialize(job)


@router.get("/{job_id}/log")
def get_job_log(job_id: str):
    """Workspace'teki job log dosyasını text/plain olarak streamler."""
    job = jobs_repo.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    if not job.log_object_key:
        raise HTTPException(status_code=404, detail="log not yet available")

    try:
        chunks = storage.iter_object_chunks(job.project_id, job.log_object_key)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="log not yet available") from None

    return StreamingResponse(chunks, media_type="text/plain; charset=utf-8")
