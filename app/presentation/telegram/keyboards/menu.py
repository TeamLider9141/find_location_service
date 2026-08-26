from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

SEARCH_BUTTON = "🔎 Manzillar"
DOCUMENTS_BUTTON = "🗂 Manzildagi hujjatlar"
NEARBY_BUTTON = "📍 Yaqin atrofda"
ADD_PLACE_BUTTON = "➕ Joy qo'shish"
MY_DATA_BUTTON = "📁 Mening ma'lumotlarim"
SETTINGS_BUTTON = "⚙️ Sozlamalar"
ADMIN_BUTTON = "🛠 Admin"
ADD_DOCUMENT_BUTTON = "➕ Hujjat qo'shish"
CANCEL_BUTTON = "/cancel"


def build_main_menu_keyboard(
    is_admin: bool = False, can_add_documents: bool = False
) -> ReplyKeyboardMarkup:
    keyboard = [
        [
            KeyboardButton(text=SEARCH_BUTTON),
            KeyboardButton(text=DOCUMENTS_BUTTON),
        ],
        [
            KeyboardButton(text=NEARBY_BUTTON),
            KeyboardButton(text=ADD_PLACE_BUTTON),
        ],
        [
            KeyboardButton(text=MY_DATA_BUTTON),
            KeyboardButton(text=SETTINGS_BUTTON),
        ],
    ]
    # Reply keyboards are drawn per driver, so a button can simply not exist
    # for everyone else instead of answering them with a refusal. Adding a
    # document rides on the same right as adding a place, so admins and the
    # approved see it; the panel stays admin-only.
    last_row = []
    if is_admin:
        last_row.append(KeyboardButton(text=ADMIN_BUTTON))
    if is_admin or can_add_documents:
        last_row.append(KeyboardButton(text=ADD_DOCUMENT_BUTTON))
    if last_row:
        keyboard.append(last_row)

    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)
