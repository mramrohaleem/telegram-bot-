from __future__ import annotations

from aiogram.utils.keyboard import InlineKeyboardBuilder

from .downloader import FormatOption


def quality_keyboard(options: list[FormatOption], job_id: str) -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    for option in options:
        builder.button(text=option.description, callback_data=f"fmt:{job_id}:{option.format_id}")
    builder.adjust(1)
    return builder


def naming_template_keyboard(current: str) -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    builder.button(text=f"Template: {current}", callback_data="settings:template")
    builder.button(text="Video send type", callback_data="settings:send_type")
    builder.button(text="Name mode", callback_data="settings:name_mode")
    builder.adjust(1)
    return builder


def audio_edit_keyboard() -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    builder.button(text="Rename only 📝", callback_data="audio:rename")
    builder.button(text="Change cover image 🖼", callback_data="audio:cover")
    builder.button(text="Rename + cover ✨", callback_data="audio:both")
    builder.button(text="Cancel ❌", callback_data="audio:cancel")
    builder.adjust(1)
    return builder


def name_confirmation_keyboard(job_id: str) -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    builder.button(text="Use this ✅", callback_data=f"name:accept:{job_id}")
    builder.button(text="Type custom name 📝", callback_data=f"name:custom:{job_id}")
    builder.adjust(1)
    return builder


def batch_confirmation_keyboard(batch_id: str) -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    builder.button(text="Start batch ✅", callback_data=f"batch:start:{batch_id}")
    builder.button(text="Cancel ❌", callback_data=f"batch:cancel:{batch_id}")
    builder.adjust(1)
    return builder


def batch_status_keyboard(batch_id: str) -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    builder.button(text="Show failed only", callback_data=f"batch:failed:{batch_id}")
    builder.button(text="Cancel remaining jobs", callback_data=f"batch:cancel:{batch_id}")
    builder.adjust(1)
    return builder
