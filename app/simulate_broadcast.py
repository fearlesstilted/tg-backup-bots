"""Simulate a broadcast of 1000 fake users without hitting Telegram.

Runs the real broadcast engine end-to-end against a sandbox SQLite database,
using a stub sender that sleeps instead of calling Telegram. Bot tokens are
not required.

Usage:
    python -m app.simulate_broadcast
    python -m app.simulate_broadcast --db ./sim.db --users 1000 --bot reviews --segment ru_reviews
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import time

from .db import Database
from .services import broadcasts as bcast_svc


class _StubSettings:
    """Minimal stand-in for Settings — broadcast engine only reads what it needs."""

    segment_links: dict[str, str] = {}


async def _seed_users(db: Database, *, bot_kind: str, segment: str, n: int) -> None:
    rows = [
        (1_000_000_000 + i, bot_kind, segment, f"sim_{i}", f"Sim{i}", "en")
        for i in range(n)
    ]
    await db.conn.executemany(
        """
        INSERT INTO users
          (telegram_id, bot_kind, segment, username, first_name, language_code, opted_in, is_active)
        VALUES (?, ?, ?, ?, ?, ?, 1, 1)
        ON CONFLICT(telegram_id, bot_kind, segment) DO NOTHING
        """,
        rows,
    )
    await db.conn.commit()


async def _main(args: argparse.Namespace) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

    db = await Database.connect(args.db)
    try:
        await _seed_users(db, bot_kind=args.bot, segment=args.segment, n=args.users)

        total = await bcast_svc.count_recipients(
            db, bot_kind=args.bot, segment=args.segment
        )
        bid = await bcast_svc.create_broadcast(
            db,
            bot_kind=args.bot,
            segment=args.segment,
            text="[simulate] hello",
            created_by=0,
            total=total,
        )
        logging.info("Simulating broadcast #%s with %d recipients", bid, total)

        sent_counter = {"n": 0}

        async def stub_send(chat_id: int, text: str) -> None:
            sent_counter["n"] += 1
            # No artificial sleep — the engine's own rate limiter sets the pace.

        t0 = time.monotonic()
        await bcast_svc.run_broadcast(stub_send, db, _StubSettings(), bid)
        dt = time.monotonic() - t0

        final = await bcast_svc.get_broadcast(db, bid)
        rate = sent_counter["n"] / dt if dt else 0.0
        logging.info(
            "Done in %.1fs (~%.1f msg/s). Status=%s sent=%s failed=%s blocked=%s",
            dt, rate, final["status"], final["sent"], final["failed"], final["blocked"],
        )
    finally:
        await db.close()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=os.environ.get("DATABASE_PATH", "./sim.db"))
    p.add_argument("--users", type=int, default=1000)
    p.add_argument("--bot", default="reviews", choices=["reviews", "private"])
    p.add_argument("--segment", default="test")
    asyncio.run(_main(p.parse_args()))


if __name__ == "__main__":
    main()
