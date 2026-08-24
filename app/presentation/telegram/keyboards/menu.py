from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

SEARCH_BUTTON = "🔎 Qidirish"
NEARBY_BUTTON = "📍 Yaqin atrofda"
ADD_PLACE_BUTTON = "➕ Joy qo'shish"
MY_PLACES_BUTTON = "📒 Mening joylarim"
SETTINGS_BUTTON = "⚙️ Sozlamalar"
ADMIN_BUTTON = "🛠 Admin"
CANCEL_BUTTON = "/cancel"


def build_main_menu_keyboard(is_admin: bool = False) -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text=SEARCH_BUTTON)],
        [
            KeyboardButton(text=NEARBY_BUTTON),
            KeyboardButton(text=ADD_PLACE_BUTTON),
        ],
        [
            KeyboardButton(text=MY_PLACES_BUTTON),
            KeyboardButton(text=SETTINGS_BUTTON),
        ],
    ]
    # Reply keyboards are drawn per driver, so the panel button can simply not
    # exist for everyone else instead of answering them with a refusal.
    if is_admin:
        keyboard.append([KeyboardButton(text=ADMIN_BUTTON)])

    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)
