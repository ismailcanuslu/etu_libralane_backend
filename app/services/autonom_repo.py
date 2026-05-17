"""Autonom kampanya CRUD."""

from __future__ import annotations

import json
from datetime import datetime
from typing import List, Optional

from sqlmodel import Session, desc, select

from app.core.db import session_scope
from app.models.autonom_campaign import (
    AutonomCampaign,
    AutonomCampaignStatus,
    AutonomIteration,
    AutonomIterationStatus,
)


def _detach(session: Session, obj):
    session.refresh(obj)
    session.expunge(obj)
    return obj


def create_campaign(
    project_id: str,
    config_key: str,
    spec_json: str,
) -> AutonomCampaign:
    campaign = AutonomCampaign(
        project_id=project_id,
        config_key=config_key,
        spec_json=spec_json,
        status=AutonomCampaignStatus.QUEUED,
    )
    with session_scope() as session:
        session.add(campaign)
        session.flush()
        return _detach(session, campaign)


def get_campaign(campaign_id: str) -> Optional[AutonomCampaign]:
    with session_scope() as session:
        row = session.get(AutonomCampaign, campaign_id)
        if row is None:
            return None
        return _detach(session, row)


def update_campaign(campaign_id: str, **fields) -> Optional[AutonomCampaign]:
    with session_scope() as session:
        row = session.get(AutonomCampaign, campaign_id)
        if not row:
            return None
        for key, value in fields.items():
            if hasattr(row, key):
                setattr(row, key, value)
        session.add(row)
        session.flush()
        return _detach(session, row)


def list_iterations(campaign_id: str) -> List[AutonomIteration]:
    with session_scope() as session:
        stmt = (
            select(AutonomIteration)
            .where(AutonomIteration.campaign_id == campaign_id)
            .order_by(AutonomIteration.index)
        )
        rows = list(session.exec(stmt).all())
        for row in rows:
            session.expunge(row)
        return rows


def create_iteration(
    campaign_id: str,
    index: int,
    param_value_json: str,
    param_label: str,
) -> AutonomIteration:
    row = AutonomIteration(
        campaign_id=campaign_id,
        index=index,
        param_value_json=param_value_json,
        param_label=param_label,
        status=AutonomIterationStatus.PENDING,
    )
    with session_scope() as session:
        session.add(row)
        session.flush()
        return _detach(session, row)


def update_iteration(iteration_id: str, **fields) -> Optional[AutonomIteration]:
    with session_scope() as session:
        row = session.get(AutonomIteration, iteration_id)
        if not row:
            return None
        for key, value in fields.items():
            if hasattr(row, key):
                setattr(row, key, value)
        session.add(row)
        session.flush()
        return _detach(session, row)


def get_iteration_by_index(campaign_id: str, index: int) -> Optional[AutonomIteration]:
    with session_scope() as session:
        stmt = select(AutonomIteration).where(
            AutonomIteration.campaign_id == campaign_id,
            AutonomIteration.index == index,
        )
        row = session.exec(stmt).first()
        if row is None:
            return None
        return _detach(session, row)


def iteration_job_ids(iteration: AutonomIteration) -> list[str]:
    if not iteration.job_ids_json:
        return []
    try:
        parsed = json.loads(iteration.job_ids_json)
        if isinstance(parsed, list):
            return [str(x) for x in parsed]
    except json.JSONDecodeError:
        pass
    return []
