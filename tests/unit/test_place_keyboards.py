from aiogram.types import InlineKeyboardMarkup

from app.domain.value_objects.category import PlaceCategory
from app.presentation.telegram.keyboards.categories import category_label
from app.presentation.telegram.keyboards.places import (
    build_category_choice_keyboard,
    build_duplicate_confirmation_keyboard,
    build_my_place_actions_keyboard,
    build_place_delete_confirmation_keyboard,
    build_place_results_keyboard,
    build_update_category_keyboard,
)


def _callback_data(keyboard: InlineKeyboardMarkup) -> list[str]:
    return [button.callback_data for row in keyboard.inline_keyboard for button in row]


def _texts(keyboard: InlineKeyboardMarkup) -> list[str]:
    return [button.text for row in keyboard.inline_keyboard for button in row]


def test_category_choice_offers_every_category() -> None:
    keyboard = build_category_choice_keyboard("pick")

    assert _callback_data(keyboard) == [
        f"pick:{category.value}" for category in PlaceCategory
    ]


def test_category_choice_labels_every_button() -> None:
    # Iterating PlaceCategory instead of the label table is what keeps a
    # category from silently vanishing from the UI, so the labels have to come
    # from the same table the rest of the bot uses.
    keyboard = build_category_choice_keyboard("pick")

    assert _texts(keyboard) == [category_label(category) for category in PlaceCategory]


def test_place_results_carry_database_ids_not_indexes() -> None:
    keyboard = build_place_results_keyboard([101, 205])

    assert _callback_data(keyboard) == ["place:101", "place:205"]


def test_place_results_are_numbered_from_one() -> None:
    # The buttons sit under a numbered list of results, so the label is the
    # position in that list while the callback stays the database id.
    keyboard = build_place_results_keyboard([101, 205])

    assert _texts(keyboard) == ["1", "2"]


def test_place_results_with_nothing_to_show_is_empty() -> None:
    assert build_place_results_keyboard([]).inline_keyboard == []


def test_duplicate_confirmation_offers_both_answers() -> None:
    assert _callback_data(build_duplicate_confirmation_keyboard()) == [
        "add_place:duplicate:yes",
        "add_place:duplicate:no",
    ]


def test_my_place_actions_target_one_place() -> None:
    assert _callback_data(build_my_place_actions_keyboard(7)) == [
        "my_place:category:7",
        "my_place:delete:7",
    ]


def test_update_category_keyboard_targets_one_place() -> None:
    keyboard = build_update_category_keyboard(7)

    assert _callback_data(keyboard) == [
        f"my_place:set_category:7:{category.value}" for category in PlaceCategory
    ]


def test_delete_confirmation_offers_both_answers() -> None:
    assert _callback_data(build_place_delete_confirmation_keyboard(7)) == [
        "my_place:confirm_delete:7",
        "my_place:cancel_delete",
    ]


def test_every_button_sits_in_its_own_row() -> None:
    # The handlers parse callback_data, not layout, but a two-button row would
    # break the row[0] indexing the existing keyboard tests rely on.
    keyboards = [
        build_category_choice_keyboard("pick"),
        build_place_results_keyboard([101, 205]),
        build_duplicate_confirmation_keyboard(),
        build_my_place_actions_keyboard(7),
        build_update_category_keyboard(7),
        build_place_delete_confirmation_keyboard(7),
    ]

    for keyboard in keyboards:
        assert all(len(row) == 1 for row in keyboard.inline_keyboard)


def test_a_place_that_fits_nothing_else_has_a_category() -> None:
    # Without a fallback a driver either abandons the place or files it under a
    # category it does not belong to, and the second is worse: everyone
    # searching that category now gets a wrong answer.
    keyboard = build_category_choice_keyboard("add_place:category")

    assert f"add_place:category:{PlaceCategory.OTHER.value}" in _callback_data(keyboard)


def test_the_fallback_category_is_offered_last() -> None:
    # "Boshqa" first would invite a driver to skip reading the real categories.
    keyboard = build_category_choice_keyboard("pick")

    assert _callback_data(keyboard)[-1] == f"pick:{PlaceCategory.OTHER.value}"


def test_the_fallback_category_is_labelled_in_uzbek() -> None:
    assert category_label(PlaceCategory.OTHER) == "📌 Boshqa kategoriya"
