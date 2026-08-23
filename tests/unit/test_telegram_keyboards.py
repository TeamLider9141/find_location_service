from app.presentation.telegram.keyboards.menu import (
    ADD_PLACE_BUTTON,
    CANCEL_BUTTON,
    MY_PLACES_BUTTON,
    NEARBY_BUTTON,
    SEARCH_BUTTON,
    SETTINGS_BUTTON,
    build_main_menu_keyboard,
)


def test_main_menu_offers_every_entry_point() -> None:
    keyboard = build_main_menu_keyboard()

    labels = [button.text for row in keyboard.keyboard for button in row]

    assert labels == [
        SEARCH_BUTTON,
        NEARBY_BUTTON,
        ADD_PLACE_BUTTON,
        MY_PLACES_BUTTON,
        SETTINGS_BUTTON,
    ]


def test_main_menu_resizes() -> None:
    assert build_main_menu_keyboard().resize_keyboard is True


def test_cancel_is_a_command_not_a_menu_button() -> None:
    labels = [
        button.text for row in build_main_menu_keyboard().keyboard for button in row
    ]

    assert CANCEL_BUTTON not in labels
