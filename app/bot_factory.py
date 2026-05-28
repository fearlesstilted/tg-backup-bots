from __future__ import annotations

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from .config import Settings
from .db import Database
from .handlers import admin as admin_h
from .handlers import user as user_h


def build(
    bot_kind: str, settings: Settings, db: Database
) -> tuple[Bot, Dispatcher]:
    bot = Bot(
        token=settings.token_for(bot_kind),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    dp = Dispatcher(storage=MemoryStorage())
    # Injected into every handler via aiogram's DI.
    dp["db"] = db
    dp["settings"] = settings
    dp["bot_kind"] = bot_kind

    # Admin router first — its filter restricts to admin IDs; user router catches the rest.
    dp.include_router(admin_h.build_router(settings))
    dp.include_router(user_h.build_router())

    return bot, dp
