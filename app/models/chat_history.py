from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ChatHistoryMessage(SQLModel, table=True):
    __tablename__ = "chat_history_messages"

    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: str = Field(index=True)
    client_message_id: str = Field(index=True)
    role: str
    content: str
    created_at: datetime = Field(default_factory=_utcnow)
    attachments_json: Optional[str] = None
    thinking: Optional[str] = None
    position: int = Field(default=0, index=True)
