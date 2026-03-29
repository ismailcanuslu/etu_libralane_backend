from fastapi import APIRouter
import os

router = APIRouter(prefix="/jobs")

@router.get("/{job_id}")
def get_log(job_id: str):

    log_file = f"logs/job_{job_id}.log"

    if not os.path.exists(log_file):
        return {"error": "job not found"}

    with open(log_file) as f:
        content = f.read()

    return {
        "job_id": job_id,
        "log": content
    }
