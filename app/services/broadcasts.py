from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator, Awaitable, Callable, Optional

from aiogram import Bot
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
)

from ..config import Settings
from ..db import Database

log = logging.getLogger(__name__)

BATCH_SIZE = 50
STATUS_POLL_EVERY = 50
SEND_INTERVAL_SEC = 1.0 / 18.0  # ~18 msg/s
MAX_RETRY_PER_USER = 3


async def count_recipients(db: Database, *, bot_kind: str, segment: str) -> int:
    cur = await db.conn.execute(
        "SELECT COUNT(*) FROM users "
        "WHERE bot_kind=? AND segment=? AND opted_in=1 AND is_active=1",
        (bot_kind, segment),
    )
    row = await cur.fetchone()
    return int(row[0])


async def create_broadcast(
    db: Database, *, bot_kind: str, segment: str, text: str, created_by: int, total: int
) -> int:
    cur = await db.conn.execute(
        "INSERT INTO broadcasts (bot_kind, segment, text, status, total, created_by) "
        "VALUES (?, ?, ?, 'processing', ?, ?)",
        (bot_kind, segment, text, total, created_by),
    )
    await db.conn.commit()
    return int(cur.lastrowid)


async def get_broadcast(
    db: Database, broadcast_id: int, *, bot_kind: str | None = None
) -> Optional[dict]:
    if bot_kind is None:
        cur = await db.conn.execute(
            "SELECT * FROM broadcasts WHERE id=?", (broadcast_id,)
        )
    else:
        cur = await db.conn.execute(
            "SELECT * FROM broadcasts WHERE id=? AND bot_kind=?",
            (broadcast_id, bot_kind),
        )
    row = await cur.fetchone()
    return dict(row) if row else None


async def list_recent(db: Database, bot_kind: str, limit: int = 10) -> list[dict]:
    cur = await db.conn.execute(
        "SELECT * FROM broadcasts WHERE bot_kind=? "
        "ORDER BY created_at DESC LIMIT ?",
        (bot_kind, limit),
    )
    return [dict(r) for r in await cur.fetchall()]


async def request_stop(
    db: Database, broadcast_id: int, *, bot_kind: str | None = None
) -> bool:
    if bot_kind is None:
        cur = await db.conn.execute(
            "UPDATE broadcasts SET status='stopped', finished_at=datetime('now') "
            "WHERE id=? AND status='processing'",
            (broadcast_id,),
        )
    else:
        cur = await db.conn.execute(
            "UPDATE broadcasts SET status='stopped', finished_at=datetime('now') "
            "WHERE id=? AND bot_kind=? AND status='processing'",
            (broadcast_id, bot_kind),
        )
    await db.conn.commit()
    return (cur.rowcount or 0) > 0


async def _iter_recipients(
    db: Database, *, bot_kind: str, segment: str
) -> AsyncIterator[tuple[int, int]]:
    cur = await db.conn.execute(
        "SELECT id, telegram_id FROM users "
        "WHERE bot_kind=? AND segment=? AND opted_in=1 AND is_active=1 "
        "ORDER BY id",
        (bot_kind, segment),
    )
    async for row in cur:
        yield int(row["id"]), int(row["telegram_id"])


async def _flush(
    db: Database,
    broadcast_id: int,
    batch: list[tuple[int, int, str, Optional[str]]],
    counters: dict[str, int],
    inactive_user_ids: list[int],
) -> None:
    if batch:
        await db.conn.executemany(
            "INSERT INTO broadcast_deliveries (broadcast_id, telegram_id, status, error) "
            "VALUES (?, ?, ?, ?)",
            batch,
        )
    if inactive_user_ids:
        await db.conn.executemany(
            "UPDATE users SET is_active=0, updated_at=datetime('now') WHERE id=?",
            [(uid,) for uid in inactive_user_ids],
        )
    await db.conn.execute(
        "UPDATE broadcasts SET sent=sent+?, failed=failed+?, blocked=blocked+? WHERE id=?",
        (counters["sent"], counters["failed"], counters["blocked"], broadcast_id),
    )
    await db.conn.commit()
    batch.clear()
    inactive_user_ids.clear()
    counters["sent"] = counters["failed"] = counters["blocked"] = 0


# Sender abstraction: real bot or simulated stub.
Sender = Callable[[int, str], Awaitable[None]]


def _real_sender(bot: Bot) -> Sender:
    async def _send(chat_id: int, text: str) -> None:
        await bot.send_message(chat_id, text)

    return _send


async def run_broadcast(
    bot_or_sender: Bot | Sender,
    db: Database,
    settings: Settings,
    broadcast_id: int,
) -> None:
    send: Sender = (
        _real_sender(bot_or_sender) if isinstance(bot_or_sender, Bot) else bot_or_sender
    )

    bcast = await get_broadcast(db, broadcast_id)
    if not bcast or bcast["status"] != "processing":
        log.info("broadcast %s not runnable (status=%s)", broadcast_id, bcast and bcast["status"])
        return

    batch: list[tuple[int, int, str, Optional[str]]] = []
    inactive_ids: list[int] = []
    counters = {"sent": 0, "failed": 0, "blocked": 0}
    processed_since_poll = 0
    stopped = False

    async for user_row_id, tg_id in _iter_recipients(
        db, bot_kind=bcast["bot_kind"], segment=bcast["segment"]
    ):
        if stopped:
            break

        retries = 0
        while True:
            try:
                await send(tg_id, bcast["text"])
                counters["sent"] += 1
                batch.append((broadcast_id, tg_id, "sent", None))
                break
            except TelegramRetryAfter as e:
                if retries >= MAX_RETRY_PER_USER:
                    counters["failed"] += 1
                    batch.append((broadcast_id, tg_id, "failed", f"retry-after-exhausted: {e}"))
                    break
                retries += 1
                await asyncio.sleep(float(e.retry_after))
                continue
            except TelegramForbiddenError as e:
                counters["blocked"] += 1
                batch.append((broadcast_id, tg_id, "blocked", repr(e)))
                inactive_ids.append(user_row_id)
                break
            except TelegramBadRequest as e:
                msg = str(e).lower()
                if "chat not found" in msg or "user is deactivated" in msg:
                    counters["blocked"] += 1
                    batch.append((broadcast_id, tg_id, "blocked", repr(e)))
                    inactive_ids.append(user_row_id)
                else:
                    counters["failed"] += 1
                    batch.append((broadcast_id, tg_id, "failed", repr(e)))
                break
            except Exception as e:  # noqa: BLE001 — defensive sink for one user
                counters["failed"] += 1
                batch.append((broadcast_id, tg_id, "failed", repr(e)))
                break

        await asyncio.sleep(SEND_INTERVAL_SEC)
        processed_since_poll += 1

        if len(batch) >= BATCH_SIZE:
            await _flush(db, broadcast_id, batch, counters, inactive_ids)

        if processed_since_poll >= STATUS_POLL_EVERY:
            processed_since_poll = 0
            cur = await db.conn.execute(
                "SELECT status FROM broadcasts WHERE id=?", (broadcast_id,)
            )
            row = await cur.fetchone()
            if row and row["status"] == "stopped":
                stopped = True

    await _flush(db, broadcast_id, batch, counters, inactive_ids)

    final = await get_broadcast(db, broadcast_id)
    if final and final["status"] == "processing":
        await db.conn.execute(
            "UPDATE broadcasts SET status='completed', finished_at=datetime('now') WHERE id=?",
            (broadcast_id,),
        )
        await db.conn.commit()
