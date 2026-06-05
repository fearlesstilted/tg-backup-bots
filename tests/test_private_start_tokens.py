from __future__ import annotations

import unittest

from app.access_tokens import create_access_token
from app.config import Settings
from app.handlers.user import resolve_start_segment


def _settings(*, require_token: bool) -> Settings:
    return Settings(
        reviews_bot_token="111:fake",
        private_bot_token="222:fake",
        admin_ids=frozenset({42}),
        database_path="/tmp/test.db",
        segment_links={
            "ru_reviews": "https://t.me/+rr",
            "foreign_reviews": "https://t.me/+fr",
            "ru_private": "https://t.me/+rp",
            "foreign_private": "https://t.me/+fp",
        },
        private_access_secret="secret-value",
        private_require_access_token=require_token,
    )


class PrivateStartTokenTests(unittest.TestCase):
    def test_reviews_bot_still_accepts_raw_segments(self) -> None:
        self.assertEqual(
            resolve_start_segment("reviews", "ru_reviews", _settings(require_token=True)),
            "ru_reviews",
        )

    def test_private_bot_accepts_raw_segments_when_not_enforced(self) -> None:
        self.assertEqual(
            resolve_start_segment(
                "private", "ru_private", _settings(require_token=False)
            ),
            "ru_private",
        )

    def test_private_bot_requires_signed_token_when_enforced(self) -> None:
        settings = _settings(require_token=True)
        token = create_access_token(
            "foreign_private",
            settings.private_access_secret,
            ttl_seconds=60,
            now=1_000,
        )

        self.assertEqual(
            resolve_start_segment("private", "foreign_private", settings, now=1_030),
            "unknown",
        )
        self.assertEqual(
            resolve_start_segment("private", token, settings, now=1_030),
            "foreign_private",
        )

    def test_private_test_segment_remains_available(self) -> None:
        self.assertEqual(
            resolve_start_segment("private", "test", _settings(require_token=True)),
            "test",
        )

    def test_invalid_token_falls_back_to_unknown(self) -> None:
        self.assertEqual(
            resolve_start_segment(
                "private", "v1.rp.dead.invalid", _settings(require_token=True)
            ),
            "unknown",
        )


if __name__ == "__main__":
    unittest.main()
