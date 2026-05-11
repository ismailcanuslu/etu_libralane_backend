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
    kill_container_by_id,
    remove_container,
    stream_container,
    wait_container,
)
from app.tools_catalog import get_tool


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


async def execute_job(job_id: str) -> None:
    job = jobs_repo.get_job(job_id)
    if job is None:
        return

    spec = get_tool(job.action)
    if spec is None:
        jobs_repo.mark_finished(
            job_id,
            status=JobStatus.FAILED,
            error_message=f"unknown action: {job.action}",
        )
        await broker.publish(job_id, "error", {"message": "unknown action"})
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
            os.makedirs(workdir, exist_ok=True)
            await broker.publish(
                job_id,
                "status",
                {"status": "preparing", "message": "Workspace'ten proje dosyaları indiriliyor"},
            )

            try:
                downloaded = storage.download_prefix(
                    job.project_id,
                    "",
                    workdir,
                    exclude_prefixes=[f"{_settings.jobs_artifacts_prefix}/"],
                )
            except Exception as e:  # noqa: BLE001
                jobs_repo.mark_finished(
                    job_id, status=JobStatus.FAILED, error_message=f"file fetch failed: {e}"
                )
                await broker.publish(job_id, "error", {"message": f"dosya indirme hatası: {e}"})
                await broker.close(job_id)
                return

            if not downloaded:
                message = "Proje workspace'inde kopyalanacak dosya yok."
                jobs_repo.mark_finished(job_id, status=JobStatus.FAILED, error_message=message)
                await broker.publish(job_id, "error", {"message": message})
                await broker.close(job_id)
                return

            has_verilog = any(path.endswith(".v") for path in downloaded)
            if not has_verilog:
                message = "Proje workspace'inde .v dosyası bulunamadı."
                jobs_repo.mark_finished(job_id, status=JobStatus.FAILED, error_message=message)
                await broker.publish(job_id, "error", {"message": message})
                await broker.close(job_id)
                return

            await broker.publish(
                job_id,
                "status",
                {"status": "running", "message": f"{len(downloaded)} dosya hazırlandı"},
            )

            # Container oluştur
            try:
                container = create_container(
                    image=spec.image,
                    cmd=list(spec.cmd),
                    host_workdir=workdir,
                )
            except Exception as e:  # noqa: BLE001
                jobs_repo.mark_finished(
                    job_id, status=JobStatus.FAILED, error_message=f"container create failed: {e}"
                )
                await broker.publish(job_id, "error", {"message": f"container oluşturulamadı: {e}"})
                await broker.close(job_id)
                return

            jobs_repo.mark_started(job_id, container_id=container.id)
            await broker.publish(
                job_id, "status", {"status": "running", "container_id": container.id}
            )

            # stream + log dosyası
            with open(log_path, "w", encoding="utf-8", buffering=1) as log_file:
                log_file.write(
                    f"# job_id={job_id}\n# action={job.action}\n# image={job.image}\n"
                    f"# cmd={job.command}\n# started_at={_now_iso()}\n\n"
                )
                try:
                    async for line in stream_container(container):
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

            # Final status
            current = jobs_repo.get_job(job_id)
            if current and current.status == JobStatus.CANCELLED:
                final_status = JobStatus.CANCELLED
            elif exit_code == 0:
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

    cancelled = False
    if job.container_id:
        cancelled = kill_container_by_id(job.container_id)

    jobs_repo.update_job(job_id, status=JobStatus.CANCELLED)
    await broker.publish(job_id, "status", {"status": "cancelled"})
    return cancelled or True


def schedule_job(job_id: str) -> None:
    """FastAPI handler'larından çağrılır — async task'i background'a salar."""
    asyncio.create_task(execute_job(job_id))
