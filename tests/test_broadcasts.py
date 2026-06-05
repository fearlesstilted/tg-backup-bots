from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter

from app.db import Database
from app.services import broadcasts
from app.services import users as users_svc


class BroadcastServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = await Database.connect(str(Path(self.tmp.name) / "test.db"))

    async def asyncTearDown(self) -> None:
        await self.db.close()
        self.tmp.cleanup()

    async def _add_opted_in_user(self, telegram_id: int) -> None:
        await users_svc.upsert_user(
            self.db,
            telegram_id=telegram_id,
            bot_kind="reviews",
            segment="test",
            username=None,
            first_name=None,
            language_code=None,
        )
        await users_svc.set_opted_in(
            self.db,
            telegram_id=telegram_id,
            bot_kind="reviews",
            segment="test",
        )

    async def _create_test_broadcast(self, text: str = "hello") -> int:
        total = await broadcasts.count_recipients(
            self.db, bot_kind="reviews", segment="test"
        )
        return await broadcasts.create_broadcast(
            self.db,
            bot_kind="reviews",
            segment="test",
            text=text,
            created_by=1,
            total=total,
        )

    async def test_get_broadcast_can_be_scoped_to_bot_kind(self) -> None:
        broadcast_id = await broadcasts.create_broadcast(
            self.db,
            bot_kind="reviews",
            segment="test",
            text="hello",
            created_by=1,
            total=0,
        )

        self.assertIsNotNone(await broadcasts.get_broadcast(self.db, broadcast_id))
        self.assertIsNotNone(
            await broadcasts.get_broadcast(
                self.db, broadcast_id, bot_kind="reviews"
            )
        )
        self.assertIsNone(
            await broadcasts.get_broadcast(
                self.db, broadcast_id, bot_kind="private"
            )
        )

    async def test_request_stop_can_be_scoped_to_bot_kind(self) -> None:
        broadcast_id = await broadcasts.create_broadcast(
            self.db,
            bot_kind="reviews",
            segment="test",
            text="hello",
            created_by=1,
            total=0,
        )

        self.assertFalse(
            await broadcasts.request_stop(
                self.db, broadcast_id, bot_kind="private"
            )
        )
        still_processing = await broadcasts.get_broadcast(self.db, broadcast_id)
        self.assertEqual(still_processing["status"], "processing")

        self.assertTrue(
            await broadcasts.request_stop(
                self.db, broadcast_id, bot_kind="reviews"
            )
        )
        stopped = await broadcasts.get_broadcast(self.db, broadcast_id)
        self.assertEqual(stopped["status"], "stopped")

    async def test_run_broadcast_writes_delivery_rows(self) -> None:
        for telegram_id in (101, 102):
            await self._add_opted_in_user(telegram_id)
        broadcast_id = await self._create_test_broadcast()

        sent_to: list[int] = []

        async def sender(chat_id: int, text: str) -> None:
            sent_to.append(chat_id)

        old_interval = broadcasts.SEND_INTERVAL_SEC
        broadcasts.SEND_INTERVAL_SEC = 0
        try:
            await broadcasts.run_broadcast(sender, self.db, broadcast_id)
        finally:
            broadcasts.SEND_INTERVAL_SEC = old_interval

        self.assertEqual(sent_to, [101, 102])

        cur = await self.db.conn.execute(
            """
            SELECT broadcast_id, telegram_id, status, error
            FROM broadcast_deliveries
            WHERE broadcast_id=?
            ORDER BY telegram_id
            """,
            (broadcast_id,),
        )
        rows = [dict(row) for row in await cur.fetchall()]
        self.assertEqual(
            rows,
            [
                {
                    "broadcast_id": broadcast_id,
                    "telegram_id": 101,
                    "status": "sent",
                    "error": None,
                },
                {
                    "broadcast_id": broadcast_id,
                    "telegram_id": 102,
                    "status": "sent",
                    "error": None,
                },
            ],
        )

        final = await broadcasts.get_broadcast(self.db, broadcast_id)
        self.assertEqual(final["status"], "completed")
        self.assertEqual(final["sent"], 2)

    async def test_blocked_user_is_deactivated(self) -> None:
        await self._add_opted_in_user(201)
        broadcast_id = await self._create_test_broadcast()

        async def sender(chat_id: int, text: str) -> None:
            raise TelegramForbiddenError(method=None, message="bot was blocked")

        old_interval = broadcasts.SEND_INTERVAL_SEC
        broadcasts.SEND_INTERVAL_SEC = 0
        try:
            await broadcasts.run_broadcast(sender, self.db, broadcast_id)
        finally:
            broadcasts.SEND_INTERVAL_SEC = old_interval

        final = await broadcasts.get_broadcast(self.db, broadcast_id)
        self.assertEqual(final["blocked"], 1)
        cur = await self.db.conn.execute(
            "SELECT is_active FROM users WHERE telegram_id=201"
        )
        self.assertEqual((await cur.fetchone())["is_active"], 0)

    async def test_retry_after_exhaustion_records_failure(self) -> None:
        await self._add_opted_in_user(301)
        broadcast_id = await self._create_test_broadcast()

        async def sender(chat_id: int, text: str) -> None:
            raise TelegramRetryAfter(method=None, message="retry", retry_after=0)

        old_interval = broadcasts.SEND_INTERVAL_SEC
        broadcasts.SEND_INTERVAL_SEC = 0
        try:
            await broadcasts.run_broadcast(sender, self.db, broadcast_id)
        finally:
            broadcasts.SEND_INTERVAL_SEC = old_interval

        final = await broadcasts.get_broadcast(self.db, broadcast_id)
        self.assertEqual(final["failed"], 1)
        cur = await self.db.conn.execute(
            "SELECT status, error FROM broadcast_deliveries WHERE broadcast_id=?",
            (broadcast_id,),
        )
        row = await cur.fetchone()
        self.assertEqual(row["status"], "failed")
        self.assertIn("retry-after-exhausted", row["error"])

    async def test_bad_request_chat_not_found_marks_blocked(self) -> None:
        await self._add_opted_in_user(401)
        broadcast_id = await self._create_test_broadcast()

        async def sender(chat_id: int, text: str) -> None:
            raise TelegramBadRequest(method=None, message="chat not found")

        old_interval = broadcasts.SEND_INTERVAL_SEC
        broadcasts.SEND_INTERVAL_SEC = 0
        try:
            await broadcasts.run_broadcast(sender, self.db, broadcast_id)
        finally:
            broadcasts.SEND_INTERVAL_SEC = old_interval

        final = await broadcasts.get_broadcast(self.db, broadcast_id)
        self.assertEqual(final["blocked"], 1)

    async def test_cancelled_broadcast_flushes_partial_batch(self) -> None:
        for telegram_id in (501, 502):
            await self._add_opted_in_user(telegram_id)
        broadcast_id = await self._create_test_broadcast()
        sent_once = asyncio.Event()
        release_sender = asyncio.Event()

        async def sender(chat_id: int, text: str) -> None:
            sent_once.set()
            await release_sender.wait()

        task = asyncio.create_task(
            broadcasts.run_broadcast(sender, self.db, broadcast_id)
        )
        await sent_once.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task

        final = await broadcasts.get_broadcast(self.db, broadcast_id)
        self.assertEqual(final["status"], "interrupted")

    async def test_stop_mid_broadcast_halts_before_all_recipients(self) -> None:
        old_poll_every = broadcasts.STATUS_POLL_EVERY
        old_interval = broadcasts.SEND_INTERVAL_SEC
        broadcasts.STATUS_POLL_EVERY = 1
        broadcasts.SEND_INTERVAL_SEC = 0
        try:
            for telegram_id in range(601, 606):
                await self._add_opted_in_user(telegram_id)
            broadcast_id = await self._create_test_broadcast()
            sent_to: list[int] = []

            async def sender(chat_id: int, text: str) -> None:
                sent_to.append(chat_id)
                if len(sent_to) == 2:
                    await broadcasts.request_stop(self.db, broadcast_id)

            await broadcasts.run_broadcast(sender, self.db, broadcast_id)
        finally:
            broadcasts.STATUS_POLL_EVERY = old_poll_every
            broadcasts.SEND_INTERVAL_SEC = old_interval

        final = await broadcasts.get_broadcast(self.db, broadcast_id)
        self.assertEqual(final["status"], "stopped")
        self.assertLess(final["sent"], final["total"])

    async def test_stale_processing_broadcasts_are_marked_interrupted(self) -> None:
        broadcast_id = await self._create_test_broadcast()

        changed = await self.db.mark_stale_broadcasts_interrupted()

        final = await broadcasts.get_broadcast(self.db, broadcast_id)
        self.assertEqual(changed, 1)
        self.assertEqual(final["status"], "interrupted")
        self.assertIsNotNone(final["finished_at"])

    async def test_duplicate_delivery_row_is_ignored(self) -> None:
        await self._add_opted_in_user(701)
        broadcast_id = await self._create_test_broadcast()

        async def sender(chat_id: int, text: str) -> None:
            return None

        old_interval = broadcasts.SEND_INTERVAL_SEC
        broadcasts.SEND_INTERVAL_SEC = 0
        try:
            await broadcasts.run_broadcast(sender, self.db, broadcast_id)
            await self.db.conn.execute(
                "UPDATE broadcasts SET status='processing' WHERE id=?",
                (broadcast_id,),
            )
            await self.db.conn.commit()
            await broadcasts.run_broadcast(sender, self.db, broadcast_id)
        finally:
            broadcasts.SEND_INTERVAL_SEC = old_interval

        cur = await self.db.conn.execute(
            "SELECT COUNT(*) FROM broadcast_deliveries WHERE broadcast_id=?",
            (broadcast_id,),
        )
        self.assertEqual((await cur.fetchone())[0], 1)
        final = await broadcasts.get_broadcast(self.db, broadcast_id)
        self.assertEqual(final["sent"], 1)


if __name__ == "__main__":
    unittest.main()
