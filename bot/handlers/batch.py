from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import List

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from ..downloader import extract_metadata, pick_format
from ..keyboards import batch_confirmation_keyboard, batch_status_keyboard
from ..queues import Job, JobStatus, get_queue_instance
from ..utils import build_suggested_name, queue_job

router = Router()


@dataclass(slots=True)
class BatchEntry:
    url: str
    quality: str | None
    name: str | None


@dataclass(slots=True)
class PendingBatch:
    batch_id: str
    user_id: int
    chat_id: int
    entries: List[BatchEntry]
    invalid: List[str]
    message_id: int | None = None


awaiting_batch_input: set[int] = set()
pending_batches: dict[str, PendingBatch] = {}
last_batch_by_user: dict[int, str] = {}

_ALLOWED_QUALITIES = {"1080p", "720p", "480p", "audio128", "audio192"}


@router.message(Command("batch"))
async def cmd_batch(message: Message) -> None:
    awaiting_batch_input.add(message.from_user.id)
    await message.answer(
        "Send each link on a new line in the format:\n"
        "URL | QUALITY | OPTIONAL NAME\n\n"
        "Example:\nhttps://youtu.be/abc | 720p | Lecture 01",
    )


@router.message(F.text, F.from_user.func(lambda u: u.id in awaiting_batch_input))
async def handle_batch_text(message: Message) -> None:
    awaiting_batch_input.discard(message.from_user.id)
    lines = [line.strip() for line in message.text.splitlines() if line.strip()]
    valid: list[BatchEntry] = []
    invalid: list[str] = []
    for line in lines:
        parts = [part.strip() for part in line.split("|")]
        if not parts:
            continue
        url = parts[0]
        if not url.lower().startswith("http"):
            invalid.append(line)
            continue
        quality = parts[1].lower() if len(parts) > 1 and parts[1] else None
        if quality and quality not in _ALLOWED_QUALITIES:
            invalid.append(line)
            continue
        name = parts[2] if len(parts) > 2 and parts[2] else None
        valid.append(BatchEntry(url=url, quality=quality, name=name))

    if not valid:
        await message.answer("No valid entries found. Please try again with the correct format.")
        return

    batch_id = uuid.uuid4().hex
    pending = PendingBatch(
        batch_id=batch_id,
        user_id=message.from_user.id,
        chat_id=message.chat.id,
        entries=valid,
        invalid=invalid,
    )
    pending_batches[batch_id] = pending
    last_batch_by_user[message.from_user.id] = batch_id

    summary = f"Received {len(lines)} lines: {len(valid)} valid, {len(invalid)} invalid."
    if invalid:
        summary += "\nInvalid examples:\n" + "\n".join(invalid[:3])

    reply = await message.answer(summary, reply_markup=batch_confirmation_keyboard(batch_id).as_markup())
    pending.message_id = reply.message_id


@router.callback_query(F.data.startswith("batch:start:"))
async def handle_batch_start(callback: CallbackQuery) -> None:
    batch_id = callback.data.split(":", 2)[-1]
    pending = pending_batches.pop(batch_id, None)
    if not pending:
        await callback.answer("Batch expired", show_alert=True)
        return
    queue = get_queue_instance()
    created = 0
    for entry in pending.entries:
        if not queue.can_enqueue(callback.from_user.id):
            break
        try:
            metadata = await extract_metadata(entry.url)
        except Exception:  # noqa: BLE001
            await callback.message.answer(f"Failed to fetch metadata for {entry.url}")
            continue
        option = pick_format(metadata, entry.quality)
        job = Job(
            chat_id=pending.chat_id,
            user_id=pending.user_id,
            url=entry.url,
            metadata=metadata,
            format_option=option,
            batch_id=batch_id,
            custom_name=(entry.name if entry.name else build_suggested_name(metadata, pending.user_id)),
        )
        await queue_job(job, pending.chat_id, callback.message.bot)
        created += 1
    await callback.answer("Batch started")
    await callback.message.edit_text(f"Batch queued {created} jobs.")


@router.callback_query(F.data.startswith("batch:cancel:"))
async def handle_batch_cancel(callback: CallbackQuery) -> None:
    batch_id = callback.data.split(":", 2)[-1]
    pending = pending_batches.pop(batch_id, None)
    queue = get_queue_instance()
    if pending:
        await callback.message.edit_text("Batch cancelled")
        await callback.answer("Cancelled")
        return
    await queue.cancel_batch(batch_id, notify=True)
    await callback.answer("Remaining jobs cancelled")


@router.message(Command("batch_status"))
async def cmd_batch_status(message: Message) -> None:
    batch_id = last_batch_by_user.get(message.from_user.id)
    if not batch_id:
        await message.answer("No batch recorded yet.")
        return
    queue = get_queue_instance()
    stats = queue.get_batch_stats(batch_id)
    text = (
        f"Batch {batch_id}\n"
        f"Total: {stats['total']}\n"
        f"Queued: {stats[JobStatus.QUEUED]}\n"
        f"Downloading: {stats[JobStatus.DOWNLOADING]}\n"
        f"Uploading: {stats[JobStatus.UPLOADING]}\n"
        f"Done: {stats[JobStatus.DONE]}\n"
        f"Failed: {stats[JobStatus.FAILED]}\n"
        f"Cancelled: {stats[JobStatus.CANCELLED]}"
    )
    await message.answer(text, reply_markup=batch_status_keyboard(batch_id).as_markup())


@router.callback_query(F.data.startswith("batch:failed:"))
async def handle_batch_failed(callback: CallbackQuery) -> None:
    batch_id = callback.data.split(":", 2)[-1]
    queue = get_queue_instance()
    failed_jobs = queue.get_batch_jobs(batch_id, status=JobStatus.FAILED)
    if not failed_jobs:
        await callback.answer("No failed jobs")
        return
    details = "\n".join(f"• {job.url} - {job.last_error or 'Unknown error'}" for job in failed_jobs[:10])
    await callback.message.answer(f"Failed jobs:\n{details}")
    await callback.answer()
