"""Preflight checks without touching Telegram.

Validates env via Settings.load(), confirms admin_ids/links are present,
opens the SQLite DB (applying schema), and prints a short summary.
Exits 0 on success, non-zero otherwise. Safe to run before live polling.

Usage:
    python -m app.healthcheck
"""

from __future__ import annotations

import asyncio
import sys
from typing import TextIO

from .config import SEGMENTS_BY_BOT, Settings
from .db import Database

PLACEHOLDER_VALUES = {
    "REVIEWS_BOT_TOKEN": ("replace-me",),
    "PRIVATE_BOT_TOKEN": ("replace-me",),
    "RU_REVIEWS_LINK": ("ru_reviews_invite",),
    "FOREIGN_REVIEWS_LINK": ("foreign_reviews_invite",),
    "RU_PRIVATE_LINK": ("ru_private_invite",),
    "FOREIGN_PRIVATE_LINK": ("foreign_private_invite",),
}


def _is_placeholder(value: str, markers: tuple[str, ...]) -> bool:
    return any(marker in value for marker in markers)


async def _check(out: TextIO) -> int:
    try:
        settings = Settings.load()
    except RuntimeError as e:
        print(f"FAIL config: {e}", file=out)
        return 2

    if not settings.admin_ids:
        print("FAIL config: ADMIN_IDS is empty (set at least one Telegram user id)", file=out)
        return 2

    placeholder_fields = []
    token_values = {
        "REVIEWS_BOT_TOKEN": settings.reviews_bot_token,
        "PRIVATE_BOT_TOKEN": settings.private_bot_token,
    }
    link_values = {
        key.upper() + "_LINK": value
        for key, value in settings.segment_links.items()
    }
    for key, value in (token_values | link_values).items():
        markers = PLACEHOLDER_VALUES.get(key, ())
        if markers and _is_placeholder(value, markers):
            placeholder_fields.append(key)
    if placeholder_fields:
        print(
            "FAIL config: replace placeholder values in "
            + ", ".join(sorted(placeholder_fields)),
            file=out,
        )
        return 2

    missing_links = [k for k, v in settings.segment_links.items() if not v]
    if missing_links:
        print(f"FAIL config: empty invite links: {', '.join(missing_links)}", file=out)
        return 2

    try:
        db = await Database.connect(settings.database_path)
    except Exception as e:  # noqa: BLE001
        print(f"FAIL db: cannot open {settings.database_path}: {e}", file=out)
        return 3

    try:
        cur = await db.conn.execute("PRAGMA journal_mode;")
        jm = (await cur.fetchone())[0]

        cur = await db.conn.execute(
            "SELECT bot_kind, segment, "
            "COUNT(*) AS total, "
            "SUM(CASE WHEN opted_in=1 AND is_active=1 THEN 1 ELSE 0 END) AS active "
            "FROM users GROUP BY bot_kind, segment ORDER BY bot_kind, segment"
        )
        rows = [dict(r) for r in await cur.fetchall()]
    finally:
        await db.close()

    print("OK preflight", file=out)
    print(f"  db.path          = {settings.database_path}", file=out)
    print(f"  db.journal_mode  = {jm}", file=out)
    print(f"  admin_ids        = {sorted(settings.admin_ids)}", file=out)
    print("  segments allowed:", file=out)
    for bot_kind, segs in SEGMENTS_BY_BOT.items():
        print(f"    {bot_kind:<7} -> {', '.join(sorted(segs))}", file=out)
    print("  users (by bot/segment):", file=out)
    if not rows:
        print("    (none yet)", file=out)
    else:
        for r in rows:
            print(
                f"    {r['bot_kind']:<7} {r['segment']:<16} "
                f"total={r['total']} active={r['active']}",
                file=out,
            )
    return 0


def main() -> None:
    sys.exit(asyncio.run(_check(sys.stdout)))


if __name__ == "__main__":
    main()
