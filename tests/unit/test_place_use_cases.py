from datetime import datetime

from app.application.use_cases.places import (
    AddPlaceUseCase,
    FindPlacesUseCase,
    NearbyPlacesUseCase,
)
from app.domain.value_objects.category import PlaceCategory
from app.domain.value_objects.coordinates import Coordinates
from app.infrastructure.repositories.in_memory_places import InMemoryPlaceRepository


def test_add_place_stores_the_contribution() -> None:
    repository = InMemoryPlaceRepository()
    use_case = AddPlaceUseCase(repository)

    place = use_case.execute(
        user_id=42,
        name="Газпром",
        category=PlaceCategory.FUEL,
        coordinates=Coordinates(latitude=55.75, longitude=37.61),
        note="M5, 120 км",
    )

    assert place.id > 0
    assert place.added_by_user_id == 42
    assert place.note == "M5, 120 км"
    assert isinstance(place.created_at, datetime)


def test_add_place_defaults_the_note_to_empty() -> None:
    repository = InMemoryPlaceRepository()
    use_case = AddPlaceUseCase(repository)

    place = use_case.execute(
        user_id=42,
        name="Газпром",
        category=PlaceCategory.FUEL,
        coordinates=Coordinates(latitude=55.75, longitude=37.61),
    )

    assert place.note == ""


def test_add_place_rejects_a_blank_name() -> None:
    use_case = AddPlaceUseCase(InMemoryPlaceRepository())

    try:
        use_case.execute(
            user_id=42,
            name="   ",
            category=PlaceCategory.FUEL,
            coordinates=Coordinates(latitude=55.75, longitude=37.61),
        )
    except ValueError:
        return
    raise AssertionError("blank name must raise ValueError")


def test_add_place_finds_duplicates_before_saving() -> None:
    repository = InMemoryPlaceRepository()
    use_case = AddPlaceUseCase(repository)
    coordinates = Coordinates(latitude=55.75, longitude=37.61)
    use_case.execute(
        user_id=42,
        name="Газпром",
        category=PlaceCategory.FUEL,
        coordinates=coordinates,
    )

    duplicates = use_case.find_duplicates(name="Газпром", coordinates=coordinates)

    assert [place.name for place in duplicates] == ["Газпром"]


def test_find_places_matches_name_or_category() -> None:
    repository = InMemoryPlaceRepository()
    add = AddPlaceUseCase(repository)
    add.execute(
        user_id=42,
        name="Газпром",
        category=PlaceCategory.FUEL,
        coordinates=Coordinates(latitude=55.75, longitude=37.61),
    )
    add.execute(
        user_id=42,
        name="Придорожное",
        category=PlaceCategory.RESTAURANT,
        coordinates=Coordinates(latitude=55.76, longitude=37.62),
    )
    use_case = FindPlacesUseCase(repository)

    assert [p.name for p in use_case.execute(name="gazprom")] == ["Газпром"]
    assert [p.name for p in use_case.execute(category=PlaceCategory.RESTAURANT)] == [
        "Придорожное"
    ]


def test_nearby_places_returns_closest_first() -> None:
    repository = InMemoryPlaceRepository()
    add = AddPlaceUseCase(repository)
    add.execute(
        user_id=42,
        name="Дальше",
        category=PlaceCategory.FUEL,
        coordinates=Coordinates(latitude=55.7700, longitude=37.6100),
    )
    add.execute(
        user_id=42,
        name="Ближе",
        category=PlaceCategory.FUEL,
        coordinates=Coordinates(latitude=55.7510, longitude=37.6100),
    )
    use_case = NearbyPlacesUseCase(repository)

    results = use_case.execute(
        Coordinates(latitude=55.7500, longitude=37.6100),
        radius_meters=5_000,
    )

    assert [place.name for place in results] == ["Ближе", "Дальше"]


def test_add_place_trims_the_note() -> None:
    # The note is stored verbatim — nothing normalizes it later — so the use
    # case is the only place that can strip what the driver typed.
    repository = InMemoryPlaceRepository()
    use_case = AddPlaceUseCase(repository)

    place = use_case.execute(
        user_id=42,
        name="Газпром",
        category=PlaceCategory.FUEL,
        coordinates=Coordinates(latitude=55.75, longitude=37.61),
        note="  M5, 120 км  ",
    )

    assert place.note == "M5, 120 км"


def test_add_place_trims_the_name_before_storing_it() -> None:
    # The stored name is what the driver sees in a result list, so the padding
    # has to go even though the search key would have ignored it.
    repository = InMemoryPlaceRepository()
    use_case = AddPlaceUseCase(repository)

    place = use_case.execute(
        user_id=42,
        name="  Газпром  ",
        category=PlaceCategory.FUEL,
        coordinates=Coordinates(latitude=55.75, longitude=37.61),
    )

    assert place.name == "Газпром"
