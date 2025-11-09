from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from ..keyboards import naming_template_keyboard
from ..state import settings_store

router = Router()


def _settings_summary(user_id: int) -> str:
    settings = settings_store.get(user_id)
    return (
        f"Naming template: <code>{settings.naming_template}</code>\n"
        f"Video send as document: {'Yes' if settings.video_send_as_document else 'No'}\n"
        f"Name mode: {settings.name_mode}"
    )


@router.message(Command("settings"))
async def cmd_settings(message: Message) -> None:
    summary = _settings_summary(message.from_user.id)
    await message.answer(
        "⚙️ <b>Your settings</b>\n" + summary,
        reply_markup=naming_template_keyboard(settings_store.get(message.from_user.id).naming_template).as_markup(),
    )


@router.callback_query(F.data == "settings:template")
async def cb_template(callback: CallbackQuery) -> None:
    settings = settings_store.cycle_template(callback.from_user.id)
    await callback.message.edit_text(
        "⚙️ <b>Your settings</b>\n" + _settings_summary(callback.from_user.id),
        reply_markup=naming_template_keyboard(settings.naming_template).as_markup(),
    )
    await callback.answer("Template updated")


@router.callback_query(F.data == "settings:send_type")
async def cb_send_type(callback: CallbackQuery) -> None:
    settings = settings_store.toggle_send_type(callback.from_user.id)
    await callback.message.edit_text(
        "⚙️ <b>Your settings</b>\n" + _settings_summary(callback.from_user.id),
        reply_markup=naming_template_keyboard(settings.naming_template).as_markup(),
    )
    await callback.answer("Video send type updated")


@router.callback_query(F.data == "settings:name_mode")
async def cb_name_mode(callback: CallbackQuery) -> None:
    settings = settings_store.toggle_name_mode(callback.from_user.id)
    await callback.message.edit_text(
        "⚙️ <b>Your settings</b>\n" + _settings_summary(callback.from_user.id),
        reply_markup=naming_template_keyboard(settings.naming_template).as_markup(),
    )
    await callback.answer("Name mode updated")
