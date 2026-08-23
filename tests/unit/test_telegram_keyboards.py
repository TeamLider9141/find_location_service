from app.domain.entities.location import Location
from app.domain.value_objects.category import PlaceCategory
from app.domain.value_objects.coordinates import Coordinates
from app.presentation.telegram.keyboards.locations import (
    build_locations_keyboard,
    build_realtime_nearby_categories_keyboard,
    build_selected_location_actions_keyboard,
)


def _location(name: str) -> Location:
    return Location(
        id=f"osm:node:{name}",
        name=name,
        address="Московская область",
        coordinates=Coordinates(latitude=55.4087, longitude=37.9094),
        source="osm",
        source_id=f"node:{name}",
    )


def test_locations_keyboard_uses_stable_index_callback_data() -> None:
    keyboard = build_locations_keyboard([_location("Аэропорт Домодедово"), _location("Домодедово")])

    assert keyboard.inline_keyboard[0][0].text == "1. Аэропорт Домодедово"
    assert keyboard.inline_keyboard[0][0].callback_data == "location:0"
    assert keyboard.inline_keyboard[1][0].text == "2. Домодедово"
    assert keyboard.inline_keyboard[1][0].callback_data == "location:1"


def test_selected_location_actions_include_nearby_category_buttons() -> None:
    keyboard = build_selected_location_actions_keyboard(location_index=2)

    callback_data = [row[0].callback_data for row in keyboard.inline_keyboard]

    assert "add_location:2" in callback_data
    assert f"nearby:2:{PlaceCategory.FUEL.value}" in callback_data
    assert f"nearby:2:{PlaceCategory.HOTEL.value}" in callback_data
    assert "nearby_realtime:start" in callback_data


def test_realtime_nearby_categories_keyboard_asks_for_category_first() -> None:
    keyboard = build_realtime_nearby_categories_keyboard()

    callback_data = [row[0].callback_data for row in keyboard.inline_keyboard]

    assert f"nearby_realtime:{PlaceCategory.RESTAURANT.value}" in callback_data
    assert f"nearby_realtime:{PlaceCategory.CAR_SERVICE.value}" in callback_data
