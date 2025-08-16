from __future__ import annotations

from typing import Optional

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from core.db.models import Track


def build_my_keyboard(
    items: list[Track],
    offset: int,
    limit: int,
    has_more: bool,
    query: Optional[str],
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    # 5 строк — треки
    for t in items:
        title = f"{t.artist or 'Unknown'} — {t.title or 'Untitled'}"
        kb.row(InlineKeyboardButton(text=title, callback_data=f"my:play:{t.id}"))

    # 6-я — навигация
    q = (query or "").strip() or "-"
    nav: list[InlineKeyboardButton] = []
    if offset > 0:
        nav.append(
            InlineKeyboardButton(
                text="⬅️ Назад", callback_data=f"my:page:{max(offset - limit, 0)}:{q}"
            )
        )
    if has_more:
        nav.append(
            InlineKeyboardButton(text="➡️ Вперёд", callback_data=f"my:page:{offset + limit}:{q}")
        )
    if nav:
        kb.row(*nav)

    # 7-я — закрыть
    kb.row(InlineKeyboardButton(text="❌ Закрыть", callback_data="my:close"))

    return kb.as_markup()
