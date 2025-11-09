from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode

from .config import get_settings
from .handlers import audio_edit, batch, settings as settings_handler, single_download, start
from .queues import DownloadQueue, set_queue_instance


async def main() -> None:
    settings = get_settings()
    bot = Bot(token=settings.telegram_token, parse_mode=ParseMode.HTML)
    dp = Dispatcher()

    queue = DownloadQueue(bot, settings)
    set_queue_instance(queue)
    queue.start()

    dp.include_router(start.router)
    dp.include_router(settings_handler.router)
    dp.include_router(single_download.router)
    dp.include_router(batch.router)
    dp.include_router(audio_edit.router)

    logging.info("Bot started")
    try:
        await dp.start_polling(bot)
    finally:
        await queue.stop()


if __name__ == "__main__":
    asyncio.run(main())
