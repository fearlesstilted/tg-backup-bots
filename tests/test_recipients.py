from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.db import Database
from app.services import broadcasts as bcast_svc
from app.services import users as users_svc


class RecipientFilterTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = await Database.connect(str(Path(self.tmp.name) / "r.db"))

    async def asyncTearDown(self) -> None:
        await self.db.close()
        self.tmp.cleanup()

    async def _add(
        self, *, tid: int, bot: str, seg: str, opted: bool = True, active: bool = True
    ) -> None:
        await users_svc.upsert_user(
            self.db, telegram_id=tid, bot_kind=bot, segment=seg,
            username=None, first_name=None, language_code=None,
        )
        if opted:
            await users_svc.set_opted_in(
                self.db, telegram_id=tid, bot_kind=bot, segment=seg
            )
        if not active:
            await self.db.conn.execute(
                "UPDATE users SET is_active=0 WHERE telegram_id=? AND bot_kind=? AND segment=?",
                (tid, bot, seg),
            )
            await self.db.conn.commit()

    async def test_count_filters_by_bot_kind_and_segment(self) -> None:
        await self._add(tid=1, bot="reviews", seg="ru_reviews")
        await self._add(tid=2, bot="reviews", seg="ru_reviews")
        await self._add(tid=3, bot="reviews", seg="foreign_reviews")
        await self._add(tid=4, bot="private", seg="ru_private")
        # Same telegram id in both bots — must not bleed across bot_kind.
        await self._add(tid=1, bot="private", seg="ru_private")

        self.assertEqual(
            await bcast_svc.count_recipients(self.db, bot_kind="reviews", segment="ru_reviews"),
            2,
        )
        self.assertEqual(
            await bcast_svc.count_recipients(self.db, bot_kind="reviews", segment="foreign_reviews"),
            1,
        )
        self.assertEqual(
            await bcast_svc.count_recipients(self.db, bot_kind="private", segment="ru_private"),
            2,
        )
        self.assertEqual(
            await bcast_svc.count_recipients(self.db, bot_kind="private", segment="foreign_private"),
            0,
        )

    async def test_count_excludes_not_opted_in_and_inactive(self) -> None:
        await self._add(tid=10, bot="reviews", seg="ru_reviews")                 # in
        await self._add(tid=11, bot="reviews", seg="ru_reviews", opted=False)    # out
        await self._add(tid=12, bot="reviews", seg="ru_reviews", active=False)   # out

        self.assertEqual(
            await bcast_svc.count_recipients(self.db, bot_kind="reviews", segment="ru_reviews"),
            1,
        )


if __name__ == "__main__":
    unittest.main()
