"""One page-turning row, shared by every list that outgrows a screen."""

from aiogram.types import InlineKeyboardButton


def navigation_row(
    page: int, total: int, page_size: int, prefix: str
) -> list[InlineKeyboardButton]:
    """Back and forward, drawn only where there is somewhere to go."""
    total_pages = max(1, -(-total // page_size))
    row = []
    if page > 0:
        row.append(
            InlineKeyboardButton(text="⬅️", callback_data=f"{prefix}:{page - 1}")
        )
    if page + 1 < total_pages:
        row.append(
            InlineKeyboardButton(text="➡️", callback_data=f"{prefix}:{page + 1}")
        )
    return row
