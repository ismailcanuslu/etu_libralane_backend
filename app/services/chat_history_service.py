from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlmodel import Session, select

from app.core.db import session_scope
from app.models.chat_history import ChatHistoryMessage


def _parse_ts(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return datetime.now(timezone.utc)


def get_messages_for_project(project_id: str) -> list[dict[str, Any]]:
    if not project_id.strip():
        return []
    with session_scope() as session:
        stmt = (
            select(ChatHistoryMessage)
            .where(ChatHistoryMessage.project_id == project_id)
            .order_by(ChatHistoryMessage.position, ChatHistoryMessage.id)
        )
        rows = list(session.exec(stmt).all())
        out: list[dict[str, Any]] = []
        for row in rows:
            attachments: list[Any] | None = None
            if row.attachments_json:
                try:
                    parsed = json.loads(row.attachments_json)
                    if isinstance(parsed, list):
                        attachments = parsed
                except json.JSONDecodeError:
                    attachments = None
            item: dict[str, Any] = {
                "id": row.client_message_id,
                "role": row.role,
                "content": row.content,
                "timestamp": row.created_at.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z"),
                "attachments": attachments,
            }
            th = getattr(row, "thinking", None)
            if isinstance(th, str) and th.strip():
                item["thinking"] = th.strip()
            out.append(item)
    return out


def replace_project_messages(session: Session, project_id: str, messages: list[dict[str, Any]]) -> None:
    existing = session.exec(
        select(ChatHistoryMessage).where(ChatHistoryMessage.project_id == project_id)
    ).all()
    for row in existing:
        session.delete(row)
    session.flush()

    for position, msg in enumerate(messages):
        mid = str(msg.get("id") or f"row-{position}")
        role = str(msg.get("role") or "user")
        content = str(msg.get("content") or "")
        ts_raw = msg.get("timestamp")
        created = _parse_ts(str(ts_raw)) if isinstance(ts_raw, str) else datetime.now(timezone.utc)
        att = msg.get("attachments")
        att_json = json.dumps(att, ensure_ascii=False) if att is not None else None
        th = msg.get("thinking")
        thinking_val = th.strip() if isinstance(th, str) and th.strip() else None
        session.add(
            ChatHistoryMessage(
                project_id=project_id,
                client_message_id=mid,
                role=role,
                content=content,
                created_at=created,
                attachments_json=att_json,
                thinking=thinking_val,
                position=position,
            )
        )


def save_project_history(project_id: str, messages: list[dict[str, Any]]) -> None:
    if not project_id.strip():
        return
    with session_scope() as session:
        replace_project_messages(session, project_id, messages)
