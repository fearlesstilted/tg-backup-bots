from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

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

        total = await broadcasts.count_recipients(
            self.db, bot_kind="reviews", segment="test"
        )
        broadcast_id = await broadcasts.create_broadcast(
            self.db,
            bot_kind="reviews",
            segment="test",
            text="hello",
            created_by=1,
            total=total,
        )

        sent_to: list[int] = []

        async def sender(chat_id: int, text: str) -> None:
            sent_to.append(chat_id)

        old_interval = broadcasts.SEND_INTERVAL_SEC
        broadcasts.SEND_INTERVAL_SEC = 0
        try:
            await broadcasts.run_broadcast(sender, self.db, object(), broadcast_id)
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


if __name__ == "__main__":
    unittest.main()
