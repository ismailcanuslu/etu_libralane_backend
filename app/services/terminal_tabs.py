"""Sunucu tarafı terminal sekmeleri — her job için açık sekme kaydı tutulur."""
from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class TerminalTabRecord:
    job_id: str
    project_id: str
    action: str
    opened_at: datetime
    closed_at: Optional[datetime] = None


class TerminalTabRegistry:
    def __init__(self) -> None:
        self._tabs: Dict[str, TerminalTabRecord] = {}
        self._lock = threading.Lock()

    def open(self, job_id: str, project_id: str, action: str) -> TerminalTabRecord:
        with self._lock:
            existing = self._tabs.get(job_id)
            if existing is not None and existing.closed_at is None:
                return existing
            record = TerminalTabRecord(
                job_id=job_id,
                project_id=project_id,
                action=action,
                opened_at=_utcnow(),
            )
            self._tabs[job_id] = record
            return record

    def close(self, job_id: str) -> bool:
        with self._lock:
            record = self._tabs.get(job_id)
            if record is None or record.closed_at is not None:
                return False
            record.closed_at = _utcnow()
            return True

    def list_open(self, project_id: Optional[str] = None) -> List[TerminalTabRecord]:
        with self._lock:
            records = [record for record in self._tabs.values() if record.closed_at is None]
        if project_id:
            records = [record for record in records if record.project_id == project_id]
        return sorted(records, key=lambda record: record.opened_at)


registry = TerminalTabRegistry()
