from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.domain.entities.saved_place import SavedPlace
from app.domain.value_objects.category import PlaceCategory
from app.presentation.telegram.keyboards.categories import category_label, editable_categories


def build_saved_place_categories_keyboard(saved_places: list[SavedPlace]) -> InlineKeyboardMarkup:
    occupied_categories = {saved_place.category for saved_place in saved_places}
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=_saved_category_button_text(category, occupied_categories),
                    callback_data=f"saved_filter:{category.value}",
                )
            ]
            for category in editable_categories()
        ]
    )


def build_saved_places_keyboard(saved_places: list[SavedPlace]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=saved_place.name,
                    callback_data=f"saved_view:{saved_place.id}",
                )
            ]
            for saved_place in saved_places
        ]
    )


def _saved_category_button_text(
    category: PlaceCategory,
    occupied_categories: set[PlaceCategory],
) -> str:
    label = category_label(category)
    if category not in occupied_categories:
        return f"{label} (bo'sh)"
    return label
