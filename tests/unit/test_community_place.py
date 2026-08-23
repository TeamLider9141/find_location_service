from datetime import datetime

from app.domain.entities.community_place import Place
from app.domain.value_objects.category import PlaceCategory
from app.domain.value_objects.coordinates import Coordinates


def test_place_carries_author_and_optional_note() -> None:
    place = Place(
        id=1,
        added_by_user_id=42,
        name="Газпром",
        category=PlaceCategory.FUEL,
        coordinates=Coordinates(latitude=55.75, longitude=37.61),
        note="",
        created_at=datetime(2026, 8, 23, 12, 0, 0),
    )

    assert place.added_by_user_id == 42
    assert place.note == ""


def test_place_is_immutable() -> None:
    place = Place(
        id=1,
        added_by_user_id=42,
        name="Газпром",
        category=PlaceCategory.FUEL,
        coordinates=Coordinates(latitude=55.75, longitude=37.61),
        note="",
        created_at=datetime(2026, 8, 23, 12, 0, 0),
    )

    try:
        place.name = "Лукойл"  # type: ignore[misc]
    except AttributeError:
        return
    raise AssertionError("Place must be frozen")
