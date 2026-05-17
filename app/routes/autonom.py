"""Atölye — otonom config iyileştirme kampanyaları."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from app.core.workspace_paths import WorkspacePathError
from app.services import autonom_repo
from app.services.autonom_orchestrator import (
    build_preview,
    cancel_campaign,
    schedule_campaign,
)
from app.services.autonom_spec import AutonomCampaignSpec, spec_to_json, validate_spec
from app.services.pubsub import broker

router = APIRouter(prefix="/autonom", tags=["autonom"])


class AutonomCampaignRequest(BaseModel):
    project_id: str = Field(min_length=1)
    config_key: str = Field(min_length=1)
    spec: dict[str, Any]


class AutonomPreviewRequest(BaseModel):
    project_id: str = Field(min_length=1)
    config_key: str = Field(min_length=1)
    spec: dict[str, Any]


@router.post("/campaigns/preview")
def preview_campaign(req: AutonomPreviewRequest):
    try:
        validated: AutonomCampaignSpec = validate_spec(req.spec)  # type: ignore[arg-type]
        return build_preview(validated, req.config_key, req.project_id)
    except (WorkspacePathError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/campaigns")
def start_campaign(req: AutonomCampaignRequest):
    try:
        validated: AutonomCampaignSpec = validate_spec(req.spec)  # type: ignore[arg-type]
        spec_json = spec_to_json(validated)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    campaign = autonom_repo.create_campaign(
        req.project_id,
        req.config_key.strip(),
        spec_json,
    )
    schedule_campaign(campaign.id)
    return {"campaign_id": campaign.id, "status": campaign.status.value}


@router.get("/campaigns/{campaign_id}")
def get_campaign(campaign_id: str):
    campaign = autonom_repo.get_campaign(campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="campaign not found")
    iterations = autonom_repo.list_iterations(campaign_id)
    return {
        "campaign": {
            "id": campaign.id,
            "project_id": campaign.project_id,
            "config_key": campaign.config_key,
            "status": campaign.status.value,
            "current_iteration": campaign.current_iteration,
            "stop_reason": campaign.stop_reason,
            "error_message": campaign.error_message,
            "spec": json.loads(campaign.spec_json),
            "created_at": campaign.created_at.isoformat(),
            "started_at": campaign.started_at.isoformat() if campaign.started_at else None,
            "finished_at": campaign.finished_at.isoformat() if campaign.finished_at else None,
        },
        "iterations": [
            {
                "index": it.index,
                "param_label": it.param_label,
                "param_value": json.loads(it.param_value_json),
                "status": it.status.value,
                "config_object_key": it.config_object_key,
                "job_ids": autonom_repo.iteration_job_ids(it),
                "error_summary": it.error_summary,
            }
            for it in iterations
        ],
    }


@router.get("/campaigns/{campaign_id}/stream")
async def stream_campaign(campaign_id: str, request: Request):
    campaign = autonom_repo.get_campaign(campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="campaign not found")

    last_event_id_raw = request.headers.get("last-event-id")
    try:
        after_seq = int(last_event_id_raw) if last_event_id_raw else 0
    except ValueError:
        after_seq = 0

    async def event_generator():
        async for event in broker.subscribe(campaign_id, after_seq=after_seq):
            if await request.is_disconnected():
                break
            yield event.to_sse()

    return EventSourceResponse(event_generator())


@router.post("/campaigns/{campaign_id}/cancel")
def cancel_campaign_route(campaign_id: str):
    campaign = autonom_repo.get_campaign(campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="campaign not found")
    cancel_campaign(campaign_id)
    return {"campaign_id": campaign_id, "cancelled": True}
