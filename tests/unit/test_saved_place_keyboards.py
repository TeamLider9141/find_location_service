from app.domain.value_objects.category import PlaceCategory
from app.domain.entities.saved_place import SavedPlace
from app.domain.value_objects.coordinates import Coordinates
from app.presentation.telegram.keyboards.categories import (
    build_add_category_keyboard,
    build_saved_place_actions_keyboard,
    build_update_category_keyboard,
)
from app.presentation.telegram.keyboards.menu import (
    ADD_LOCATION_BUTTON,
    CANCEL_BUTTON,
    SAVED_LOCATIONS_BUTTON,
    SEARCH_LOCATION_BUTTON,
    build_main_menu_keyboard,
)
from app.presentation.telegram.keyboards.saved_places import build_saved_places_keyboard
from app.presentation.telegram.keyboards.saved_places import build_saved_place_categories_keyboard


def _saved_place(saved_place_id: int, name: str) -> SavedPlace:
    return SavedPlace(
        id=saved_place_id,
        user_id=42,
        name=name,
        category=PlaceCategory.FUEL,
        coordinates=Coordinates(latitude=55.4087, longitude=37.9094),
        address="Moscow",
        source="telegram",
        source_id="venue:42",
    )


def test_main_menu_keyboard_contains_add_and_saved_locations_buttons() -> None:
    keyboard = build_main_menu_keyboard()

    # The old handlers still import these names, so they have to keep pointing
    # at real menu buttons until Task 24 removes them.
    assert SEARCH_LOCATION_BUTTON == "🔎 Qidirish"
    assert ADD_LOCATION_BUTTON == "➕ Joy qo'shish"
    assert SAVED_LOCATIONS_BUTTON == "📒 Mening joylarim"
    assert CANCEL_BUTTON == "/cancel"
    assert keyboard.keyboard[0][0].text == "🔎 Qidirish"
    assert len(keyboard.keyboard[0]) == 1
    assert keyboard.keyboard[1][1].text == "➕ Joy qo'shish"
    assert keyboard.keyboard[2][0].text == "📒 Mening joylarim"


def test_add_category_keyboard_keeps_selected_location_index_in_callback_data() -> None:
    keyboard = build_add_category_keyboard(location_index=2)

    callback_data = [row[0].callback_data for row in keyboard.inline_keyboard]

    assert f"add_category:2:{PlaceCategory.RESTAURANT.value}" in callback_data
    assert f"add_category:2:{PlaceCategory.FUEL.value}" in callback_data
    assert f"add_category:2:{PlaceCategory.HOTEL.value}" in callback_data


def test_saved_place_actions_keyboard_allows_category_change_and_delete() -> None:
    keyboard = build_saved_place_actions_keyboard(saved_place_id=7)

    assert keyboard.inline_keyboard[0][0].callback_data == "saved_category:7"
    assert keyboard.inline_keyboard[1][0].callback_data == "saved_delete:7"


def test_update_category_keyboard_targets_saved_place_id() -> None:
    keyboard = build_update_category_keyboard(saved_place_id=7)

    callback_data = [row[0].callback_data for row in keyboard.inline_keyboard]

    assert f"update_category:7:{PlaceCategory.HOTEL.value}" in callback_data
    assert f"update_category:7:{PlaceCategory.CAR_SERVICE.value}" in callback_data


def test_saved_places_keyboard_lists_saved_addresses() -> None:
    keyboard = build_saved_places_keyboard([_saved_place(3, "Cafe Driver"), _saved_place(4, "Hotel Road")])

    assert keyboard.inline_keyboard[0][0].text == "Cafe Driver"
    assert keyboard.inline_keyboard[0][0].callback_data == "saved_view:3"
    assert keyboard.inline_keyboard[1][0].text == "Hotel Road"
    assert keyboard.inline_keyboard[1][0].callback_data == "saved_view:4"


def test_saved_place_categories_keyboard_marks_empty_categories() -> None:
    keyboard = build_saved_place_categories_keyboard([_saved_place(3, "Cafe Driver")])

    buttons = {row[0].callback_data: row[0].text for row in keyboard.inline_keyboard}

    assert buttons["saved_filter:fuel"] == "⛽ Gas quyish shaxobchasi"
    assert buttons["saved_filter:hotel"] == "🏨 Mehmonxona (bo'sh)"
