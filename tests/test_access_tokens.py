from __future__ import annotations

import unittest

from app.access_tokens import (
    AccessTokenError,
    create_access_token,
    verify_access_token,
)


class AccessTokenTests(unittest.TestCase):
    def test_private_token_roundtrip(self) -> None:
        token = create_access_token(
            "ru_private", "secret-value", ttl_seconds=60, now=1_000
        )

        self.assertLessEqual(len(token), 64)
        self.assertEqual(
            verify_access_token(token, "secret-value", now=1_030),
            "ru_private",
        )

    def test_token_rejects_tampering(self) -> None:
        token = create_access_token(
            "foreign_private", "secret-value", ttl_seconds=60, now=1_000
        )
        bad = token.replace(".fp.", ".rp.")

        with self.assertRaises(AccessTokenError):
            verify_access_token(bad, "secret-value", now=1_030)

    def test_token_rejects_expiry(self) -> None:
        token = create_access_token(
            "ru_private", "secret-value", ttl_seconds=60, now=1_000
        )

        with self.assertRaises(AccessTokenError):
            verify_access_token(token, "secret-value", now=1_061)

    def test_only_private_segments_can_be_tokenized(self) -> None:
        with self.assertRaises(AccessTokenError):
            create_access_token("ru_reviews", "secret-value")


if __name__ == "__main__":
    unittest.main()
