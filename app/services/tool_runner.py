"""Job orchestrator.

Akış (her job için):
  1. workspace dizinini hazırla (host path)
  2. Workspace'ten proje dosyalarını indir
  3. runner container'ı oluştur ve canlı log akışını başlat
  4. her log satırını dosyaya yaz + pubsub'a publish et
  5. exit code'a göre status, log/artefakt upload, DB güncelleme
  6. workspace cleanup, pubsub close
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
from datetime import datetime, timezone
from typing import Optional

from app.core.config import get_settings
from app.core import storage
from app.models.job import JobStatus
from app.services import jobs_repo
from app.services.pubsub import broker
from app.services.runner import (
    create_container,
    interrupt_container_by_id,
    remove_container,
    stream_container,
    wait_container,
)
from app.tools_catalog import ToolSpec, get_tool


_settings = get_settings()
_run_semaphore: asyncio.Semaphore | None = None


def _get_semaphore() -> asyncio.Semaphore:
    """Global eşzamanlılık semaforu (lazy init: event loop'a bağlı)."""
    global _run_semaphore
    if _run_semaphore is None:
        _run_semaphore = asyncio.Semaphore(_settings.max_concurrent_jobs)
    return _run_semaphore


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _job_root(job_id: str) -> str:
    return os.path.join(_settings.jobs_host_dir, job_id)


def _workspace_dir(job_id: str) -> str:
    return os.path.join(_job_root(job_id), "workspace")


def _log_path(job_id: str) -> str:
    return os.path.join(_job_root(job_id), "job.log")


def _job_command(job, spec: ToolSpec) -> list[str]:
    try:
        parsed = json.loads(job.command)
        if isinstance(parsed, list) and parsed:
            return [str(part) for part in parsed]
    except json.JSONDecodeError:
        pass
    return list(spec.cmd)


def _needs_workspace_files(spec: ToolSpec) -> bool:
    return spec.kind == "flow" or spec.requires_verilog or spec.requires_config


def _has_config_file(paths: list[str]) -> bool:
    return any(
        path.endswith("config.json")
        or path.endswith("config.tcl")
        or path.split("/")[-1] in {"config.json", "config.tcl"}
        for path in paths
    )


def _runner_env(spec: ToolSpec) -> dict[str, str]:
    env: dict[str, str] = {}
    if spec.requires_pdk and _settings.openlane_pdk_host_path:
        env["PDK_ROOT"] = _settings.openlane_pdk_mount_path
    return env


def _runner_extra_volumes(spec: ToolSpec) -> dict:
    if not spec.requires_pdk or not _settings.openlane_pdk_host_path:
        return {}
    return {
        _settings.openlane_pdk_host_path: {
            "bind": _settings.openlane_pdk_mount_path,
            "mode": "ro",
        }
    }


async def _fail_job(job_id: str, *, message: str, error_message: str | None = None) -> None:
    jobs_repo.mark_finished(
        job_id,
        status=JobStatus.FAILED,
        exit_code=-1,
        error_message=error_message or message,
    )
    await broker.publish(job_id, "error", {"message": message})
    await broker.publish(
        job_id,
        "done",
        {
            "status": JobStatus.FAILED.value,
            "exit_code": -1,
            "log_object_key": None,
            "artifacts_prefix": None,
        },
    )


def _is_cancelled(job_id: str) -> bool:
    job = jobs_repo.get_job(job_id)
    return job is not None and job.status == JobStatus.CANCELLED


async def _finish_cancelled(job_id: str, *, message: str) -> None:
    jobs_repo.mark_finished(
        job_id,
        status=JobStatus.CANCELLED,
        exit_code=130,
        error_message=message,
    )
    await broker.publish(job_id, "status", {"status": "cancelled", "message": message})
    await broker.publish(
        job_id,
        "line",
        {"stream": "system", "line": message, "ts": _now_iso()},
    )
    await broker.publish(
        job_id,
        "done",
        {
            "status": JobStatus.CANCELLED.value,
            "exit_code": 130,
            "log_object_key": None,
            "artifacts_prefix": None,
        },
    )


async def execute_job(job_id: str) -> None:
    job = jobs_repo.get_job(job_id)
    if job is None:
        return

    spec = get_tool(job.action)
    if spec is None:
        await _fail_job(job_id, message=f"unknown action: {job.action}")
        await broker.close(job_id)
        return

    workdir = _workspace_dir(job_id)
    log_path = _log_path(job_id)
    artifacts_prefix = f"{_settings.jobs_artifacts_prefix}/{job_id}"

    sem = _get_semaphore()
    # _value private; "queued" mesajı için bilgilendirme — kritik değil.
    if sem.locked() or getattr(sem, "_value", 1) <= 0:
        await broker.publish(
            job_id,
            "status",
            {"status": "queued", "message": "Sırada — eşzamanlılık limiti"},
        )

    async with sem:
        try:
            if _is_cancelled(job_id):
                return

            os.makedirs(workdir, exist_ok=True)
            await broker.publish(
                job_id,
                "status",
                {"status": "preparing", "message": "Workspace'ten proje dosyaları indiriliyor"},
            )

            try:
                downloaded = await asyncio.to_thread(
                    storage.download_prefix,
                    job.project_id,
                    "",
                    workdir,
                    exclude_prefixes=[f"{_settings.jobs_artifacts_prefix}/"],
                )
            except Exception as e:  # noqa: BLE001
                await _fail_job(
                    job_id,
                    message=f"dosya indirme hatası: {e}",
                    error_message=f"file fetch failed: {e}",
                )
                return

            if not downloaded and _needs_workspace_files(spec):
                await _fail_job(job_id, message="Proje workspace'inde kopyalanacak dosya yok.")
                return

            if spec.requires_verilog:
                has_verilog = any(path.endswith(".v") for path in downloaded)
                if not has_verilog:
                    await _fail_job(job_id, message="Proje workspace'inde .v dosyası bulunamadı.")
                    return

            if spec.requires_config and not _has_config_file(downloaded):
                await _fail_job(
                    job_id,
                    message="Proje workspace'inde config.json veya config.tcl bulunamadı.",
                )
                return

            await broker.publish(
                job_id,
                "status",
                {"status": "running", "message": f"{len(downloaded)} dosya hazırlandı"},
            )

            command = _job_command(job, spec)

            if _is_cancelled(job_id):
                return

            await broker.publish(
                job_id,
                "status",
                {
                    "status": "running",
                    "message": f"Runner hazırlanıyor ({spec.image})…",
                },
            )

            # Container oluştur (Docker SDK bloklayıcı — event loop'u kilitlemesin)
            try:
                container = await asyncio.to_thread(
                    create_container,
                    spec.image,
                    command,
                    workdir,
                    env=_runner_env(spec),
                    extra_volumes=_runner_extra_volumes(spec),
                )
            except Exception as e:  # noqa: BLE001
                await _fail_job(
                    job_id,
                    message=f"container oluşturulamadı: {e}",
                    error_message=f"container create failed: {e}",
                )
                return

            jobs_repo.mark_started(job_id, container_id=container.id)
            await broker.publish(
                job_id, "status", {"status": "running", "container_id": container.id}
            )

            # stream + log dosyası
            with open(log_path, "w", encoding="utf-8", buffering=1) as log_file:
                log_file.write(
                    f"# job_id={job_id}\n# action={job.action}\n# image={job.image}\n"
                    f"# cmd={command}\n# started_at={_now_iso()}\n\n"
                )
                try:
                    async for line in stream_container(container):
                        if _is_cancelled(job_id):
                            interrupt_container_by_id(container.id, signal="SIGINT")
                            break
                        formatted = f"[{line.stream}] {line.line}"
                        log_file.write(formatted + "\n")
                        await broker.publish(
                            job_id,
                            "line",
                            {"stream": line.stream, "line": line.line, "ts": _now_iso()},
                        )
                except Exception as e:  # noqa: BLE001
                    log_file.write(f"# stream error: {e}\n")
                    await broker.publish(job_id, "error", {"message": f"stream hatası: {e}"})

                exit_code = await wait_container(container, timeout=_settings.runner_timeout_seconds)
                log_file.write(f"\n# exit_code={exit_code}\n# finished_at={_now_iso()}\n")

            remove_container(container)

            if _is_cancelled(job_id):
                return

            # Final status
            if exit_code == 0:
                final_status = JobStatus.DONE
            else:
                final_status = JobStatus.FAILED

            # Log upload
            log_object_key: Optional[str] = None
            try:
                log_object_key = f"{artifacts_prefix}/log.txt"
                storage.upload_file(job.project_id, log_object_key, log_path, content_type="text/plain")
            except Exception as e:  # noqa: BLE001
                await broker.publish(job_id, "error", {"message": f"log yüklenemedi: {e}"})
                log_object_key = None

            # Artefakt upload
            uploaded_prefix: Optional[str] = None
            try:
                uploaded = storage.upload_dir(job.project_id, f"{artifacts_prefix}/artifacts", workdir)
                if uploaded:
                    uploaded_prefix = f"{artifacts_prefix}/artifacts"
            except Exception as e:  # noqa: BLE001
                await broker.publish(job_id, "error", {"message": f"artefaktlar yüklenemedi: {e}"})

            jobs_repo.mark_finished(
                job_id,
                status=final_status,
                exit_code=exit_code,
                log_object_key=log_object_key,
                artifacts_prefix=uploaded_prefix,
            )

            await broker.publish(
                job_id,
                "done",
                {
                    "status": final_status.value,
                    "exit_code": exit_code,
                    "log_object_key": log_object_key,
                    "artifacts_prefix": uploaded_prefix,
                },
            )

        finally:
            try:
                shutil.rmtree(_job_root(job_id), ignore_errors=True)
            except Exception:
                pass

            await broker.close(job_id)
            # Topic kalsın — ring buffer geç gelen subscriber'lar için useful.
            # Kalıcı temizleme: gelecekte periyodik bir TTL job'u.


async def cancel_job(job_id: str) -> bool:
    job = jobs_repo.get_job(job_id)
    if not job:
        return False
    if job.status not in (JobStatus.RUNNING, JobStatus.QUEUED):
        return False

    if job.container_id:
        interrupt_container_by_id(job.container_id, signal="SIGINT")

    message = "İşlem iptal edildi (SIGINT / Ctrl+C)."
    await _finish_cancelled(job_id, message=message)
    return True
