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
    ]
    # Reply keyboards are drawn per driver, so a button can simply not exist
    # for everyone else instead of answering them with a refusal. Everything
    # behind the add right — the driver's own data and the document button —
    # is drawn only for admins and the approved; the panel stays admin-only.
    # The handlers still keep their gates: a keyboard drawn before the right
    # was revoked keeps its buttons until the next redraw.
    contributor = is_admin or can_add_documents
    third_row = []
    if contributor:
        third_row.append(KeyboardButton(text=MY_DATA_BUTTON))
    third_row.append(KeyboardButton(text=SETTINGS_BUTTON))
    keyboard.append(third_row)

    last_row = []
    if is_admin:
        last_row.append(KeyboardButton(text=ADMIN_BUTTON))
    if contributor:
        last_row.append(KeyboardButton(text=ADD_DOCUMENT_BUTTON))
    if last_row:
        keyboard.append(last_row)

    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)
