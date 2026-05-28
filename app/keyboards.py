from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def optin_keyboard(segment: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"optin:{segment}")]
        ]
    )


def broadcast_confirm_keyboard(token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🚀 Отправить", callback_data=f"bcast:confirm:{token}"),
                InlineKeyboardButton(text="🧪 Dry-run", callback_data=f"bcast:dryrun:{token}"),
            ],
            [InlineKeyboardButton(text="✖ Отмена", callback_data=f"bcast:cancel:{token}")],
        ]
    )
