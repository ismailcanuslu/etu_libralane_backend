"""Host sistem metrikleri."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter

from app.services.system_metrics import collect_system_metrics

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/metrics")
async def get_system_metrics():
    """CPU, RAM, disk, GPU ve ağ özeti (host üzerinde psutil)."""
    return await asyncio.to_thread(collect_system_metrics)
