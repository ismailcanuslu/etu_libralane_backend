"""Job ve workspace artefakt önekleri (_jobs / _autonom_jobs)."""

from __future__ import annotations

from app.core.config import Settings, get_settings
from app.models.job import Job


def workspace_artifact_prefixes(settings: Settings | None = None) -> list[str]:
    s = settings or get_settings()
    return [
        f"{s.jobs_artifacts_prefix}/",
        f"{s.autonom_jobs_artifacts_prefix}/",
    ]


def job_artifacts_base(settings: Settings | None = None, *, channel: str = "default") -> str:
    s = settings or get_settings()
    if channel == "autonom":
        return s.autonom_jobs_artifacts_prefix
    return s.jobs_artifacts_prefix


def job_artifacts_prefix(job: Job, settings: Settings | None = None) -> str:
    channel = getattr(job, "channel", None) or "default"
    return f"{job_artifacts_base(settings, channel=channel)}/{job.id}"


def job_layout_png_object_key(job_id: str, *, channel: str = "default") -> str:
    from app.services.layout_preview import FLOW_LAYOUT_PNG_NAME

    base = job_artifacts_base(channel=channel)
    return f"{base}/{job_id}/{FLOW_LAYOUT_PNG_NAME}"
