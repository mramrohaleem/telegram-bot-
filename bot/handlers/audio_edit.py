from __future__ import annotations

import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from ..audio_edit import AudioEditResult, apply_cover, apply_rename
from ..config import get_settings
from ..keyboards import audio_edit_keyboard

router = Router()


@dataclass(slots=True)
class AudioSession:
    original_path: Path
    temp_dir: Path
    stage: str = "choose"
    pending_title: str | None = None


sessions: dict[int, AudioSession] = {}


async def _download_to_path(message: Message, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if message.audio:
        file = message.audio
    elif message.voice:
        file = message.voice
    else:
        raise ValueError("Message has no audio")
    await message.bot.download(file, destination=destination)


def _cleanup(session: AudioSession) -> None:
    try:
        shutil.rmtree(session.temp_dir)
    except FileNotFoundError:
        pass


@router.message(F.audio | F.voice)
async def handle_audio(message: Message) -> None:
    settings = get_settings()
    download_dir = settings.download_dir / "audio_edits" / uuid.uuid4().hex
    download_dir.mkdir(parents=True, exist_ok=True)
    ext = ".ogg"
    if message.audio and message.audio.file_name:
        ext = Path(message.audio.file_name).suffix or ext
    destination = download_dir / f"source{ext}"
    await _download_to_path(message, destination)
    sessions[message.from_user.id] = AudioSession(original_path=destination, temp_dir=download_dir)
    await message.answer("Choose what to do with this audio:", reply_markup=audio_edit_keyboard().as_markup())


@router.callback_query(F.data.startswith("audio:"))
async def handle_audio_callback(callback: CallbackQuery) -> None:
    session = sessions.get(callback.from_user.id)
    if not session:
        await callback.answer("No audio in progress", show_alert=True)
        return
    action = callback.data.split(":", 1)[-1]
    if action == "cancel":
        _cleanup(session)
        sessions.pop(callback.from_user.id, None)
        await callback.message.edit_text("Cancelled")
        await callback.answer("Cancelled")
        return
    if action == "rename":
        session.stage = "await_title"
        await callback.message.edit_text("Send the new title for this audio.")
        await callback.answer()
    elif action == "cover":
        session.stage = "await_cover"
        await callback.message.edit_text("Send the new cover image.")
        await callback.answer()
    elif action == "both":
        session.stage = "await_title_then_cover"
        await callback.message.edit_text("Send the new title first.")
        await callback.answer()
    else:
        await callback.answer("Unknown action", show_alert=True)


async def _send_result(message: Message, result: AudioEditResult) -> None:
    await message.answer_audio(audio=result.file_path, title=result.title)


@router.message(F.text, F.from_user.func(lambda user: user.id in sessions))
async def handle_text(message: Message) -> None:
    session = sessions.get(message.from_user.id)
    if not session:
        return
    if session.stage not in {"await_title", "await_title_then_cover"}:
        return
    session.pending_title = message.text.strip()
    if session.stage == "await_title":
        result = await apply_rename(session.original_path, session.temp_dir, session.pending_title)
        await _send_result(message, result)
        _cleanup(session)
        sessions.pop(message.from_user.id, None)
    else:
        session.stage = "await_cover_after_title"
        await message.answer("Great! Now send the cover image.")


@router.message(F.photo, F.from_user.func(lambda user: user.id in sessions))
async def handle_photo(message: Message) -> None:
    session = sessions.get(message.from_user.id)
    if not session or session.stage not in {"await_cover", "await_cover_after_title"}:
        return
    cover_dir = session.temp_dir / "cover"
    cover_dir.mkdir(parents=True, exist_ok=True)
    cover_path = cover_dir / "cover.jpg"
    await message.bot.download(message.photo[-1], destination=cover_path)
    new_title = session.pending_title if session.pending_title else None
    result = await apply_cover(session.original_path, session.temp_dir, cover_path, new_title=new_title)
    await _send_result(message, result)
    _cleanup(session)
    sessions.pop(message.from_user.id, None)


@router.message(F.document, F.from_user.func(lambda user: user.id in sessions))
async def handle_document_cover(message: Message) -> None:
    session = sessions.get(message.from_user.id)
    if not session or session.stage not in {"await_cover", "await_cover_after_title"}:
        return
    cover_dir = session.temp_dir / "cover"
    cover_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(message.document.file_name or "cover.jpg").suffix or ".jpg"
    cover_path = cover_dir / f"cover{ext}"
    await message.bot.download(message.document, destination=cover_path)
    new_title = session.pending_title if session.pending_title else None
    result = await apply_cover(session.original_path, session.temp_dir, cover_path, new_title=new_title)
    await _send_result(message, result)
    _cleanup(session)
    sessions.pop(message.from_user.id, None)
