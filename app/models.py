from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class User:
    id: int
    telegram_id: int
    bot_kind: str
    segment: str
    opted_in: bool
    is_active: bool


@dataclass
class Broadcast:
    id: int
    bot_kind: str
    segment: str
    text: str
    status: str
    total: int
    sent: int
    failed: int
    blocked: int
    created_by: int
    created_at: str
    finished_at: Optional[str]
