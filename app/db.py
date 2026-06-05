from __future__ import annotations

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  telegram_id   INTEGER NOT NULL,
  bot_kind      TEXT NOT NULL,
  segment       TEXT NOT NULL,
  username      TEXT,
  first_name    TEXT,
  language_code TEXT,
  opted_in      INTEGER NOT NULL DEFAULT 0,
  is_active     INTEGER NOT NULL DEFAULT 1,
  created_at    TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at    TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(telegram_id, bot_kind, segment)
);
CREATE INDEX IF NOT EXISTS idx_users_bot_segment_active
  ON users(bot_kind, segment, opted_in, is_active);

CREATE TABLE IF NOT EXISTS broadcasts (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  bot_kind     TEXT NOT NULL,
  segment      TEXT NOT NULL,
  text         TEXT NOT NULL,
  status       TEXT NOT NULL,
  total        INTEGER NOT NULL DEFAULT 0,
  sent         INTEGER NOT NULL DEFAULT 0,
  failed       INTEGER NOT NULL DEFAULT 0,
  blocked      INTEGER NOT NULL DEFAULT 0,
  created_by   INTEGER NOT NULL,
  created_at   TEXT NOT NULL DEFAULT (datetime('now')),
  finished_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_broadcasts_bot ON broadcasts(bot_kind, created_at DESC);

CREATE TABLE IF NOT EXISTS broadcast_deliveries (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  broadcast_id  INTEGER NOT NULL REFERENCES broadcasts(id),
  telegram_id   INTEGER NOT NULL,
  status        TEXT NOT NULL,
  error         TEXT,
  sent_at       TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_deliveries_broadcast
  ON broadcast_deliveries(broadcast_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_deliveries_broadcast_user
  ON broadcast_deliveries(broadcast_id, telegram_id);
CREATE INDEX IF NOT EXISTS idx_deliveries_user
  ON broadcast_deliveries(telegram_id);
"""


class Database:
    def __init__(self, conn: aiosqlite.Connection, path: str) -> None:
        self.conn = conn
        self.path = path

    @classmethod
    async def connect(cls, path: str) -> "Database":
        conn = await aiosqlite.connect(path)
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA journal_mode=WAL;")
        await conn.execute("PRAGMA busy_timeout=5000;")
        await conn.execute("PRAGMA foreign_keys=ON;")
        await conn.executescript(SCHEMA)
        await conn.commit()
        return cls(conn, path)

    async def close(self) -> None:
        await self.conn.close()

    async def mark_stale_broadcasts_interrupted(self) -> int:
        cur = await self.conn.execute(
            "UPDATE broadcasts "
            "SET status='interrupted', finished_at=datetime('now') "
            "WHERE status='processing'"
        )
        await self.conn.commit()
        return cur.rowcount or 0
