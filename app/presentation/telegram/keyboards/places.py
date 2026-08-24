from typing import Mapping

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.domain.value_objects.category import PlaceCategory
from app.presentation.telegram.keyboards.categories import category_label


# The borders live behind one button: two flags at the top level would crowd
# the list, and more borders may follow.
BORDER_CATEGORIES = (PlaceCategory.BORDER_KZ, PlaceCategory.BORDER_RU)
BORDER_GROUP_VALUE = "borders"
BORDER_GROUP_LABEL = "🛂 Chegara hududlari"
CHOOSE_BORDER_MESSAGE = "Qaysi chegara hududi?"


def build_category_choice_keyboard(
    prefix: str, counts: Mapping[PlaceCategory, int] | None = None
) -> InlineKeyboardMarkup:
    """One button per category, each callback prefixed by the caller's flow.

    ``counts`` appends "(N ta)" to each label, so a driver picks a category
    knowing whether anything waits behind it. Left off where the number would
    be noise — choosing a category for a new place, say.

    The border categories fold into one group button; tapping it is answered
    with ``build_border_choice_keyboard`` by every flow that uses this one.
    """
    # Iterating PlaceCategory rather than the label table keeps the keyboard in
    # step with the enum: a category added to the domain shows up here without a
    # second edit. A label table that fell behind is what hid CAFE from the UI
    # before.
    rows = []
    for category in PlaceCategory:
        if category in BORDER_CATEGORIES:
            continue
        if category is PlaceCategory.OTHER:
            # The group sits where its members would have been: before the
            # fallback, which stays last.
            rows.append(
                [
                    InlineKeyboardButton(
                        text=_border_group_label(counts),
                        callback_data=f"{prefix}:{BORDER_GROUP_VALUE}",
                    )
                ]
            )
        rows.append(
            [
                InlineKeyboardButton(
                    text=_category_button_label(category, counts),
                    callback_data=f"{prefix}:{category.value}",
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_border_choice_keyboard(
    prefix: str, counts: Mapping[PlaceCategory, int] | None = None
) -> InlineKeyboardMarkup:
    """The individual borders, shown once the group button is tapped."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=_category_button_label(category, counts),
                    callback_data=f"{prefix}:{category.value}",
                )
            ]
            for category in BORDER_CATEGORIES
        ]
    )


def _border_group_label(counts: Mapping[PlaceCategory, int] | None) -> str:
    total = sum((counts or {}).get(category, 0) for category in BORDER_CATEGORIES)
    return f"{BORDER_GROUP_LABEL} ({total} ta)" if total else BORDER_GROUP_LABEL


def _category_button_label(
    category: PlaceCategory, counts: Mapping[PlaceCategory, int] | None
) -> str:
    label = category_label(category)
    total = (counts or {}).get(category, 0)
    # An empty category keeps its plain label — "(0 ta)" reads like a shrug.
    return f"{label} ({total} ta)" if total else label


def build_place_results_keyboard(place_ids: list[int]) -> InlineKeyboardMarkup:
    """Buttons carry the database id, so a later search cannot shift the target."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"{index}", callback_data=f"place:{place_id}")]
            for index, place_id in enumerate(place_ids, start=1)
        ]
    )


def build_duplicate_confirmation_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Ha, qo'sh",
                    callback_data="add_place:duplicate:yes",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Yo'q",
                    callback_data="add_place:duplicate:no",
                )
            ],
        ]
    )


def build_my_place_actions_keyboard(place_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Kategoriyani o'zgartirish",
                    callback_data=f"my_place:category:{place_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="O'chirish",
                    callback_data=f"my_place:delete:{place_id}",
                )
            ],
        ]
    )


def build_update_category_keyboard(place_id: int) -> InlineKeyboardMarkup:
    # The same fold as everywhere else: the callback pattern lines up because
    # "prefix" here simply ends with the place id.
    return build_category_choice_keyboard(f"my_place:set_category:{place_id}")


def build_place_delete_confirmation_keyboard(place_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ O'chirishni tasdiqlash",
                    callback_data=f"my_place:confirm_delete:{place_id}",
                )
            ],
            # No place_id on cancel: nothing is deleted, so there is nothing to
            # target, and a stale id here would be one more thing to validate.
            [
                InlineKeyboardButton(
                    text="Bekor qilish",
                    callback_data="my_place:cancel_delete",
                )
            ],
        ]
    )
