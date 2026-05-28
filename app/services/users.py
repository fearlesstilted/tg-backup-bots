from __future__ import annotations

from typing import Optional

from ..db import Database


async def upsert_user(
    db: Database,
    *,
    telegram_id: int,
    bot_kind: str,
    segment: str,
    username: Optional[str],
    first_name: Optional[str],
    language_code: Optional[str],
) -> None:
    await db.conn.execute(
        """
        INSERT INTO users (telegram_id, bot_kind, segment, username, first_name, language_code)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(telegram_id, bot_kind, segment) DO UPDATE SET
          username      = excluded.username,
          first_name    = excluded.first_name,
          language_code = excluded.language_code,
          updated_at    = datetime('now')
        """,
        (telegram_id, bot_kind, segment, username, first_name, language_code),
    )
    await db.conn.commit()


async def set_opted_in(
    db: Database, *, telegram_id: int, bot_kind: str, segment: str
) -> None:
    await db.conn.execute(
        """
        UPDATE users
        SET opted_in=1, is_active=1, updated_at=datetime('now')
        WHERE telegram_id=? AND bot_kind=? AND segment=?
        """,
        (telegram_id, bot_kind, segment),
    )
    await db.conn.commit()


async def stats_by_segment(db: Database, bot_kind: str) -> list[dict]:
    cur = await db.conn.execute(
        """
        SELECT segment,
               COUNT(*)                              AS total,
               SUM(CASE WHEN opted_in=1 THEN 1 ELSE 0 END) AS opted_in,
               SUM(CASE WHEN opted_in=1 AND is_active=1 THEN 1 ELSE 0 END) AS active
        FROM users
        WHERE bot_kind=?
        GROUP BY segment
        ORDER BY segment
        """,
        (bot_kind,),
    )
    rows = await cur.fetchall()
    return [dict(r) for r in rows]
