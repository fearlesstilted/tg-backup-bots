from __future__ import annotations

import unittest

from app.config import SEGMENTS_BY_BOT, is_valid_segment


class SegmentValidationTests(unittest.TestCase):
    def test_reviews_bot_accepts_its_segments(self) -> None:
        for seg in ("ru_reviews", "foreign_reviews", "test"):
            self.assertTrue(is_valid_segment("reviews", seg), seg)

    def test_private_bot_accepts_its_segments(self) -> None:
        for seg in ("ru_private", "foreign_private", "test"):
            self.assertTrue(is_valid_segment("private", seg), seg)

    def test_reviews_bot_rejects_private_segments(self) -> None:
        self.assertFalse(is_valid_segment("reviews", "ru_private"))
        self.assertFalse(is_valid_segment("reviews", "foreign_private"))

    def test_private_bot_rejects_reviews_segments(self) -> None:
        self.assertFalse(is_valid_segment("private", "ru_reviews"))
        self.assertFalse(is_valid_segment("private", "foreign_reviews"))

    def test_unknown_segment_rejected(self) -> None:
        self.assertFalse(is_valid_segment("reviews", ""))
        self.assertFalse(is_valid_segment("reviews", "garbage"))
        self.assertFalse(is_valid_segment("private", "unknown"))

    def test_unknown_bot_kind_rejected(self) -> None:
        self.assertFalse(is_valid_segment("mirror", "ru_reviews"))

    def test_segment_sets_are_disjoint_except_test(self) -> None:
        rev = SEGMENTS_BY_BOT["reviews"]
        priv = SEGMENTS_BY_BOT["private"]
        self.assertEqual(rev & priv, {"test"})


if __name__ == "__main__":
    unittest.main()
