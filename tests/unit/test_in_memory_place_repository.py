from datetime import datetime, timezone

import pytest

from app.domain.entities.place import Place
from app.domain.value_objects.category import PlaceCategory
from app.domain.value_objects.coordinates import Coordinates
from app.infrastructure.repositories.in_memory_places import InMemoryPlaceRepository


def make_place(
    name: str = "Газпром",
    categories: tuple[PlaceCategory, ...] = (PlaceCategory.FUEL,),
    latitude: float = 55.75,
    longitude: float = 37.61,
    user_id: int = 42,
    note: str = "",
) -> Place:
    return Place(
        id=0,
        added_by_user_id=user_id,
        name=name,
        categories=categories,
        coordinates=Coordinates(latitude=latitude, longitude=longitude),
        note=note,
        created_at=datetime(2026, 1, 1),
    )


def test_add_assigns_incrementing_ids() -> None:
    repository = InMemoryPlaceRepository()

    first = repository.add(make_place(name="Первое"))
    second = repository.add(make_place(name="Второе"))

    assert (first.id, second.id) == (1, 2)


def test_search_matches_normalized_name() -> None:
    repository = InMemoryPlaceRepository()
    repository.add(make_place(name="Газпром"))

    assert [place.name for place in repository.search(name="gazprom")] == ["Газпром"]


def test_nearby_sorts_by_distance_and_drops_far_places() -> None:
    repository = InMemoryPlaceRepository()
    repository.add(make_place(name="Дальше", latitude=55.7700))
    repository.add(make_place(name="Ближе", latitude=55.7510))
    repository.add(make_place(name="Слишком далеко", latitude=56.5000))

    results = repository.nearby(
        Coordinates(latitude=55.7500, longitude=37.6100),
        radius_meters=5_000,
    )

    assert [place.name for place in results] == ["Ближе", "Дальше"]


def test_delete_by_another_user_returns_false() -> None:
    repository = InMemoryPlaceRepository()
    stored = repository.add(make_place(user_id=42))

    assert repository.delete(stored.id, user_id=7) is False
    assert repository.get(stored.id) is not None


def test_find_duplicates_matches_overlapping_names_in_radius() -> None:
    repository = InMemoryPlaceRepository()
    repository.add(make_place(name="Газпром", latitude=55.7500, longitude=37.6100))

    duplicates = repository.find_duplicates(
        name="Газпром 24",
        coordinates=Coordinates(latitude=55.7500, longitude=37.6100),
        radius_meters=200,
    )

    assert [place.name for place in duplicates] == ["Газпром"]


def test_update_by_another_user_changes_nothing() -> None:
    repository = InMemoryPlaceRepository()
    stored = repository.add(make_place(name="Газпром", user_id=42))

    assert repository.update(stored.id, user_id=7, name="Взломано") is None
    unchanged = repository.get(stored.id)
    assert unchanged is not None
    assert unchanged.name == "Газпром"


def test_update_by_the_author_changes_the_name() -> None:
    repository = InMemoryPlaceRepository()
    stored = repository.add(make_place(name="Газпром", user_id=42))

    updated = repository.update(stored.id, user_id=42, name="Лукойл")

    assert updated is not None
    assert updated.name == "Лукойл"
    # Re-read, not just the return value: a double that returned an updated
    # Place without storing it would look right to every caller that never
    # looks the place up again.
    reread = repository.get(stored.id)
    assert reread is not None
    assert reread.name == "Лукойл"


def test_update_with_an_empty_note_clears_it() -> None:
    repository = InMemoryPlaceRepository()
    stored = repository.add(make_place(note="кругл", user_id=42))

    updated = repository.update(stored.id, user_id=42, note="")

    assert updated is not None
    assert updated.note == ""


def test_update_with_none_leaves_fields_alone() -> None:
    repository = InMemoryPlaceRepository()
    stored = repository.add(make_place(name="Газпром", note="кругл", user_id=42))

    updated = repository.update(stored.id, user_id=42, category=PlaceCategory.CAFE)

    assert updated is not None
    assert updated.name == "Газпром"
    assert updated.note == "кругл"


def test_find_duplicates_ignores_a_stored_blank_name() -> None:
    # One row with a blank name must not report itself as everyone's duplicate:
    # every string contains the empty string. This was a real bug in the SQLite
    # repository, and a double without the same guard would hide it.
    repository = InMemoryPlaceRepository()
    repository.add(make_place(name="   ", latitude=55.7500, longitude=37.6100))

    duplicates = repository.find_duplicates(
        name="Лукойл",
        coordinates=Coordinates(latitude=55.7500, longitude=37.6100),
        radius_meters=200,
    )

    assert duplicates == []


def test_list_by_author_returns_newest_first() -> None:
    repository = InMemoryPlaceRepository()
    repository.add(make_place(name="Первое", user_id=42))
    repository.add(make_place(name="Второе", user_id=42))
    repository.add(make_place(name="Чужое", user_id=7))

    results = repository.list_by_author(user_id=42)

    assert [place.name for place in results] == ["Второе", "Первое"]


def test_nearby_with_a_negative_limit_returns_nothing() -> None:
    # Matches the real repository, which clamps with max(limit, 0). Two places
    # inside the radius, because a raw negative slice on a one-element list
    # comes out empty by accident and would pass against the bug.
    repository = InMemoryPlaceRepository()
    repository.add(make_place(name="Ближе", latitude=55.7510, longitude=37.6100))
    repository.add(make_place(name="Дальше", latitude=55.7600, longitude=37.6100))

    results = repository.nearby(
        Coordinates(latitude=55.7500, longitude=37.6100),
        radius_meters=5_000,
        limit=-1,
    )

    assert results == []


def test_search_with_a_negative_limit_returns_everything() -> None:
    # SQLite reads a negative LIMIT as "no limit"; the double copies that.
    repository = InMemoryPlaceRepository()
    repository.add(make_place(name="Альфа"))
    repository.add(make_place(name="Бета"))

    assert len(repository.search(limit=-1)) == 2


def test_add_stamps_created_at_instead_of_trusting_the_caller() -> None:
    # The real INSERT omits created_at, so CURRENT_TIMESTAMP always wins.
    repository = InMemoryPlaceRepository()

    stored = repository.add(make_place())

    assert stored.created_at != datetime(2026, 1, 1)
    assert stored.created_at.tzinfo is None


def test_update_writes_a_blank_name_rather_than_ignoring_it() -> None:
    # "" means "set the name to empty", the same way note="" clears the note.
    # Rejecting a blank name is the use case layer's job, not the repository's.
    repository = InMemoryPlaceRepository()
    stored = repository.add(make_place(name="Газпром", user_id=42))

    updated = repository.update(stored.id, user_id=42, name="")

    assert updated is not None
    assert updated.name == ""


def test_delete_by_the_author_actually_removes_the_place() -> None:
    # The refusal path was covered, the success path only by its return value.
    repository = InMemoryPlaceRepository()
    stored = repository.add(make_place(user_id=42))

    assert repository.delete(stored.id, user_id=42) is True
    assert repository.get(stored.id) is None


def test_add_stamps_naive_utc_to_the_second() -> None:
    # CURRENT_TIMESTAMP is naive UTC with one-second resolution. Local time or
    # kept microseconds would both drift away from what SQLite writes.
    repository = InMemoryPlaceRepository()

    stored = repository.add(make_place())

    assert stored.created_at.microsecond == 0
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    assert abs((now - stored.created_at).total_seconds()) < 5


def test_search_rejects_a_non_enum_category_even_when_empty() -> None:
    # The real repository reads category.value before it queries, so it raises
    # whether or not anything would have matched.
    repository = InMemoryPlaceRepository()

    with pytest.raises(AttributeError):
        repository.search(category="fuel")  # type: ignore[arg-type]


def test_nearby_rejects_a_non_enum_category_even_when_empty() -> None:
    repository = InMemoryPlaceRepository()

    with pytest.raises(AttributeError):
        repository.nearby(
            Coordinates(latitude=55.75, longitude=37.61),
            radius_meters=5_000,
            category="fuel",  # type: ignore[arg-type]
        )


def test_update_rejects_a_non_enum_category_rather_than_storing_it() -> None:
    # Storing the raw string would leave a Place whose category is not a
    # PlaceCategory, poisoning every later read of that place.
    repository = InMemoryPlaceRepository()
    stored = repository.add(make_place(categories=(PlaceCategory.FUEL,), user_id=42))

    with pytest.raises(AttributeError):
        repository.update(stored.id, user_id=42, category="cafe")  # type: ignore[arg-type]

    unchanged = repository.get(stored.id)
    assert unchanged is not None
    assert unchanged.category is PlaceCategory.FUEL


def test_add_rejects_a_non_enum_category_rather_than_storing_it() -> None:
    # Storing the raw string would leave a Place whose category is not a
    # PlaceCategory, poisoning every later read of that place.
    repository = InMemoryPlaceRepository()

    with pytest.raises(AttributeError):
        repository.add(make_place(categories=("fuel",)))  # type: ignore[arg-type]

    assert repository.search() == []


def test_add_rejects_none_as_a_category_rather_than_storing_it() -> None:
    # category is required here, unlike the optional filter parameter on
    # search/nearby/update: None must raise, not be treated as "no filter".
    # A stored None would poison every later category-filtered read.
    repository = InMemoryPlaceRepository()

    with pytest.raises(AttributeError):
        repository.add(make_place(categories=(None,)))  # type: ignore[arg-type]

    assert repository.search() == []


def test_search_skips_the_places_an_offset_names() -> None:
    # Pagination reads the same ordering twice and steps past what it showed.
    repository = InMemoryPlaceRepository()
    for name in ("Ажур", "Берёзка", "Ветерок"):
        repository.add(make_place(name=name))

    first = repository.search(category=PlaceCategory.FUEL, limit=2)
    second = repository.search(category=PlaceCategory.FUEL, limit=2, offset=2)

    assert [place.name for place in first] == ["Ажур", "Берёзка"]
    assert [place.name for place in second] == ["Ветерок"]


def test_an_offset_past_the_end_finds_nothing() -> None:
    repository = InMemoryPlaceRepository()
    repository.add(make_place())

    assert repository.search(limit=10, offset=10) == []
