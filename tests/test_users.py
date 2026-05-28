from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.db import Database
from app.services import users as users_svc


class UsersServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = await Database.connect(str(Path(self.tmp.name) / "u.db"))

    async def asyncTearDown(self) -> None:
        await self.db.close()
        self.tmp.cleanup()

    async def _row(self, telegram_id: int, bot_kind: str, segment: str) -> dict | None:
        cur = await self.db.conn.execute(
            "SELECT * FROM users WHERE telegram_id=? AND bot_kind=? AND segment=?",
            (telegram_id, bot_kind, segment),
        )
        row = await cur.fetchone()
        return dict(row) if row else None

    async def test_upsert_creates_row_with_defaults(self) -> None:
        await users_svc.upsert_user(
            self.db,
            telegram_id=42,
            bot_kind="reviews",
            segment="ru_reviews",
            username="alice",
            first_name="Alice",
            language_code="ru",
        )
        row = await self._row(42, "reviews", "ru_reviews")
        self.assertIsNotNone(row)
        self.assertEqual(row["opted_in"], 0)
        self.assertEqual(row["is_active"], 1)
        self.assertEqual(row["username"], "alice")

    async def test_upsert_updates_profile_on_conflict(self) -> None:
        await users_svc.upsert_user(
            self.db, telegram_id=42, bot_kind="reviews", segment="ru_reviews",
            username="alice", first_name="Alice", language_code="ru",
        )
        await users_svc.upsert_user(
            self.db, telegram_id=42, bot_kind="reviews", segment="ru_reviews",
            username="alice2", first_name="Alicia", language_code="en",
        )
        row = await self._row(42, "reviews", "ru_reviews")
        self.assertEqual(row["username"], "alice2")
        self.assertEqual(row["first_name"], "Alicia")
        self.assertEqual(row["language_code"], "en")

    async def test_same_telegram_id_can_exist_in_two_bots(self) -> None:
        await users_svc.upsert_user(
            self.db, telegram_id=42, bot_kind="reviews", segment="ru_reviews",
            username="a", first_name="A", language_code=None,
        )
        await users_svc.upsert_user(
            self.db, telegram_id=42, bot_kind="private", segment="ru_private",
            username="a", first_name="A", language_code=None,
        )
        cur = await self.db.conn.execute(
            "SELECT COUNT(*) FROM users WHERE telegram_id=42"
        )
        self.assertEqual((await cur.fetchone())[0], 2)

    async def test_set_opted_in_flips_only_target_row(self) -> None:
        await users_svc.upsert_user(
            self.db, telegram_id=42, bot_kind="reviews", segment="ru_reviews",
            username="a", first_name="A", language_code=None,
        )
        await users_svc.upsert_user(
            self.db, telegram_id=42, bot_kind="private", segment="ru_private",
            username="a", first_name="A", language_code=None,
        )

        await users_svc.set_opted_in(
            self.db, telegram_id=42, bot_kind="reviews", segment="ru_reviews"
        )

        rev = await self._row(42, "reviews", "ru_reviews")
        priv = await self._row(42, "private", "ru_private")
        self.assertEqual(rev["opted_in"], 1)
        self.assertEqual(rev["is_active"], 1)
        self.assertEqual(priv["opted_in"], 0)


if __name__ == "__main__":
    unittest.main()
