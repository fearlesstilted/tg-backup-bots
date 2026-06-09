from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)


BTN_STATS = "📊 Статистика"
BTN_LAST = "📜 Последние"
BTN_BROADCAST_RU = "📣 Рассылка RU"
BTN_BROADCAST_FOREIGN = "📣 Рассылка Foreign"
BTN_HELP = "ℹ️ Помощь"


def optin_keyboard(segment: str) -> InlineKeyboardMarkup:
    text = "✅ Подтвердить" if segment.startswith("ru_") else "✅ Confirm"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=text, callback_data=f"optin:{segment}")]
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


def admin_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_STATS), KeyboardButton(text=BTN_LAST)],
            [
                KeyboardButton(text=BTN_BROADCAST_RU),
                KeyboardButton(text=BTN_BROADCAST_FOREIGN),
            ],
            [KeyboardButton(text=BTN_HELP)],
        ],
        resize_keyboard=True,
        input_field_placeholder="Выберите действие",
    )
