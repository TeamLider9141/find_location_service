from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.domain.entities.location import Location
from app.presentation.telegram.keyboards.categories import category_label, editable_categories


def build_locations_keyboard(locations: list[Location]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"{index}. {location.name}",
                    callback_data=f"location:{index - 1}",
                )
            ]
            for index, location in enumerate(locations, start=1)
        ]
    )


def build_selected_location_actions_keyboard(location_index: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="➕ Manzil qo'shish",
                    callback_data=f"add_location:{location_index}",
                )
            ],
            *[
                [
                    InlineKeyboardButton(
                        text=f"Atrofda: {category_label(category)}",
                        callback_data=f"nearby:{location_index}:{category.value}",
                    )
                ]
                for category in editable_categories()
            ],
            [
                InlineKeyboardButton(
                    text="📡 Hozirgi lokatsiyamdan izlash",
                    callback_data="nearby_realtime:start",
                )
            ],
        ]
    )


def build_realtime_nearby_categories_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=category_label(category),
                    callback_data=f"nearby_realtime:{category.value}",
                )
            ]
            for category in editable_categories()
        ]
    )
