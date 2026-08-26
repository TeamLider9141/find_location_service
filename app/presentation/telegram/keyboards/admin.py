from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.application.use_cases.admin import UsersPage
from app.application.use_cases.documents import AdminDocumentsPage
from app.domain.entities.place import Place
from app.presentation.telegram.admin_formatters import standing_mark

USERS_PAGE_SIZE = 5


def build_admin_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 Statistika", callback_data="admin:stats")],
            [InlineKeyboardButton(text="👥 Foydalanuvchilar", callback_data="admin:users:0")],
            [InlineKeyboardButton(text="🗺 Userlar manzillari", callback_data="admin:places")],
            [InlineKeyboardButton(text="📁 Hujjatlar", callback_data="admin:documents:0")],
            [InlineKeyboardButton(text="🧾 O'chirishlar jurnali", callback_data="admin:deletions")],
            [InlineKeyboardButton(text="🔎 Top qidiruvlar", callback_data="admin:searches")],
            [InlineKeyboardButton(text="📢 Xabar yuborish", callback_data="admin:broadcast")],
        ]
    )


def build_users_page_keyboard(page: UsersPage) -> InlineKeyboardMarkup:
    # The same 📍/👁‍🗨 mark as the list text: the button is what the admin
    # actually taps, so it has to answer the same question at a glance.
    rows = [
        [
            InlineKeyboardButton(
                text=f"{standing_mark(row)}{row.user.full_name} — {row.places} ta joy",
                callback_data=f"admin:user:{row.user.id}",
            )
        ]
        for row in page.rows
    ]

    navigation: list[InlineKeyboardButton] = []
    if page.page > 0:
        navigation.append(
            InlineKeyboardButton(text="⬅️", callback_data=f"admin:users:{page.page - 1}")
        )
    # Offer the next page only when rows remain behind this one, otherwise the
    # arrow opens an empty list and the admin cannot tell it from a bug.
    if (page.page + 1) * page.page_size < page.total:
        navigation.append(
            InlineKeyboardButton(text="➡️", callback_data=f"admin:users:{page.page + 1}")
        )
    if navigation:
        rows.append(navigation)

    rows.append([InlineKeyboardButton(text="⬅ Admin menyu", callback_data="admin:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_user_detail_keyboard(
    places: list[Place], user_id: int, page: int = 0, may_add: bool = False
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"🗑 {place.name}",
                callback_data=f"admin:place_delete:{place.id}",
            )
        ]
        for place in places
    ]
    # One button, matching the standing: granting an approved driver again or
    # revoking a stranger would both be no-ops dressed as actions.
    if may_add:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🚫 Joy qo'shish ruxsatini olib tashlash",
                    callback_data=f"admin:revoke_add:{user_id}",
                )
            ]
        )
    else:
        rows.append(
            [
                InlineKeyboardButton(
                    text="✅ Joy qo'shish ruxsatini berish",
                    callback_data=f"admin:grant_add:{user_id}",
                )
            ]
        )
    rows.append(
        [InlineKeyboardButton(text="⬅ Ro'yxatga", callback_data=f"admin:users:{max(page, 0)}")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_add_access_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Ruxsat berish",
                    callback_data=f"admin:allow_add:{user_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⛔ Rad etish",
                    callback_data=f"admin:deny_add:{user_id}",
                )
            ],
        ]
    )


def build_admin_delete_confirmation_keyboard(place_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Ha, o'chir",
                    callback_data=f"admin:place_delete_confirm:{place_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Bekor qilish",
                    callback_data="admin:place_delete_cancel",
                )
            ],
        ]
    )


def build_broadcast_confirmation_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📤 Hammaga yuborish",
                    callback_data="admin:broadcast:send",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Bekor qilish",
                    callback_data="admin:broadcast:cancel",
                )
            ],
        ]
    )


def build_deletion_log_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📄 HTML ko'rinishda yuklab olish",
                    callback_data="admin:deletions_html",
                )
            ],
            [InlineKeyboardButton(text="⬅ Admin menyu", callback_data="admin:home")],
        ]
    )


def build_admin_documents_keyboard(page: AdminDocumentsPage) -> InlineKeyboardMarkup:
    navigation: list[InlineKeyboardButton] = []
    if page.page > 0:
        navigation.append(
            InlineKeyboardButton(text="⬅️", callback_data=f"admin:documents:{page.page - 1}")
        )
    if (page.page + 1) * page.page_size < page.total:
        navigation.append(
            InlineKeyboardButton(text="➡️", callback_data=f"admin:documents:{page.page + 1}")
        )

    rows = [navigation] if navigation else []
    rows.append([InlineKeyboardButton(text="⬅ Admin menyu", callback_data="admin:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def add_back_row(markup: InlineKeyboardMarkup, target: str) -> InlineKeyboardMarkup:
    """The same keyboard with one ⬅️ row under it.

    Every nested page needs its way back; the shared builders — categories,
    borders — cannot know whose flow they serve, so the caller appends it.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            *markup.inline_keyboard,
            [InlineKeyboardButton(text="⬅️", callback_data=target)],
        ]
    )


def build_back_keyboard(target: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⬅️", callback_data=target)]]
    )


def build_back_to_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅ Admin menyu", callback_data="admin:home")]
        ]
    )
