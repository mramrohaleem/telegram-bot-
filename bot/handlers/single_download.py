from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from ..downloader import MediaMetadata, extract_metadata, pick_format, sanitize_filename
from ..keyboards import name_confirmation_keyboard, quality_keyboard
from ..queues import Job, get_queue_instance
from ..state import settings_store
from ..utils import build_suggested_name, queue_job

router = Router()

_URL_RE = re.compile(r"https?://")


@dataclass(slots=True)
class PendingMetadata:
    metadata: MediaMetadata
    chat_id: int
    message_id: int
    url: str


pending_requests: dict[str, PendingMetadata] = {}
pending_name_prompts: dict[str, Job] = {}
pending_custom_names: dict[int, Job] = {}


@router.message(F.text)
async def handle_url_message(message: Message) -> None:
    if not message.text or not _URL_RE.search(message.text):
        return
    queue = get_queue_instance()
    if not queue.can_enqueue(message.from_user.id):
        await message.answer("You have too many active downloads. Please wait before adding more.")
        return
    try:
        metadata = await extract_metadata(message.text.strip())
    except Exception:  # noqa: BLE001
        await message.answer("Failed to fetch metadata for this URL. Make sure it is supported.")
        return
    if not metadata.formats:
        await message.answer("No downloadable formats were found for this URL.")
        return
    job_id = uuid.uuid4().hex
    keyboard = quality_keyboard(metadata.formats, job_id).as_markup()
    reply = await message.answer(
        "Select the quality you prefer:",
        reply_markup=keyboard,
    )
    pending_requests[job_id] = PendingMetadata(
        metadata=metadata,
        chat_id=message.chat.id,
        message_id=reply.message_id,
        url=message.text.strip(),
    )


@router.callback_query(F.data.startswith("fmt:"))
async def handle_format(callback: CallbackQuery) -> None:
    parts = callback.data.split(":", 2)
    if len(parts) != 3:
        await callback.answer("Invalid selection", show_alert=True)
        return
    _, job_id, format_id = parts
    pending = pending_requests.pop(job_id, None)
    if not pending:
        await callback.answer("This selection expired.", show_alert=True)
        return
    option = pick_format(pending.metadata, quality=None)
    for fmt in pending.metadata.formats:
        if fmt.format_id == format_id:
            option = fmt
            break
    settings = settings_store.get(callback.from_user.id)
    suggested_name = build_suggested_name(pending.metadata, callback.from_user.id)

    job = Job(
        chat_id=pending.chat_id,
        user_id=callback.from_user.id,
        url=pending.url,
        metadata=pending.metadata,
        format_option=option,
    )

    await callback.answer("Format selected")

    if settings.name_mode == "ask" and option.is_audio:
        pending_name_prompts[job.job_id] = job
        pending_custom_names[callback.from_user.id] = job
        await callback.message.edit_text(
            f"Suggested name: <b>{suggested_name}</b>",
            reply_markup=name_confirmation_keyboard(job.job_id).as_markup(),
        )
        job.custom_name = suggested_name
        return

    job.custom_name = suggested_name if option.is_audio else None
    await queue_job(job, pending.chat_id, callback.message.bot)


@router.callback_query(F.data.startswith("name:"))
async def handle_name_choice(callback: CallbackQuery) -> None:
    _, action, job_id = callback.data.split(":", 2)
    job = pending_name_prompts.get(job_id)
    if not job:
        await callback.answer("No job found", show_alert=True)
        return
    if action == "accept":
        pending_name_prompts.pop(job_id, None)
        pending_custom_names.pop(callback.from_user.id, None)
        await callback.message.edit_text("Name confirmed. Queuing job...")
        await queue_job(job, job.chat_id, callback.message.bot)
        await callback.answer("Queued")
    elif action == "custom":
        await callback.message.edit_text("Please type the custom name now.")
        await callback.answer()
    else:
        await callback.answer("Unknown choice", show_alert=True)


@router.message(F.text, F.from_user.func(lambda u: u.id in pending_custom_names))
async def handle_custom_name(message: Message) -> None:
    job = pending_custom_names.pop(message.from_user.id)
    pending_name_prompts.pop(job.job_id, None)
    job.custom_name = sanitize_filename(message.text.strip())
    await message.answer("Thanks! Added to the queue.")
    await queue_job(job, message.chat.id, message.bot)
