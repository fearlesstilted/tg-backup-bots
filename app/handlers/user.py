from __future__ import annotations

from aiogram import Router, F
from aiogram.filters import CommandStart, CommandObject
from aiogram.types import CallbackQuery, Message

from ..config import Settings, is_valid_segment
from ..db import Database
from ..keyboards import optin_keyboard
from ..services import users as users_svc

OPTIN_TEXT = (
    "Привет! Нажмите кнопку ниже, чтобы подтвердить подписку. "
    "Так мы сможем прислать ссылку и не потеряем связь."
)


async def cmd_start(
    message: Message,
    command: CommandObject,
    db: Database,
    settings: Settings,
    bot_kind: str,
) -> None:
    arg = (command.args or "").strip()
    segment = arg if is_valid_segment(bot_kind, arg) else "unknown"

    user = message.from_user
    await users_svc.upsert_user(
        db,
        telegram_id=user.id,
        bot_kind=bot_kind,
        segment=segment,
        username=user.username,
        first_name=user.first_name,
        language_code=user.language_code,
    )

    if segment == "unknown":
        await message.answer(
            "Привет! Похоже, ссылка пришла без параметра. "
            "Зайдите по корректной ссылке, чтобы получить доступ."
        )
        return

    await message.answer(OPTIN_TEXT, reply_markup=optin_keyboard(segment))


async def cb_optin(
    cb: CallbackQuery,
    db: Database,
    settings: Settings,
    bot_kind: str,
) -> None:
    segment = cb.data.split(":", 1)[1]
    if not is_valid_segment(bot_kind, segment):
        await cb.answer("Сегмент недоступен.", show_alert=True)
        return

    await users_svc.set_opted_in(
        db, telegram_id=cb.from_user.id, bot_kind=bot_kind, segment=segment
    )

    link = settings.segment_links.get(segment)
    if link:
        body = f"Спасибо! Вот ваша ссылка:\n{link}"
    else:
        body = "Спасибо! Подписка подтверждена (тестовый сегмент)."

    try:
        await cb.message.edit_text(body)
    except Exception:
        await cb.message.answer(body)
    await cb.answer()


def build_router() -> Router:
    r = Router(name="user")
    r.message.register(cmd_start, CommandStart())
    r.callback_query.register(cb_optin, F.data.startswith("optin:"))
    return r
