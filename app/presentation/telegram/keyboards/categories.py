from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.domain.value_objects.category import PlaceCategory

CATEGORY_LABELS: dict[PlaceCategory, str] = {
    PlaceCategory.RESTAURANT: "🍽 Oshxona",
    PlaceCategory.CAFE: "☕ Kafe",
    PlaceCategory.FUEL: "⛽ Gas quyish shaxobchasi",
    PlaceCategory.HOTEL: "🏨 Mehmonxona",
    PlaceCategory.PARKING: "🅿️ Parking",
    PlaceCategory.CAR_SERVICE: "🔧 Usta / servis",
}


def category_label(category: PlaceCategory) -> str:
    return CATEGORY_LABELS.get(category, category.value)


def editable_categories() -> list[PlaceCategory]:
    return list(CATEGORY_LABELS)


def build_add_category_keyboard(location_index: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=category_label(category),
                    callback_data=f"add_category:{location_index}:{category.value}",
                )
            ]
            for category in editable_categories()
        ]
    )


def build_save_confirmation_keyboard(location_index: int, category: PlaceCategory) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Tasdiqlash",
                    callback_data=f"confirm_save:{location_index}:{category.value}",
                )
            ],
            [InlineKeyboardButton(text="Bekor qilish", callback_data="cancel_save")],
        ]
    )


def build_saved_place_actions_keyboard(saved_place_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Kategoriya o'zgartirish",
                    callback_data=f"saved_category:{saved_place_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="O'chirish",
                    callback_data=f"saved_delete:{saved_place_id}",
                )
            ],
        ]
    )


def build_update_category_keyboard(saved_place_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=category_label(category),
                    callback_data=f"update_category:{saved_place_id}:{category.value}",
                )
            ]
            for category in editable_categories()
        ]
    )


def build_delete_confirmation_keyboard(saved_place_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ O'chirishni tasdiqlash",
                    callback_data=f"confirm_delete:{saved_place_id}",
                )
            ],
            [InlineKeyboardButton(text="Bekor qilish", callback_data="cancel_delete")],
        ]
    )
