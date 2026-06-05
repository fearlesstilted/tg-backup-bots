from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
import sys

from .bot_factory import build
from .config import Settings
from .db import Database
from .handlers import admin as admin_h
from .single_instance import AlreadyRunningError, SingleInstanceLock, lock_path_for


async def _run(settings: Settings) -> None:
    db = await Database.connect(settings.database_path)

    interrupted = await db.mark_stale_broadcasts_interrupted()
    if interrupted:
        logging.info("Marked %d stale broadcast(s) as interrupted.", interrupted)

    reviews_bot, reviews_dp = build("reviews", settings, db)
    private_bot, private_dp = build("private", settings, db)
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def _request_stop(signame: str) -> None:
        logging.info("Received %s, stopping polling.", signame)
        stop_event.set()

    registered_signals: list[signal.Signals] = []
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _request_stop, sig.name)
            registered_signals.append(sig)
        except NotImplementedError:
            pass

    polling_tasks = [
        asyncio.create_task(
            reviews_dp.start_polling(
                reviews_bot,
                handle_signals=False,
                close_bot_session=False,
            ),
            name="reviews-polling",
        ),
        asyncio.create_task(
            private_dp.start_polling(
                private_bot,
                handle_signals=False,
                close_bot_session=False,
            ),
            name="private-polling",
        ),
    ]
    stop_task = asyncio.create_task(stop_event.wait(), name="shutdown-wait")

    try:
        done, pending = await asyncio.wait(
            [*polling_tasks, stop_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        if stop_task in done:
            await asyncio.gather(
                reviews_dp.stop_polling(),
                private_dp.stop_polling(),
                return_exceptions=True,
            )
            await asyncio.gather(*polling_tasks, return_exceptions=True)
        else:
            stop_task.cancel()
            for task in done:
                task.result()
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
    finally:
        for sig in registered_signals:
            with contextlib.suppress(NotImplementedError):
                loop.remove_signal_handler(sig)
        stop_task.cancel()
        await admin_h.shutdown_background_tasks(db)
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
    try:
        settings = Settings.load()
    except RuntimeError as e:
        logging.error("Configuration error: %s", e)
        sys.exit(2)

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
