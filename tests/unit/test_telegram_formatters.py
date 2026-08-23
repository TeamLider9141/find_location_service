from app.domain.entities.location import Location
from app.domain.entities.place import Place
from app.domain.value_objects.category import PlaceCategory
from app.domain.value_objects.coordinates import Coordinates
from app.presentation.telegram.formatters import (
    format_nearby_places,
    format_search_results,
    format_selected_location,
    format_start_message,
)


def _location(name: str, address: str, latitude: float = 55.4087, longitude: float = 37.9094) -> Location:
    return Location(
        id=f"osm:node:{name}",
        name=name,
        address=address,
        coordinates=Coordinates(latitude=latitude, longitude=longitude),
        source="osm",
        source_id=f"node:{name}",
    )


def test_start_message_invites_driver_to_send_address() -> None:
    message = format_start_message()

    assert "manzil" in message.lower()
    assert "Домодедово аэропорт" in message


def test_search_results_are_numbered_with_addresses() -> None:
    message = format_search_results(
        [
            _location("Аэропорт Домодедово", "Московская область"),
            _location("Домодедово", "Московская область"),
        ]
    )

    assert "1. Аэропорт Домодедово" in message
    assert "2. Домодедово" in message
    assert "📍 Московская область" in message


def test_selected_location_includes_coordinates_and_map_link() -> None:
    message = format_selected_location(
        _location("Аэропорт Домодедово", "Московская область"),
        result_number=3,
    )

    assert "Natija: 3" in message
    assert "Аэропорт Домодедово" in message
    assert "55.4087, 37.9094" in message
    assert "https://www.google.com/maps/search/?api=1&query=55.4087,37.9094" in message


def test_nearby_places_are_numbered_with_distance_and_address() -> None:
    message = format_nearby_places(
        category=PlaceCategory.FUEL,
        places=[
            Place(
                id="osm:node:1",
                name="Gazprom",
                category=PlaceCategory.FUEL,
                coordinates=Coordinates(latitude=55.75, longitude=37.61),
                address="Moscow",
                phone=None,
                distance_meters=250.0,
                source="osm",
                source_id="node:1",
            )
        ],
    )

    assert "Gas quyish" in message
    assert "1. Gazprom" in message
    assert "250 m" in message
    assert "Moscow" in message
