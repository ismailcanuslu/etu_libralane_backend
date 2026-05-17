from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import uuid4

from sqlmodel import Field, SQLModel


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return uuid4().hex


class Job(SQLModel, table=True):
    __tablename__ = "jobs"

    id: str = Field(default_factory=_new_id, primary_key=True)
    project_id: str = Field(index=True)
    action: str
    image: str
    command: str
    # JSON listesi: workspace'e kopyalanacak proje anahtarlari (bos = tum proje)
    input_keys_json: Optional[str] = None

    status: JobStatus = Field(default=JobStatus.QUEUED, index=True)
    exit_code: Optional[int] = None

    log_object_key: Optional[str] = None
    artifacts_prefix: Optional[str] = None
    error_message: Optional[str] = None

    container_id: Optional[str] = None

    created_at: datetime = Field(default_factory=_utcnow, index=True)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
