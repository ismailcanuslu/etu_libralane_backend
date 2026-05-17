import os
from contextlib import contextmanager
from typing import Iterator

from sqlmodel import Session, SQLModel, create_engine

from app.core.config import get_settings

_settings = get_settings()


def _ensure_parent_dir(path: str) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


_ensure_parent_dir(_settings.db_path)

_DB_URL = f"sqlite:///{_settings.db_path}"

engine = create_engine(
    _DB_URL,
    echo=False,
    connect_args={"check_same_thread": False},
)


def init_db() -> None:
    # Tablo metadata'sının yüklenmiş olması için modelleri import et.
    from app.models import chat_history, job  # noqa: F401

    SQLModel.metadata.create_all(engine)
    _ensure_chat_thinking_column()
    _ensure_job_input_keys_column()


def _ensure_chat_thinking_column() -> None:
    """Mevcut SQLite DB'ye thinking sutunu ekle (create_all ALTER yapmaz)."""
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    if "chat_history_messages" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("chat_history_messages")}
    if "thinking" in cols:
        return
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE chat_history_messages ADD COLUMN thinking TEXT"))


def _ensure_job_input_keys_column() -> None:
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    if "jobs" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("jobs")}
    if "input_keys_json" in cols:
        return
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE jobs ADD COLUMN input_keys_json TEXT"))


@contextmanager
def session_scope() -> Iterator[Session]:
    session = Session(engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session() -> Iterator[Session]:
    with session_scope() as session:
        yield session
