from __future__ import annotations

import asyncio
import logging
import sys

from .bot_factory import build
from .config import Settings
from .db import Database
from .single_instance import AlreadyRunningError, SingleInstanceLock, lock_path_for


async def _run(settings: Settings) -> None:
    db = await Database.connect(settings.database_path)

    interrupted = await db.mark_stale_broadcasts_interrupted()
    if interrupted:
        logging.info("Marked %d stale broadcast(s) as interrupted.", interrupted)

    reviews_bot, reviews_dp = build("reviews", settings, db)
    private_bot, private_dp = build("private", settings, db)

    try:
        await asyncio.gather(
            reviews_dp.start_polling(reviews_bot),
            private_dp.start_polling(private_bot),
        )
    finally:
        await asyncio.gather(
            reviews_bot.session.close(),
            private_bot.session.close(),
            return_exceptions=True,
        )
        await db.close()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = Settings.load()
    lock = SingleInstanceLock(lock_path_for(settings.database_path))
    try:
        lock.acquire()
    except AlreadyRunningError as e:
        logging.error(str(e))
        sys.exit(4)
    try:
        try:
            asyncio.run(_run(settings))
        except (KeyboardInterrupt, SystemExit):
            pass
    finally:
        lock.release()


if __name__ == "__main__":
    main()
