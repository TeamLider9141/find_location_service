from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.application.use_cases.documents import DocumentsPage
from app.domain.entities.place import Place

PLACES_PER_PICK_PAGE = 7


def build_documents_page_keyboard(page: DocumentsPage) -> InlineKeyboardMarkup:
    """Numbered buttons open one document each; arrows walk the pages.

    Buttons carry the database id, so a document added while the list was on
    screen cannot shift the target.
    """
    first_number = page.page * page.page_size + 1
    number_row = [
        InlineKeyboardButton(
            text=f"{index}", callback_data=f"docs:open:{card.document.id}"
        )
        for index, card in enumerate(page.rows, start=first_number)
    ]

    rows = [number_row] if number_row else []
    navigation = _navigation_row(
        page.page, page.total, page.page_size, prefix="docs:page"
    )
    if navigation:
        rows.append(navigation)
    return InlineKeyboardMarkup(inline_keyboard=rows)


DOCUMENTED_MARK = "📝"


def build_place_pick_keyboard(
    places: list[Place],
    page: int,
    prefix: str = "add_doc",
    documented: frozenset[int] = frozenset(),
) -> InlineKeyboardMarkup:
    """One button per place for pinning a document, seven a page.

    ``documented`` marks the places that already carry documents — the caller
    has ranked them first, and the mark says why they lead the list.
    """
    start = page * PLACES_PER_PICK_PAGE
    rows = [
        [
            InlineKeyboardButton(
                text=(
                    f"{DOCUMENTED_MARK} {place.name}"
                    if place.id in documented
                    else place.name
                ),
                callback_data=f"{prefix}:place:{place.id}",
            )
        ]
        for place in places[start : start + PLACES_PER_PICK_PAGE]
    ]

    navigation = _navigation_row(
        page, len(places), PLACES_PER_PICK_PAGE, prefix=f"{prefix}:pick_page"
    )
    if navigation:
        rows.append(navigation)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_document_preview_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💾 Saqlash", callback_data="add_doc:save"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔁 Faylni qayta tashlash", callback_data="add_doc:refile"
                )
            ],
            [
                InlineKeyboardButton(
                    text="✏️ Izohni o'zgartirish", callback_data="add_doc:renote"
                )
            ],
        ]
    )


def build_my_data_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📒 Mening joylarim", callback_data="my_data:places"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🗂 Mening hujjatlarim", callback_data="my_data:documents"
                )
            ],
        ]
    )


def build_my_document_actions_keyboard(document_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🖼 Fayl/rasmni almashtirish",
                    callback_data=f"my_doc:refile:{document_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="✏️ Izohni almashtirish",
                    callback_data=f"my_doc:renote:{document_id}",
                )
            ],
        ]
    )


def _navigation_row(
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
