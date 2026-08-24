from datetime import datetime, timezone
from math import degrees

import pytest

from app.application.use_cases.places import (
    AddPlaceUseCase,
    DeletePlaceUseCase,
    FindPlacesUseCase,
    GetPlaceUseCase,
    ListMyPlacesUseCase,
    NearbyPlacesUseCase,
    UpdatePlaceUseCase,
)
from app.domain.entities.place import Place
from app.domain.value_objects.category import PlaceCategory
from app.domain.value_objects.coordinates import Coordinates
from app.infrastructure.repositories.in_memory_deletions import InMemoryDeletionLog
from app.infrastructure.repositories.in_memory_places import InMemoryPlaceRepository

_EARTH_RADIUS_METERS = 6_371_000


def _north_by_meters(coordinates: Coordinates, meters: float) -> Coordinates:
    """Offset ``coordinates`` due north by ``meters``, longitude unchanged."""
    delta_lat_degrees = degrees(meters / _EARTH_RADIUS_METERS)
    return Coordinates(
        latitude=coordinates.latitude + delta_lat_degrees,
        longitude=coordinates.longitude,
    )


def test_add_place_stores_the_contribution() -> None:
    repository = InMemoryPlaceRepository()
    use_case = AddPlaceUseCase(repository)

    place = use_case.execute(
        user_id=42,
        name="Газпром",
        categories=(PlaceCategory.FUEL,),
        coordinates=Coordinates(latitude=55.75, longitude=37.61),
        note="M5, 120 км",
    )

    assert place.id > 0
    assert place.added_by_user_id == 42
    assert place.note == "M5, 120 км"
    assert place.created_at.tzinfo is None
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    assert abs((now - place.created_at).total_seconds()) < 5


def test_add_place_defaults_the_note_to_empty() -> None:
    repository = InMemoryPlaceRepository()
    use_case = AddPlaceUseCase(repository)

    place = use_case.execute(
        user_id=42,
        name="Газпром",
        categories=(PlaceCategory.FUEL,),
        coordinates=Coordinates(latitude=55.75, longitude=37.61),
    )

    assert place.note == ""


def test_add_place_rejects_a_blank_name() -> None:
    use_case = AddPlaceUseCase(InMemoryPlaceRepository())

    with pytest.raises(ValueError):
        use_case.execute(
            user_id=42,
            name="   ",
            categories=(PlaceCategory.FUEL,),
            coordinates=Coordinates(latitude=55.75, longitude=37.61),
        )


def test_add_place_finds_duplicates_within_the_default_radius_but_not_beyond_it() -> None:
    # DEFAULT_DUPLICATE_RADIUS_METERS is 200. A place seeded at the exact query
    # point would report a duplicate at any non-negative radius, so this pins
    # the boundary with two seeded places: one inside it, one outside it.
    repository = InMemoryPlaceRepository()
    use_case = AddPlaceUseCase(repository)
    query_point = Coordinates(latitude=55.75, longitude=37.61)
    near_point = _north_by_meters(query_point, 150)
    far_point = _north_by_meters(query_point, 300)

    # The offsets are computed, not guessed — check them against the same
    # distance function the repository uses before trusting anything below.
    assert abs(query_point.distance_to(near_point) - 150) < 1
    assert abs(query_point.distance_to(far_point) - 300) < 1

    use_case.execute(
        user_id=42,
        name="Газпром",
        categories=(PlaceCategory.FUEL,),
        coordinates=near_point,
        note="near",
    )
    use_case.execute(
        user_id=42,
        name="Газпром",
        categories=(PlaceCategory.FUEL,),
        coordinates=far_point,
        note="far",
    )

    duplicates = use_case.find_duplicates(name="Газпром", coordinates=query_point)

    assert [place.note for place in duplicates] == ["near"]


def test_find_places_matches_name_or_category() -> None:
    repository = InMemoryPlaceRepository()
    add = AddPlaceUseCase(repository)
    add.execute(
        user_id=42,
        name="Газпром",
        categories=(PlaceCategory.FUEL,),
        coordinates=Coordinates(latitude=55.75, longitude=37.61),
    )
    add.execute(
        user_id=42,
        name="Придорожное",
        categories=(PlaceCategory.RESTAURANT,),
        coordinates=Coordinates(latitude=55.76, longitude=37.62),
    )
    use_case = FindPlacesUseCase(repository)

    assert [p.name for p in use_case.execute(name="gazprom")] == ["Газпром"]
    assert [p.name for p in use_case.execute(category=PlaceCategory.RESTAURANT)] == [
        "Придорожное"
    ]


def test_find_places_default_limit_is_ten() -> None:
    # A one-element result list can't tell a correct limit and ordering from a
    # hardcoded, swapped, or reversed one, so this seeds more than a page.
    # Inserted in reverse so insertion order (and id order) is the opposite of
    # name order — a test that inserted ascending couldn't tell "sorted by
    # name" from "sorted by id", since both would produce the same sequence.
    repository = InMemoryPlaceRepository()
    add = AddPlaceUseCase(repository)
    for index in reversed(range(12)):
        add.execute(
            user_id=42,
            name=f"АЗС {index:02d}",
            categories=(PlaceCategory.FUEL,),
            coordinates=Coordinates(latitude=55.75, longitude=37.61),
        )
    use_case = FindPlacesUseCase(repository)

    default_results = use_case.execute(category=PlaceCategory.FUEL)
    limited_results = use_case.execute(category=PlaceCategory.FUEL, limit=3)

    assert [p.name for p in default_results] == [f"АЗС {i:02d}" for i in range(10)]
    assert [p.name for p in limited_results] == [f"АЗС {i:02d}" for i in range(3)]


def test_nearby_places_returns_closest_first() -> None:
    repository = InMemoryPlaceRepository()
    add = AddPlaceUseCase(repository)
    add.execute(
        user_id=42,
        name="Дальше",
        categories=(PlaceCategory.FUEL,),
        coordinates=Coordinates(latitude=55.7700, longitude=37.6100),
    )
    add.execute(
        user_id=42,
        name="Ближе",
        categories=(PlaceCategory.FUEL,),
        coordinates=Coordinates(latitude=55.7510, longitude=37.6100),
    )
    use_case = NearbyPlacesUseCase(repository)

    results = use_case.execute(
        Coordinates(latitude=55.7500, longitude=37.6100),
        radius_meters=5_000,
    )

    assert [place.name for place in results] == ["Ближе", "Дальше"]


def test_nearby_places_default_limit_is_ten() -> None:
    # A two-place seed can't tell a correct default limit from one hardcoded
    # smaller, or one left unbounded, so this seeds more than a page at
    # distinct, increasing distances — the note carries the intended rank so
    # the assertion pins both the count and the closest-first ordering.
    repository = InMemoryPlaceRepository()
    add = AddPlaceUseCase(repository)
    query_point = Coordinates(latitude=55.75, longitude=37.61)
    for index in range(12):
        add.execute(
            user_id=42,
            name=f"АЗС {index:02d}",
            categories=(PlaceCategory.FUEL,),
            coordinates=_north_by_meters(query_point, 100 * (index + 1)),
            note=str(index),
        )
    use_case = NearbyPlacesUseCase(repository)

    default_results = use_case.execute(query_point, radius_meters=5_000)
    limited_results = use_case.execute(query_point, radius_meters=5_000, limit=3)

    assert [place.note for place in default_results] == [str(i) for i in range(10)]
    assert [place.note for place in limited_results] == [str(i) for i in range(3)]


def test_nearby_places_filters_by_category() -> None:
    repository = InMemoryPlaceRepository()
    add = AddPlaceUseCase(repository)
    add.execute(
        user_id=42,
        name="АЗС",
        categories=(PlaceCategory.FUEL,),
        coordinates=Coordinates(latitude=55.7510, longitude=37.6100),
    )
    add.execute(
        user_id=42,
        name="Кафе",
        categories=(PlaceCategory.CAFE,),
        coordinates=Coordinates(latitude=55.7505, longitude=37.6100),
    )
    use_case = NearbyPlacesUseCase(repository)
    query_point = Coordinates(latitude=55.7500, longitude=37.6100)

    filtered = use_case.execute(
        query_point, radius_meters=5_000, category=PlaceCategory.FUEL
    )
    unfiltered = use_case.execute(query_point, radius_meters=5_000)

    assert [place.name for place in filtered] == ["АЗС"]
    assert {place.name for place in unfiltered} == {"АЗС", "Кафе"}


def test_add_place_trims_the_note() -> None:
    # The note is stored verbatim — nothing normalizes it later — so the use
    # case is the only place that can strip what the driver typed.
    repository = InMemoryPlaceRepository()
    use_case = AddPlaceUseCase(repository)

    place = use_case.execute(
        user_id=42,
        name="Газпром",
        categories=(PlaceCategory.FUEL,),
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
        categories=(PlaceCategory.FUEL,),
        coordinates=Coordinates(latitude=55.75, longitude=37.61),
    )

    assert place.name == "Газпром"


def _seed(repository: InMemoryPlaceRepository, user_id: int = 42) -> Place:
    return AddPlaceUseCase(repository).execute(
        user_id=user_id,
        name="Газпром",
        categories=(PlaceCategory.FUEL,),
        coordinates=Coordinates(latitude=55.75, longitude=37.61),
        note="кругл",
    )


def test_list_my_places_returns_only_my_contributions() -> None:
    repository = InMemoryPlaceRepository()
    _seed(repository, user_id=42)
    _seed(repository, user_id=7)

    results = ListMyPlacesUseCase(repository).execute(user_id=42)

    assert [place.added_by_user_id for place in results] == [42]


def test_get_place_returns_the_place_whoever_asks() -> None:
    # Reading is not author-scoped: the whole point of the shared database is
    # that another driver can open a place they did not add.
    repository = InMemoryPlaceRepository()
    stored = _seed(repository, user_id=42)

    found = GetPlaceUseCase(repository).execute(stored.id)

    assert found is not None
    assert found.id == stored.id


def test_get_place_returns_none_for_a_missing_id() -> None:
    repository = InMemoryPlaceRepository()

    assert GetPlaceUseCase(repository).execute(999) is None


def test_update_place_changes_the_category() -> None:
    repository = InMemoryPlaceRepository()
    stored = _seed(repository)

    updated = UpdatePlaceUseCase(repository).execute(
        place_id=stored.id,
        user_id=42,
        category=PlaceCategory.CAFE,
    )

    assert updated is not None
    assert updated.category is PlaceCategory.CAFE


def test_update_place_by_another_user_returns_none() -> None:
    repository = InMemoryPlaceRepository()
    stored = _seed(repository)

    updated = UpdatePlaceUseCase(repository).execute(
        place_id=stored.id,
        user_id=7,
        category=PlaceCategory.CAFE,
    )

    assert updated is None
    unchanged = repository.get(stored.id)
    assert unchanged is not None
    assert unchanged.category is PlaceCategory.FUEL


def test_update_place_rejects_a_blank_name() -> None:
    repository = InMemoryPlaceRepository()
    stored = _seed(repository)

    with pytest.raises(ValueError):
        UpdatePlaceUseCase(repository).execute(
            place_id=stored.id,
            user_id=42,
            name="   ",
        )

    unchanged = repository.get(stored.id)
    assert unchanged is not None
    assert unchanged.name == "Газпром"


def test_update_place_trims_the_name() -> None:
    repository = InMemoryPlaceRepository()
    stored = _seed(repository)

    updated = UpdatePlaceUseCase(repository).execute(
        place_id=stored.id,
        user_id=42,
        name="  Лукойл  ",
    )

    assert updated is not None
    assert updated.name == "Лукойл"


def test_update_place_trims_the_note_and_can_clear_it() -> None:
    # note="" means "remove the note", so the strip must not turn a blank note
    # into None and leave the old text in place.
    repository = InMemoryPlaceRepository()
    stored = _seed(repository)

    trimmed = UpdatePlaceUseCase(repository).execute(
        place_id=stored.id, user_id=42, note="  M5, 120 км  "
    )
    assert trimmed is not None
    assert trimmed.note == "M5, 120 км"

    cleared = UpdatePlaceUseCase(repository).execute(
        place_id=stored.id, user_id=42, note="   "
    )
    assert cleared is not None
    assert cleared.note == ""


def test_update_place_with_nothing_to_change_leaves_the_place_alone() -> None:
    repository = InMemoryPlaceRepository()
    stored = _seed(repository)

    updated = UpdatePlaceUseCase(repository).execute(place_id=stored.id, user_id=42)

    assert updated is not None
    assert updated.name == "Газпром"
    assert updated.category is PlaceCategory.FUEL
    assert updated.note == "кругл"


def test_delete_place_by_the_author_succeeds() -> None:
    repository = InMemoryPlaceRepository()
    stored = _seed(repository)

    deleter = DeletePlaceUseCase(repository, InMemoryDeletionLog())
    # The snapshot comes back so the caller can name what disappeared.
    assert deleter.execute(stored.id, user_id=42).name == stored.name
    assert repository.get(stored.id) is None


def test_delete_place_by_another_user_fails() -> None:
    repository = InMemoryPlaceRepository()
    stored = _seed(repository)

    deleter = DeletePlaceUseCase(repository, InMemoryDeletionLog())
    assert deleter.execute(stored.id, user_id=7) is None
    assert repository.get(stored.id) is not None
