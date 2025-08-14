from __future__ import annotations

from typing import Optional

from aiogram.types import InlineKeyboardMarkup
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
        title = f"{(t.artist or 'Unknown')} — {(t.title or 'Untitled')}"
        kb.button(text=title, callback_data=f"my:play:{t.id}")

    # 6-я строка — навигация
    nav_row: list[tuple[str, str]] = []
    q = query if (query and query.strip()) else "-"
    if offset > 0:
        nav_row.append(("⬅️ Назад", f"my:page:{max(offset - limit, 0)}:{q}"))
    if has_more:
        nav_row.append(("➡️ Вперёд", f"my:page:{offset + limit}:{q}"))
    if nav_row:
        kb.row(
            *[
                kb.button(text=txt, callback_data=data).as_markup().inline_keyboard[0][0]
                for txt, data in nav_row
            ]
        )

    # 7-я строка — закрыть
    kb.button(text="❌ Закрыть", callback_data="my:close")
    kb.adjust(1)

    return kb.as_markup()
