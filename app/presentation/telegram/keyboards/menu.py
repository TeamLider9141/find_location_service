from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

SEARCH_BUTTON = "🔎 Qidirish"
NEARBY_BUTTON = "📍 Yaqin atrofda"
ADD_PLACE_BUTTON = "➕ Joy qo'shish"
MY_PLACES_BUTTON = "📒 Mening joylarim"
SETTINGS_BUTTON = "⚙️ Sozlamalar"
CANCEL_BUTTON = "/cancel"


def build_main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=SEARCH_BUTTON)],
            [
                KeyboardButton(text=NEARBY_BUTTON),
                KeyboardButton(text=ADD_PLACE_BUTTON),
            ],
            [
                KeyboardButton(text=MY_PLACES_BUTTON),
                KeyboardButton(text=SETTINGS_BUTTON),
            ],
        ],
        resize_keyboard=True,
    )


# Deprecated aliases kept until the old handlers are removed (Task 24).
SEARCH_LOCATION_BUTTON = SEARCH_BUTTON
ADD_LOCATION_BUTTON = ADD_PLACE_BUTTON
SAVED_LOCATIONS_BUTTON = MY_PLACES_BUTTON
