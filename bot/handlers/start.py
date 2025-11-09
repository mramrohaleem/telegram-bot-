from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    text = (
        "👋 Welcome!\n\n"
        "Send me a supported media link to download it.\n"
        "Send an audio file to rename it or change its cover.\n"
        "Use /batch for multiple links and /batch_status to check progress."
    )
    await message.answer(text)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    text = (
        "ℹ️ <b>How to use</b>\n\n"
        "<b>Single link:</b> send a URL, choose quality, wait for delivery.\n"
        "<b>Audio edit:</b> send an audio file and choose rename/cover options.\n"
        "<b>Batch:</b> /batch to provide many links at once.\n\n"
        "Limits: Telegram max upload size applies (approx 2GB)."
    )
    await message.answer(text)
