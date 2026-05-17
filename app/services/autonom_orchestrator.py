"""Atölye kampanya orkestratörü — config iterasyonu + build araçları."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

from app.core.config import get_settings
from app.core import storage
from app.models.autonom_campaign import AutonomCampaignStatus, AutonomIterationStatus
from app.models.job import JobStatus
from app.openlane1_flow_stages import normalize_flow_steps
from app.services import autonom_repo, jobs_repo
from app.services.autonom_spec import (
    AutonomCampaignSpec,
    format_param_label,
    list_iteration_values,
    parse_spec_json,
)
from app.services.job_command import encode_job_command
from app.services.openlane_config_patch import patch_config_content
from app.services.pubsub import broker
from app.services.tool_runner import schedule_execute_job
from app.tools_catalog import build_tool_command, get_tool
from app.services.openlane_layout import resolve_design_name, resolve_flow_design_arg

_settings = get_settings()
_running_campaigns: dict[str, asyncio.Task] = {}
_cancelled_campaigns: set[str] = set()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _campaign_prefix(campaign_id: str) -> str:
    return f"{_settings.autonom_jobs_artifacts_prefix}/{campaign_id}"


def _is_cancelled(campaign_id: str) -> bool:
    return campaign_id in _cancelled_campaigns


async def _wait_job_terminal_for_campaign(campaign_id: str, job_id: str) -> JobStatus:
    while True:
        if _is_cancelled(campaign_id):
            return JobStatus.CANCELLED
        job = jobs_repo.get_job(job_id)
        if job is None:
            return JobStatus.FAILED
        if job.status in (JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELLED):
            return job.status
        await asyncio.sleep(1.0)


def active_campaign_count() -> int:
    return sum(1 for t in _running_campaigns.values() if not t.done())


def schedule_campaign(campaign_id: str) -> None:
    if active_campaign_count() >= _settings.max_concurrent_autonom_campaigns:
        autonom_repo.update_campaign(
            campaign_id,
            status=AutonomCampaignStatus.FAILED,
            error_message=(
                f"Eşzamanlı kampanya limiti ({_settings.max_concurrent_autonom_campaigns}) dolu"
            ),
            stop_reason="Kampanya kuyruğa alınamadı",
            finished_at=datetime.now(timezone.utc),
        )
        return

    async def _wrapper() -> None:
        try:
            await execute_campaign(campaign_id)
        finally:
            _running_campaigns.pop(campaign_id, None)

    _running_campaigns[campaign_id] = asyncio.create_task(_wrapper())


def cancel_campaign(campaign_id: str) -> bool:
    _cancelled_campaigns.add(campaign_id)
    autonom_repo.update_campaign(
        campaign_id,
        status=AutonomCampaignStatus.CANCELLED,
        stop_reason="Kullanıcı iptal etti",
        finished_at=datetime.now(timezone.utc),
    )
    task = _running_campaigns.get(campaign_id)
    if task and not task.done():
        task.cancel()
    return True


async def execute_campaign(campaign_id: str) -> None:
    campaign = autonom_repo.get_campaign(campaign_id)
    if campaign is None:
        return

    try:
        spec = parse_spec_json(campaign.spec_json)
    except ValueError as exc:
        autonom_repo.update_campaign(
            campaign_id,
            status=AutonomCampaignStatus.FAILED,
            error_message=str(exc),
            finished_at=datetime.now(timezone.utc),
        )
        await broker.publish(campaign_id, "error", {"message": str(exc)})
        await broker.close(campaign_id)
        return

    autonom_repo.update_campaign(
        campaign_id,
        status=AutonomCampaignStatus.RUNNING,
        started_at=datetime.now(timezone.utc),
    )
    await broker.publish(
        campaign_id,
        "status",
        {"status": "running", "message": "Kampanya başladı"},
    )

    try:
        base_config = storage.read_bytes(campaign.project_id, campaign.config_key)
    except Exception as exc:  # noqa: BLE001
        await _fail_campaign(campaign_id, f"Config okunamadı: {exc}")
        return

    try:
        iteration_values = list_iteration_values(spec)
    except ValueError as exc:
        await _fail_campaign(campaign_id, str(exc))
        return

    param = spec["param"]
    config_key = campaign.config_key
    input_files_base = list(spec.get("input_files") or [])
    build_actions = list(spec["build_actions"])
    flow_steps = None
    if "openlane1-flow" in build_actions and spec.get("openlane_flow_steps"):
        try:
            flow_steps = normalize_flow_steps(spec["openlane_flow_steps"])
        except ValueError as exc:
            await _fail_campaign(campaign_id, str(exc))
            return

    for idx, iter_value in enumerate(iteration_values):
        if _is_cancelled(campaign_id):
            await _finish_cancelled(campaign_id)
            return

        label = format_param_label(iter_value, param)
        value_json = json.dumps(iter_value, ensure_ascii=False)
        iteration = autonom_repo.create_iteration(
            campaign_id, idx, value_json, label
        )
        autonom_repo.update_campaign(campaign_id, current_iteration=idx)

        await broker.publish(
            campaign_id,
            "iteration_started",
            {"index": idx, "param_label": label, "param_value": iter_value},
        )

        autonom_repo.update_iteration(
            iteration.id,
            status=AutonomIterationStatus.RUNNING,
        )

        iter_config_key = f"{_campaign_prefix(campaign_id)}/iter_{idx}/{config_key}"
        try:
            patched = patch_config_content(base_config, config_key, param, iter_value)
            storage.write_bytes(campaign.project_id, iter_config_key, patched)
        except Exception as exc:  # noqa: BLE001
            await _fail_iteration_and_campaign(
                campaign_id, iteration.id, idx, f"Config patch: {exc}"
            )
            return

        autonom_repo.update_iteration(iteration.id, config_object_key=iter_config_key)

        # Bu iterasyonda kullanılacak dosyalar: config anahtarını iter kopyasıyla değiştir
        input_keys = [k for k in input_files_base if k != config_key]
        input_keys.append(iter_config_key)
        input_keys_json = json.dumps(sorted(set(input_keys)))

        child_job_ids: list[str] = []
        for action in build_actions:
            if _is_cancelled(campaign_id):
                await _finish_cancelled(campaign_id)
                return

            tool = get_tool(action)
            if tool is None or not tool.enabled:
                await _fail_iteration_and_campaign(
                    campaign_id,
                    iteration.id,
                    idx,
                    f"Araç kullanılamıyor: {action}",
                )
                return

            design_name = None
            flow_design_arg = None
            if tool.kind == "flow":
                flow_design_arg = resolve_flow_design_arg(campaign.project_id, None)
                design_name = resolve_design_name(campaign.project_id, None)

            try:
                argv = build_tool_command(
                    tool,
                    design_name=flow_design_arg if tool.kind == "flow" else design_name,
                    flow_steps=flow_steps if action == "openlane1-flow" else None,
                )
            except ValueError as exc:
                await _fail_iteration_and_campaign(
                    campaign_id, iteration.id, idx, str(exc)
                )
                return

            job = jobs_repo.create_job(
                campaign.project_id,
                tool.id,
                tool.image,
                encode_job_command(
                    argv,
                    flow_steps=flow_steps if action == "openlane1-flow" else None,
                ),
                input_keys_json=input_keys_json,
                channel="autonom",
                campaign_id=campaign_id,
            )
            child_job_ids.append(job.id)
            schedule_execute_job(job.id)

            await broker.publish(
                campaign_id,
                "job_started",
                {"iteration": idx, "action": action, "job_id": job.id},
            )

            status = await _wait_job_terminal_for_campaign(campaign_id, job.id)
            if status != JobStatus.DONE:
                reason = f"{action} başarısız (job {job.id[:8]}, durum={status.value})"
                autonom_repo.update_iteration(
                    iteration.id,
                    status=AutonomIterationStatus.FAILED,
                    job_ids_json=json.dumps(child_job_ids),
                    error_summary=reason,
                    finished_at=datetime.now(timezone.utc),
                )
                await broker.publish(
                    campaign_id,
                    "iteration_done",
                    {"index": idx, "status": "failed", "reason": reason},
                )
                autonom_repo.update_campaign(
                    campaign_id,
                    status=AutonomCampaignStatus.FAILED,
                    stop_reason=reason,
                    finished_at=datetime.now(timezone.utc),
                )
                await broker.publish(
                    campaign_id,
                    "done",
                    {"status": "failed", "stop_reason": reason},
                )
                await broker.close(campaign_id)
                return

        autonom_repo.update_iteration(
            iteration.id,
            status=AutonomIterationStatus.DONE,
            job_ids_json=json.dumps(child_job_ids),
            finished_at=datetime.now(timezone.utc),
        )
        await broker.publish(
            campaign_id,
            "iteration_done",
            {"index": idx, "status": "done", "param_label": label},
        )

        # Son iterasyon (hedefe ulaşıldı)
        if idx == len(iteration_values) - 1:
            autonom_repo.update_campaign(
                campaign_id,
                status=AutonomCampaignStatus.DONE,
                stop_reason="Hedef parametre değerine ulaşıldı",
                finished_at=datetime.now(timezone.utc),
            )
            await broker.publish(
                campaign_id,
                "done",
                {"status": "done", "stop_reason": "Hedef parametre değerine ulaşıldı"},
            )
            await broker.close(campaign_id)
            return

    autonom_repo.update_campaign(
        campaign_id,
        status=AutonomCampaignStatus.DONE,
        stop_reason="Tüm iterasyonlar tamamlandı",
        finished_at=datetime.now(timezone.utc),
    )
    await broker.publish(
        campaign_id,
        "done",
        {"status": "done", "stop_reason": "Tüm iterasyonlar tamamlandı"},
    )
    await broker.close(campaign_id)


async def _fail_campaign(campaign_id: str, message: str) -> None:
    autonom_repo.update_campaign(
        campaign_id,
        status=AutonomCampaignStatus.FAILED,
        error_message=message,
        stop_reason=message,
        finished_at=datetime.now(timezone.utc),
    )
    await broker.publish(campaign_id, "error", {"message": message})
    await broker.publish(campaign_id, "done", {"status": "failed", "stop_reason": message})
    await broker.close(campaign_id)


async def _fail_iteration_and_campaign(
    campaign_id: str,
    iteration_id: str,
    index: int,
    message: str,
) -> None:
    autonom_repo.update_iteration(
        iteration_id,
        status=AutonomIterationStatus.FAILED,
        error_summary=message,
        finished_at=datetime.now(timezone.utc),
    )
    await broker.publish(
        campaign_id,
        "iteration_done",
        {"index": index, "status": "failed", "reason": message},
    )
    await _fail_campaign(campaign_id, message)


async def _finish_cancelled(campaign_id: str) -> None:
    await broker.publish(campaign_id, "done", {"status": "cancelled"})
    await broker.close(campaign_id)


def build_preview(spec: AutonomCampaignSpec, config_key: str, project_id: str) -> dict[str, Any]:
    """Onay adımı için dosya listesi ve iterasyon tablosu."""
    from app.services.autonom_spec import validate_spec

    validate = validate_spec(spec)
    values = list_iteration_values(validate)
    param = validate["param"]
    iterations = [
        {
            "index": i,
            "param_label": format_param_label(v, param),
            "param_value": v,
        }
        for i, v in enumerate(values)
    ]
    input_files = sorted(set(validate.get("input_files") or []))
    return {
        "project_id": project_id,
        "config_key": config_key,
        "iteration_count": len(values),
        "iterations": iterations,
        "input_files": input_files,
        "build_actions": validate.get("build_actions") or [],
        "openlane_flow_steps": validate.get("openlane_flow_steps"),
        "param": param,
    }
