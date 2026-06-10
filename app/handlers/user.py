from __future__ import annotations

import logging

from aiogram import Router, F
from aiogram.filters import Command, CommandStart, CommandObject
from aiogram.types import CallbackQuery, Message

from ..access_tokens import AccessTokenError, verify_access_token
from ..config import Settings, is_valid_segment
from ..db import Database
from ..keyboards import optin_keyboard
from ..services import users as users_svc

REVIEWS_WELCOME_RU = (
    "Добро пожаловать в Shmali отзывы! 👋 Здесь наше сообщество делится "
    "реальным опытом с продуктами Shmali. Читайте честные отзывы от клиентов "
    "как ты — узнайте, что работает и что люди любят. Для нас прозрачность — "
    "это всё.\n\n"
    "Нажмите кнопку ниже, чтобы получить ссылку."
)
REVIEWS_WELCOME_EN = (
    "Welcome to Shmali Reviews! 👋 This is where our community shares real "
    "experiences with Shmali products. Read honest feedback from customers "
    "like you — see what works, what people love, and make informed choices. "
    "We’re all about transparency here.\n\n"
    "Tap the button below to receive your link."
)
PRIVATE_WELCOME_RU = (
    "Добро пожаловать в Shmali VIP Members Only! 🌿 Вы получили доступ к "
    "закрытому чату нашего сообщества. Здесь вы общаетесь с другими клиентами "
    "Shmali, получаете доступ к новым продуктам раньше всех и наслаждаетесь "
    "эксклюзивными привилегиями. Теперь вы в нашем внутреннем кругу. 🤝\n\n"
    "Нажмите кнопку ниже, чтобы получить ссылку."
)
PRIVATE_WELCOME_EN = (
    "Welcome to Shmali VIP Members Only! 🌿 You’ve unlocked members-only "
    "access to our exclusive community chat. Here you’ll connect directly "
    "with fellow Shmali customers, get early access to new drops, and enjoy "
    "VIP-only perks. You’re part of the inner circle now.\n\n"
    "Tap the button below to receive your link."
)

UNKNOWN_TEXT_RU = (
    "Привет! Похоже, ссылка открыта без нужного параметра. "
    "Пожалуйста, откройте бота по кнопке на сайте или по закреплённой ссылке в чате."
)
UNKNOWN_TEXT_EN = (
    "Hi! This link was opened without the required parameter. "
    "Please open the bot from the website button or from the pinned chat link."
)


def _is_ru_segment(segment: str, language_code: str | None = None) -> bool:
    return segment.startswith("ru_") or (segment == "unknown" and language_code == "ru")


def _optin_text(
    bot_kind: str, segment: str, language_code: str | None = None
) -> str:
    is_ru = _is_ru_segment(segment, language_code)
    if bot_kind == "private":
        return PRIVATE_WELCOME_RU if is_ru else PRIVATE_WELCOME_EN
    return REVIEWS_WELCOME_RU if is_ru else REVIEWS_WELCOME_EN


def _unknown_text(language_code: str | None = None) -> str:
    return UNKNOWN_TEXT_RU if language_code == "ru" else UNKNOWN_TEXT_EN

log = logging.getLogger(__name__)


def resolve_start_segment(
    bot_kind: str,
    arg: str,
    settings: Settings,
    *,
    now: int | None = None,
) -> str:
    if bot_kind == "private" and arg and arg != "test":
        if not settings.private_require_access_token and is_valid_segment(bot_kind, arg):
            return arg
        if settings.private_access_secret:
            try:
                return verify_access_token(
                    arg, settings.private_access_secret, now=now
                )
            except AccessTokenError:
                return "unknown"
        return "unknown"

    if is_valid_segment(bot_kind, arg):
        return arg
    return "unknown"


async def cmd_start(
    message: Message,
    command: CommandObject,
    db: Database,
    settings: Settings,
    bot_kind: str,
) -> None:
    arg = (command.args or "").strip()
    segment = resolve_start_segment(bot_kind, arg, settings)

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
        await message.answer(_unknown_text(user.language_code))
        return

    await message.answer(
        _optin_text(bot_kind, segment, user.language_code),
        reply_markup=optin_keyboard(segment),
    )


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

    if (
        bot_kind == "private"
        and settings.private_require_access_token
        and segment != "test"
    ):
        existing = await users_svc.get_user(
            db, telegram_id=cb.from_user.id, bot_kind=bot_kind, segment=segment
        )
        if not existing:
            await cb.answer(
                "Откройте ссылку из профиля на сайте ещё раз.",
                show_alert=True,
            )
            return

    updated = await users_svc.set_opted_in(
        db, telegram_id=cb.from_user.id, bot_kind=bot_kind, segment=segment
    )
    if not updated:
        await cb.answer(
            "Сессия не найдена. Откройте ссылку на бота ещё раз.",
            show_alert=True,
        )
        return

    link = settings.segment_links.get(segment)
    if link:
        if _is_ru_segment(segment):
            body = f"Спасибо! Вот ваша ссылка:\n{link}"
        else:
            body = f"Thank you! Here is your link:\n{link}"
    else:
        body = "Спасибо! Подписка подтверждена (тестовый сегмент)."

    try:
        await cb.message.edit_text(body)
    except Exception as e:  # noqa: BLE001
        log.warning("Failed to edit opt-in message: %r", e)
        try:
            await cb.message.answer(body)
        except Exception as answer_error:  # noqa: BLE001
            log.exception("Failed to send opt-in fallback: %r", answer_error)
            await cb.answer("Не удалось отправить ссылку. Попробуйте ещё раз.", show_alert=True)
            return
    await cb.answer()


async def cmd_stop(message: Message, db: Database, bot_kind: str) -> None:
    count = await users_svc.opt_out(
        db, telegram_id=message.from_user.id, bot_kind=bot_kind
    )
    if count:
        await message.answer("Вы отписались от emergency-рассылки.")
    else:
        await message.answer("Активной подписки не найдено.")


def build_router() -> Router:
    r = Router(name="user")
    r.message.register(cmd_start, CommandStart())
    r.message.register(cmd_stop, Command("stop"))
    r.callback_query.register(cb_optin, F.data.startswith("optin:"))
    return r
