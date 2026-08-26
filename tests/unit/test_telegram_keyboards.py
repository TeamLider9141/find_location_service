from app.presentation.telegram.keyboards.menu import (
    ADD_DOCUMENT_BUTTON,
    ADD_PLACE_BUTTON,
    ADMIN_BUTTON,
    CANCEL_BUTTON,
    DOCUMENTS_BUTTON,
    MY_DATA_BUTTON,
    NEARBY_BUTTON,
    SEARCH_BUTTON,
    SETTINGS_BUTTON,
    build_main_menu_keyboard,
)


def labels_of(keyboard) -> list[str]:
    return [button.text for row in keyboard.keyboard for button in row]


def test_main_menu_offers_every_open_entry_point() -> None:
    labels = labels_of(build_main_menu_keyboard())

    assert labels == [
        SEARCH_BUTTON,
        DOCUMENTS_BUTTON,
        NEARBY_BUTTON,
        ADD_PLACE_BUTTON,
        SETTINGS_BUTTON,
    ]


def test_main_menu_resizes() -> None:
    assert build_main_menu_keyboard().resize_keyboard is True


def test_cancel_is_a_command_not_a_menu_button() -> None:
    assert CANCEL_BUTTON not in labels_of(build_main_menu_keyboard())


def test_the_admin_button_is_hidden_from_ordinary_drivers() -> None:
    # The reply keyboard is drawn per driver, so a button everyone can see but
    # nobody except the admin can use would just be noise.
    assert ADMIN_BUTTON not in labels_of(build_main_menu_keyboard())


def test_an_admin_gets_the_panel_and_document_buttons() -> None:
    labels = labels_of(build_main_menu_keyboard(is_admin=True))

    assert labels[-2:] == [ADMIN_BUTTON, ADD_DOCUMENT_BUTTON]


def test_an_approved_driver_gets_the_document_button_without_the_panel() -> None:
    labels = labels_of(build_main_menu_keyboard(can_add_documents=True))

    assert labels[-1] == ADD_DOCUMENT_BUTTON
    assert ADMIN_BUTTON not in labels


def test_a_plain_driver_sees_neither_admin_nor_document_button() -> None:
    labels = labels_of(build_main_menu_keyboard())

    assert ADD_DOCUMENT_BUTTON not in labels
    assert ADMIN_BUTTON not in labels


def test_my_data_is_hidden_from_a_plain_driver() -> None:
    # Hidden, not locked: a section that only answers with a refusal is
    # noise on a keyboard drawn per driver. The handler keeps its gate for
    # keyboards drawn before the right was revoked.
    assert MY_DATA_BUTTON not in labels_of(build_main_menu_keyboard())


def test_my_data_appears_for_an_admin() -> None:
    assert MY_DATA_BUTTON in labels_of(build_main_menu_keyboard(is_admin=True))


def test_my_data_appears_for_an_approved_driver() -> None:
    assert MY_DATA_BUTTON in labels_of(build_main_menu_keyboard(can_add_documents=True))
