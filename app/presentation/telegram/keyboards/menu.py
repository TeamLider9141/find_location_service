from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

SEARCH_LOCATION_BUTTON = "🔎 Manzil qidirish"
ADD_LOCATION_BUTTON = "➕ Manzil qo'shish"
SAVED_LOCATIONS_BUTTON = "📍 Saqlangan manzillar"
CANCEL_BUTTON = "/cancel"
SETTINGS_BUTTON = "⚙️ Sozlamalar"


def build_main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=SEARCH_LOCATION_BUTTON)],
            [
                KeyboardButton(text=ADD_LOCATION_BUTTON),
                KeyboardButton(text=SAVED_LOCATIONS_BUTTON),
            ],
            [
                KeyboardButton(text=CANCEL_BUTTON),
                KeyboardButton(text=SETTINGS_BUTTON),
            ],
        ],
        resize_keyboard=True,
    )
