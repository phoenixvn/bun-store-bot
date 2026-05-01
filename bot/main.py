from __future__ import annotations

import asyncio
import logging

import uvicorn
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot.api_app import app as api_app
from bot.bot_instance import set_bot
from bot.config import settings
from bot.handlers import admin, api, deposit, language, product, profile, shop, start, support
from bot.payments import bep20, ton, tron

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("bot")


async def main() -> None:
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=None),
    )
    set_bot(bot)
    dp = Dispatcher(storage=MemoryStorage())

    # admin first so /admin command beats catch-all support relay
    dp.include_router(admin.router)
    dp.include_router(start.router)
    dp.include_router(language.router)
    dp.include_router(shop.router)
    dp.include_router(product.router)
    dp.include_router(deposit.router)
    dp.include_router(profile.router)
    dp.include_router(api.router)
    # support last — has the catch-all private message bridge
    dp.include_router(support.router)

    # background pollers
    asyncio.create_task(bep20.poll_loop())
    asyncio.create_task(ton.poll_loop())
    asyncio.create_task(tron.poll_loop())

    # FastAPI sidecar
    config = uvicorn.Config(
        api_app, host=settings.api_host, port=settings.api_port, log_level="warning"
    )
    server = uvicorn.Server(config)
    asyncio.create_task(server.serve())

    log.info("Bot starting…")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
