from datetime import datetime
from typing import List, Optional

from sqlmodel import Session, desc, select

from app.core.db import session_scope
from app.models.job import Job, JobStatus


def _detach(session: Session, job: Job) -> Job:
    session.refresh(job)
    session.expunge(job)
    return job


def create_job(project_id: str, action: str, image: str, command: str) -> Job:
    job = Job(
        project_id=project_id,
        action=action,
        image=image,
        command=command,
        status=JobStatus.QUEUED,
    )
    with session_scope() as session:
        session.add(job)
        session.flush()
        return _detach(session, job)


def get_job(job_id: str) -> Optional[Job]:
    with session_scope() as session:
        job = session.get(Job, job_id)
        if job is None:
            return None
        return _detach(session, job)


def list_jobs(
    project_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> List[Job]:
    with session_scope() as session:
        stmt = select(Job)
        if project_id:
            stmt = stmt.where(Job.project_id == project_id)
        stmt = stmt.order_by(desc(Job.created_at)).limit(limit).offset(offset)
        jobs = list(session.exec(stmt).all())
        for job in jobs:
            session.expunge(job)
        return jobs


def update_job(job_id: str, **fields) -> Optional[Job]:
    with session_scope() as session:
        job = session.get(Job, job_id)
        if not job:
            return None
        for key, value in fields.items():
            if hasattr(job, key):
                setattr(job, key, value)
        session.add(job)
        session.flush()
        return _detach(session, job)


def mark_started(job_id: str, container_id: Optional[str] = None) -> Optional[Job]:
    return update_job(
        job_id,
        status=JobStatus.RUNNING,
        started_at=datetime.utcnow(),
        container_id=container_id,
    )


def mark_finished(
    job_id: str,
    *,
    status: JobStatus,
    exit_code: Optional[int] = None,
    log_object_key: Optional[str] = None,
    artifacts_prefix: Optional[str] = None,
    error_message: Optional[str] = None,
) -> Optional[Job]:
    return update_job(
        job_id,
        status=status,
        exit_code=exit_code,
        log_object_key=log_object_key,
        artifacts_prefix=artifacts_prefix,
        error_message=error_message,
        finished_at=datetime.utcnow(),
    )
