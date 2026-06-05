from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

from dotenv import load_dotenv

BOT_KINDS = ("reviews", "private")

SEGMENTS_BY_BOT: Mapping[str, frozenset[str]] = {
    "reviews": frozenset({"ru_reviews", "foreign_reviews", "test"}),
    "private": frozenset({"ru_private", "foreign_private", "test"}),
}


@dataclass(frozen=True)
class Settings:
    reviews_bot_token: str
    private_bot_token: str
    admin_ids: frozenset[int]
    database_path: str
    segment_links: Mapping[str, str]
    private_access_secret: str
    private_require_access_token: bool

    @classmethod
    def load(cls) -> "Settings":
        load_dotenv()

        def _req(key: str) -> str:
            v = os.environ.get(key)
            if not v:
                raise RuntimeError(f"Missing required env var: {key}")
            return v

        admin_raw = os.environ.get("ADMIN_IDS", "")
        try:
            admin_ids = frozenset(
                int(x.strip()) for x in admin_raw.split(",") if x.strip()
            )
        except ValueError as e:
            raise RuntimeError(
                "ADMIN_IDS must be a comma-separated list of Telegram user IDs"
            ) from e

        def _bool(key: str, default: bool = False) -> bool:
            raw = os.environ.get(key)
            if raw is None:
                return default
            return raw.strip().lower() in {"1", "true", "yes", "on"}

        return cls(
            reviews_bot_token=_req("REVIEWS_BOT_TOKEN"),
            private_bot_token=_req("PRIVATE_BOT_TOKEN"),
            admin_ids=admin_ids,
            database_path=os.environ.get("DATABASE_PATH", "./bots.db"),
            segment_links={
                "ru_reviews": _req("RU_REVIEWS_LINK"),
                "foreign_reviews": _req("FOREIGN_REVIEWS_LINK"),
                "ru_private": _req("RU_PRIVATE_LINK"),
                "foreign_private": _req("FOREIGN_PRIVATE_LINK"),
            },
            private_access_secret=os.environ.get("PRIVATE_ACCESS_SECRET", ""),
            private_require_access_token=_bool("PRIVATE_REQUIRE_ACCESS_TOKEN"),
        )

    def token_for(self, bot_kind: str) -> str:
        if bot_kind == "reviews":
            return self.reviews_bot_token
        if bot_kind == "private":
            return self.private_bot_token
        raise ValueError(f"Unknown bot_kind: {bot_kind}")


def is_valid_segment(bot_kind: str, segment: str) -> bool:
    return segment in SEGMENTS_BY_BOT.get(bot_kind, frozenset())
