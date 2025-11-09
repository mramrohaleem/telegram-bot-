from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import FSInputFile

from .config import Settings
from .downloader import DownloadResult, FormatOption, MediaMetadata, download_media, sanitize_filename
from .state import settings_store

LOGGER = logging.getLogger(__name__)


class JobStatus:
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    UPLOADING = "uploading"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(slots=True)
class Job:
    chat_id: int
    user_id: int
    url: str
    metadata: MediaMetadata
    format_option: FormatOption
    custom_name: str | None = None
    batch_id: str | None = None
    progress_message_id: int | None = None
    job_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    status: str = JobStatus.QUEUED
    progress: float = 0.0
    last_error: str | None = None
    created_at: float = field(default_factory=time.time)
    last_update_ts: float = field(default=0.0)
    cancelled: bool = False


class DownloadQueue:
    def __init__(self, bot: Bot, settings: Settings) -> None:
        self.bot = bot
        self.settings = settings
        self.queue: asyncio.Queue[Job] = asyncio.Queue()
        self.jobs: dict[str, Job] = {}
        self.user_active: dict[int, set[str]] = {}
        self.batch_jobs: dict[str, list[str]] = {}
        self._workers: list[asyncio.Task[None]] = []
        self._stop = asyncio.Event()

    def start(self) -> None:
        for _ in range(self.settings.max_concurrent_downloads):
            task = asyncio.create_task(self._worker())
            self._workers.append(task)

    async def stop(self) -> None:
        self._stop.set()
        for task in self._workers:
            task.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)

    def _register_job(self, job: Job) -> None:
        self.jobs[job.job_id] = job
        self.user_active.setdefault(job.user_id, set()).add(job.job_id)
        if job.batch_id:
            self.batch_jobs.setdefault(job.batch_id, []).append(job.job_id)

    def _unregister_job(self, job: Job) -> None:
        self.user_active.get(job.user_id, set()).discard(job.job_id)

    def can_enqueue(self, user_id: int, limit: int = 5) -> bool:
        return len(self.user_active.get(user_id, set())) < limit

    async def enqueue(self, job: Job) -> None:
        self._register_job(job)
        await self.queue.put(job)
        LOGGER.info("Enqueued job %s for user %s url=%s format=%s", job.job_id, job.user_id, job.url, job.format_option.description)

    async def cancel_job(self, job_id: str, notify: bool = True) -> None:
        job = self.jobs.get(job_id)
        if not job:
            return
        job.cancelled = True
        job.status = JobStatus.CANCELLED
        if notify and job.progress_message_id:
            try:
                await self.bot.edit_message_text(
                    chat_id=job.chat_id,
                    message_id=job.progress_message_id,
                    text="❌ Download cancelled",
                )
            except TelegramBadRequest:
                pass
        self._unregister_job(job)

    async def cancel_batch(self, batch_id: str, notify: bool = True) -> None:
        for job_id in self.batch_jobs.get(batch_id, []):
            await self.cancel_job(job_id, notify=notify)

    def get_batch_stats(self, batch_id: str) -> dict[str, int]:
        job_ids = self.batch_jobs.get(batch_id, [])
        stats = {state: 0 for state in [
            JobStatus.QUEUED,
            JobStatus.DOWNLOADING,
            JobStatus.UPLOADING,
            JobStatus.DONE,
            JobStatus.FAILED,
            JobStatus.CANCELLED,
        ]}
        for job_id in job_ids:
            job = self.jobs.get(job_id)
            if not job:
                continue
            stats[job.status] = stats.get(job.status, 0) + 1
        stats["total"] = len(job_ids)
        return stats

    def get_batch_jobs(self, batch_id: str, status: str | None = None) -> list[Job]:
        job_ids = self.batch_jobs.get(batch_id, [])
        jobs: list[Job] = []
        for job_id in job_ids:
            job = self.jobs.get(job_id)
            if not job:
                continue
            if status and job.status != status:
                continue
            jobs.append(job)
        return jobs

    async def _worker(self) -> None:
        while not self._stop.is_set():
            try:
                job = await self.queue.get()
            except asyncio.CancelledError:
                break
            try:
                if job.cancelled:
                    continue
                await self._process_job(job)
            except Exception as exc:  # noqa: BLE001
                LOGGER.exception("Job %s failed: %s", job.job_id, exc)
                job.status = JobStatus.FAILED
                job.last_error = str(exc)
                await self._send_failure(job, "Unexpected error occurred during download.")
            finally:
                self.queue.task_done()
                self._unregister_job(job)

    async def _process_job(self, job: Job) -> None:
        job.status = JobStatus.DOWNLOADING
        if job.progress_message_id:
            await self._edit_progress(job, "⬇️ Starting download...")
        download_dir = Path(self.settings.download_dir)
        progress_state = {"last_pct": 0.0, "last_update": 0.0}

        def _on_progress(data: dict[str, object]) -> None:
            if job.cancelled:
                return
            if data.get("status") != "downloading":
                return
            total = float(data.get("total_bytes", 0) or data.get("total_bytes_estimate", 0) or 0)
            downloaded = float(data.get("downloaded_bytes", 0))
            speed = float(data.get("speed", 0))
            if total <= 0:
                pct = 0.0
            else:
                pct = downloaded / total * 100
            now = time.time()
            if pct - progress_state["last_pct"] < 5 and now - progress_state["last_update"] < 3:
                return
            progress_state["last_pct"] = pct
            progress_state["last_update"] = now
            eta = data.get("eta")
            text = (
                f"⬇️ Downloading {pct:.1f}%\n"
                f"{downloaded/1024/1024:.2f} / {total/1024/1024:.2f} MB\n"
            )
            if speed:
                text += f"Speed: {speed/1024/1024:.2f} MB/s\n"
            if eta:
                text += f"ETA: {int(eta)} s"
            asyncio.create_task(self._edit_progress(job, text))

        result: DownloadResult = await download_media(
            url=job.url,
            download_dir=download_dir,
            format_id=job.format_option.format_id,
            progress_callback=_on_progress,
        )

        if job.cancelled:
            result.file_path.unlink(missing_ok=True)
            job.status = JobStatus.CANCELLED
            return

        if result.file_size > self.settings.max_file_size_bytes:
            result.file_path.unlink(missing_ok=True)
            job.status = JobStatus.FAILED
            await self._send_failure(
                job,
                f"File is too large ({result.file_size/1024/1024:.1f} MB). Limit is {self.settings.max_file_size_mb} MB.",
            )
            return

        job.status = JobStatus.UPLOADING
        if job.progress_message_id:
            await self._edit_progress(job, "⬆️ Uploading to Telegram...")

        file_name = job.custom_name or sanitize_filename(result.title)
        file_path = result.file_path
        input_file = FSInputFile(path=str(file_path), filename=f"{file_name}{file_path.suffix}")

        if result.is_audio:
            await self.bot.send_audio(chat_id=job.chat_id, audio=input_file)
        else:
            user_settings = settings_store.get(job.user_id)
            if user_settings.video_send_as_document:
                await self.bot.send_document(chat_id=job.chat_id, document=input_file)
            else:
                await self.bot.send_video(chat_id=job.chat_id, video=input_file)

        job.status = JobStatus.DONE
        if job.progress_message_id:
            await self._edit_progress(job, "✅ Download complete")

        try:
            file_path.unlink(missing_ok=True)
        except OSError:
            LOGGER.warning("Failed to delete file %s", file_path)

    async def _edit_progress(self, job: Job, text: str) -> None:
        if not job.progress_message_id:
            try:
                message = await self.bot.send_message(job.chat_id, text)
            except TelegramBadRequest:
                return
            job.progress_message_id = message.message_id
            return
        try:
            await self.bot.edit_message_text(chat_id=job.chat_id, message_id=job.progress_message_id, text=text)
        except TelegramBadRequest:
            pass

    async def _send_failure(self, job: Job, text: str) -> None:
        if job.progress_message_id:
            try:
                await self.bot.edit_message_text(chat_id=job.chat_id, message_id=job.progress_message_id, text=f"❌ {text}")
            except TelegramBadRequest:
                await self.bot.send_message(job.chat_id, f"❌ {text}")
        else:
            await self.bot.send_message(job.chat_id, f"❌ {text}")


_queue_instance: DownloadQueue | None = None


def set_queue_instance(queue: DownloadQueue) -> None:
    global _queue_instance
    _queue_instance = queue


def get_queue_instance() -> DownloadQueue:
    if _queue_instance is None:
        raise RuntimeError("Queue instance not initialised")
    return _queue_instance
