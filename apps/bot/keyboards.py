from __future__ import annotations

from typing import Optional

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from core.db.models import Track


def _short(s: str, limit: int = 30) -> str:
    s = s.strip()
    return s if len(s) <= limit else s[:limit]


def make_like_cb(track_id: int, ctx: str, offset: int, query: Optional[str]) -> str:
    q = _short(query or "-")
    return f"like:t:{track_id}:o:{ctx}:p:{offset}:q:{q}"


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
        play_btn = InlineKeyboardButton(text=title, callback_data=f"my:play:{t.id}")
        remove_btn = InlineKeyboardButton(
            text="💔", callback_data=make_like_cb(t.id, "m", offset, query)
        )
        kb.row(play_btn, remove_btn)

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


def build_like_toggle_kb(
    track_id: int, liked: bool, ctx: str, offset: int = 0, query: Optional[str] = None
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    text = "💔" if liked else "❤️"
    kb.button(text=text, callback_data=make_like_cb(track_id, ctx, offset, query))
    return kb.as_markup()
