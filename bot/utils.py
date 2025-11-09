from __future__ import annotations

from aiogram import Bot

from .downloader import MediaMetadata, sanitize_filename
from .queues import Job, get_queue_instance
from .state import settings_store


async def queue_job(job: Job, chat_id: int, bot: Bot) -> None:
    queue = get_queue_instance()
    message = await bot.send_message(chat_id, "📥 Job queued")
    job.progress_message_id = message.message_id
    await queue.enqueue(job)


def build_suggested_name(metadata: MediaMetadata, user_id: int) -> str:
    settings = settings_store.get(user_id)
    values = {
        "title": metadata.title or "Audio",
        "uploader": metadata.uploader or "Unknown",
        "playlist": metadata.webpage_url.split("/")[-2] if "/" in metadata.webpage_url else "",
    }
    template = settings.naming_template
    name = template.format(**values)
    return sanitize_filename(name)
