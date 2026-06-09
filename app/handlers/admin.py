from __future__ import annotations

import asyncio
import logging
import secrets
import time

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from ..config import SEGMENTS_BY_BOT, Settings, is_valid_segment
from ..db import Database
from ..keyboards import (
    BTN_BROADCAST_FOREIGN,
    BTN_BROADCAST_RU,
    BTN_HELP,
    BTN_LAST,
    BTN_STATS,
    admin_menu_keyboard,
    broadcast_confirm_keyboard,
)
from ..services import broadcasts as bcast_svc
from ..services import users as users_svc

log = logging.getLogger(__name__)


class BroadcastCompose(StatesGroup):
    awaiting_text = State()


class TestCompose(StatesGroup):
    awaiting_text = State()


# In-memory pending broadcasts keyed by short token; admin sessions are short-lived.
_pending: dict[str, dict] = {}
_background_tasks: set[asyncio.Task] = set()
PENDING_TTL_SEC = 3600
BACKGROUND_SHUTDOWN_TIMEOUT_SEC = 15.0


def _segment_for_button(bot_kind: str, button_text: str) -> str | None:
    if bot_kind == "reviews":
        mapping = {
            BTN_BROADCAST_RU: "ru_reviews",
            BTN_BROADCAST_FOREIGN: "foreign_reviews",
        }
    else:
        mapping = {
            BTN_BROADCAST_RU: "ru_private",
            BTN_BROADCAST_FOREIGN: "foreign_private",
        }
    return mapping.get(button_text)


def _sweep_pending(now: float | None = None) -> None:
    current = time.time() if now is None else now
    expired = [
        token
        for token, pending in _pending.items()
        if current - float(pending.get("created_at", 0)) > PENDING_TTL_SEC
    ]
    for token in expired:
        _pending.pop(token, None)


def _start_background_task(coro) -> None:
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


async def _run_broadcast_task(bot: Bot, db_path: str, broadcast_id: int) -> None:
    broadcast_db = await Database.connect(db_path)

    async def sender(chat_id: int, text: str) -> None:
        await bot.send_message(chat_id, text)

    try:
        await bcast_svc.run_broadcast(sender, broadcast_db, broadcast_id)
    finally:
        await broadcast_db.close()


async def shutdown_background_tasks(db: Database) -> None:
    _sweep_pending()
    if not _background_tasks:
        return
    await db.mark_stale_broadcasts_interrupted()
    done, pending = await asyncio.wait(
        set(_background_tasks),
        timeout=BACKGROUND_SHUTDOWN_TIMEOUT_SEC,
    )
    for task in done:
        try:
            task.result()
        except Exception:
            log.exception("Background broadcast task failed during shutdown.")
    for task in pending:
        task.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)


async def cmd_stats(message: Message, db: Database, bot_kind: str) -> None:
    rows = await users_svc.stats_by_segment(db, bot_kind)
    if not rows:
        await message.answer(f"[{bot_kind}] нет пользователей.")
        return
    lines = [f"📊 Stats [{bot_kind}]"]
    for r in rows:
        lines.append(
            f"• {r['segment']}: total={r['total']} optin={r['opted_in']} active={r['active']}"
        )
    await message.answer("\n".join(lines))


async def cmd_menu(message: Message, bot_kind: str) -> None:
    await message.answer(
        f"Админ-меню [{bot_kind}]. Выберите действие кнопкой ниже.",
        reply_markup=admin_menu_keyboard(),
    )


async def cmd_help(message: Message, bot_kind: str) -> None:
    valid = sorted(s for s in SEGMENTS_BY_BOT.get(bot_kind, frozenset()) if s != "test")
    await message.answer(
        "Доступные действия:\n"
        "• 📊 Статистика — пользователи по сегментам\n"
        "• 📜 Последние — последние рассылки\n"
        "• 📣 Рассылка RU / Foreign — начать рассылку\n\n"
        "Команды тоже работают:\n"
        f"• /broadcast SEGMENT, где SEGMENT: {', '.join(valid)}\n"
        "• /broadcast_status ID\n"
        "• /stop_broadcast ID\n"
        "• /test SEGMENT\n",
        reply_markup=admin_menu_keyboard(),
    )


async def cmd_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Действие отменено.", reply_markup=admin_menu_keyboard())


async def cmd_last(message: Message, db: Database, bot_kind: str) -> None:
    rows = await bcast_svc.list_recent(db, bot_kind, limit=10)
    if not rows:
        await message.answer("Рассылок ещё не было.")
        return
    lines = [f"📜 Последние рассылки [{bot_kind}]"]
    for r in rows:
        lines.append(
            f"#{r['id']} {r['segment']} {r['status']} "
            f"sent={r['sent']}/{r['total']} fail={r['failed']} blk={r['blocked']} "
            f"({r['created_at']})"
        )
    await message.answer("\n".join(lines))


async def cmd_broadcast_status(
    message: Message, command: CommandObject, db: Database, bot_kind: str
) -> None:
    if not command.args or not command.args.strip().isdigit():
        await message.answer("Использование: /broadcast_status ID")
        return
    b = await bcast_svc.get_broadcast(
        db, int(command.args.strip()), bot_kind=bot_kind
    )
    if not b:
        await message.answer("Не найдено.")
        return
    await message.answer(
        f"#{b['id']} [{b['bot_kind']}/{b['segment']}] {b['status']}\n"
        f"sent={b['sent']}/{b['total']} failed={b['failed']} blocked={b['blocked']}\n"
        f"created={b['created_at']} finished={b['finished_at'] or '-'}"
    )


async def cmd_stop_broadcast(
    message: Message, command: CommandObject, db: Database, bot_kind: str
) -> None:
    if not command.args or not command.args.strip().isdigit():
        await message.answer("Использование: /stop_broadcast ID")
        return
    ok = await bcast_svc.request_stop(
        db, int(command.args.strip()), bot_kind=bot_kind
    )
    await message.answer("Остановка запрошена." if ok else "Не идёт или уже завершена.")


async def _start_broadcast_flow(
    message: Message,
    state: FSMContext,
    bot_kind: str,
    segment: str,
) -> None:
    if (not is_valid_segment(bot_kind, segment)) or segment == "test":
        valid = sorted(s for s in SEGMENTS_BY_BOT.get(bot_kind, frozenset()) if s != "test")
        await message.answer(
            f"Использование: /broadcast SEGMENT. Допустимо: {', '.join(valid)}"
        )
        return
    await state.set_state(BroadcastCompose.awaiting_text)
    await state.update_data(segment=segment)
    await message.answer(f"Пришлите текст рассылки для сегмента «{segment}».")


async def cmd_broadcast(
    message: Message,
    command: CommandObject,
    state: FSMContext,
    bot_kind: str,
) -> None:
    await _start_broadcast_flow(
        message, state, bot_kind, (command.args or "").strip()
    )


async def button_broadcast(
    message: Message,
    state: FSMContext,
    bot_kind: str,
) -> None:
    segment = _segment_for_button(bot_kind, message.text or "")
    if not segment:
        await message.answer("Неизвестная кнопка.", reply_markup=admin_menu_keyboard())
        return
    await _start_broadcast_flow(message, state, bot_kind, segment)


async def broadcast_text(
    message: Message,
    state: FSMContext,
    db: Database,
    bot_kind: str,
) -> None:
    _sweep_pending()
    data = await state.get_data()
    segment = data["segment"]
    text = message.html_text or message.text

    total = await bcast_svc.count_recipients(db, bot_kind=bot_kind, segment=segment)

    token = secrets.token_urlsafe(8)
    _pending[token] = {
        "admin_id": message.from_user.id,
        "bot_kind": bot_kind,
        "segment": segment,
        "text": text,
        "total": total,
        "created_at": time.time(),
    }
    await state.clear()

    await message.answer(
        f"🔎 Превью [{bot_kind}/{segment}]\nПолучателей: {total}\n\n———\n{text}",
        reply_markup=broadcast_confirm_keyboard(token),
    )


async def cb_broadcast(
    cb: CallbackQuery,
    bot: Bot,
    db: Database,
) -> None:
    parts = (cb.data or "").split(":", 2)
    if len(parts) != 3:
        await cb.answer("Bad request.", show_alert=True)
        return

    _, action, token = parts
    pending = _pending.get(token)
    if not pending or pending["admin_id"] != cb.from_user.id:
        await cb.answer("Сессия истекла или не ваша.", show_alert=True)
        return
    if time.time() - float(pending.get("created_at", 0)) > PENDING_TTL_SEC:
        _pending.pop(token, None)
        await cb.answer("Сессия рассылки устарела.", show_alert=True)
        try:
            await cb.message.edit_text("Сессия рассылки устарела. Запустите /broadcast заново.")
        except Exception:
            pass
        return

    if action == "cancel":
        _pending.pop(token, None)
        await cb.message.edit_text("Отменено.")
        await cb.answer()
        return

    if action == "dryrun":
        await cb.answer()
        await cb.message.answer(
            f"Dry-run: было бы отправлено {pending['total']} сообщений в "
            f"{pending['bot_kind']}/{pending['segment']}. Ничего не отправлено."
        )
        return

    if action == "confirm":
        _pending.pop(token, None)
        broadcast_id = await bcast_svc.create_broadcast(
            db,
            bot_kind=pending["bot_kind"],
            segment=pending["segment"],
            text=pending["text"],
            created_by=cb.from_user.id,
            total=pending["total"],
        )
        _start_background_task(
            _run_broadcast_task(bot, db.path, broadcast_id)
        )
        await cb.message.edit_text(
            f"🚀 Рассылка #{broadcast_id} запущена. "
            f"Статус: /broadcast_status {broadcast_id}"
        )
        await cb.answer()


async def cmd_test(
    message: Message,
    command: CommandObject,
    state: FSMContext,
    bot_kind: str,
) -> None:
    segment = (command.args or "").strip()
    if not is_valid_segment(bot_kind, segment):
        await message.answer(
            f"Использование: /test SEGMENT. Допустимо: "
            f"{', '.join(sorted(SEGMENTS_BY_BOT.get(bot_kind, frozenset())))}"
        )
        return
    await state.set_state(TestCompose.awaiting_text)
    await state.update_data(segment=segment)
    await message.answer("Пришлите текст — отправлю только вам.")


async def test_text(message: Message, state: FSMContext, bot: Bot) -> None:
    text = message.html_text or message.text
    await state.clear()
    await bot.send_message(message.from_user.id, text)
    await message.answer("✅ Тестовое сообщение отправлено вам.")


def build_router(settings: Settings) -> Router:
    r = Router(name="admin")
    admin_ids = settings.admin_ids

    def _is_admin_msg(message: Message) -> bool:
        return message.from_user is not None and message.from_user.id in admin_ids

    def _is_admin_cb(cb: CallbackQuery) -> bool:
        return cb.from_user is not None and cb.from_user.id in admin_ids

    r.message.filter(_is_admin_msg)
    r.callback_query.filter(_is_admin_cb)

    r.message.register(cmd_menu, Command("menu"))
    r.message.register(cmd_help, Command("help"))
    r.message.register(cmd_help, F.text == BTN_HELP)
    r.message.register(cmd_cancel, Command("cancel"))
    r.message.register(cmd_stats, Command("stats"))
    r.message.register(cmd_stats, F.text == BTN_STATS)
    r.message.register(cmd_last, Command("last"))
    r.message.register(cmd_last, F.text == BTN_LAST)
    r.message.register(cmd_broadcast_status, Command("broadcast_status"))
    r.message.register(cmd_stop_broadcast, Command("stop_broadcast"))
    r.message.register(cmd_broadcast, Command("broadcast"))
    r.message.register(
        button_broadcast,
        F.text.in_({BTN_BROADCAST_RU, BTN_BROADCAST_FOREIGN}),
    )
    r.message.register(cmd_test, Command("test"))
    r.message.register(broadcast_text, BroadcastCompose.awaiting_text, F.text)
    r.message.register(test_text, TestCompose.awaiting_text, F.text)
    r.callback_query.register(cb_broadcast, F.data.startswith("bcast:"))
    return r
