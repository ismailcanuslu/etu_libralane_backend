"""Otonom config iyileştirme kampanyası."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import uuid4

from sqlmodel import Field, SQLModel


class AutonomCampaignStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AutonomIterationStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return uuid4().hex


class AutonomCampaign(SQLModel, table=True):
    __tablename__ = "autonom_campaigns"

    id: str = Field(default_factory=_new_id, primary_key=True)
    project_id: str = Field(index=True)
    config_key: str = Field(description="Workspace içindeki config dosya yolu")
    spec_json: str = Field(description="AutonomCampaignSpec JSON")
    status: AutonomCampaignStatus = Field(
        default=AutonomCampaignStatus.QUEUED, index=True
    )
    current_iteration: int = Field(default=0)
    stop_reason: Optional[str] = None
    error_message: Optional[str] = None

    created_at: datetime = Field(default_factory=_utcnow, index=True)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class AutonomIteration(SQLModel, table=True):
    __tablename__ = "autonom_iterations"

    id: str = Field(default_factory=_new_id, primary_key=True)
    campaign_id: str = Field(index=True, foreign_key="autonom_campaigns.id")
    index: int = Field(index=True)
    param_value_json: str = Field(description="Bu iterasyondaki parametre değeri")
    param_label: str = Field(default="")
    status: AutonomIterationStatus = Field(
        default=AutonomIterationStatus.PENDING, index=True
    )
    job_ids_json: Optional[str] = Field(default=None, description="Sıralı child job id listesi")
    config_object_key: Optional[str] = Field(
        default=None, description="Bu iterasyonun config kopyası storage anahtarı"
    )
    error_summary: Optional[str] = None

    created_at: datetime = Field(default_factory=_utcnow)
    finished_at: Optional[datetime] = None
