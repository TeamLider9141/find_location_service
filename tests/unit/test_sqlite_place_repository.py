from datetime import datetime

import pytest

from app.domain.entities.place import Place
from app.domain.value_objects.category import PlaceCategory
from app.domain.value_objects.coordinates import Coordinates
from app.infrastructure.database.sqlite_places import SQLitePlaceRepository


@pytest.fixture
def repository(tmp_path) -> SQLitePlaceRepository:
    return SQLitePlaceRepository(tmp_path / "places.sqlite3")


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


def test_add_assigns_an_id(repository: SQLitePlaceRepository) -> None:
    stored = repository.add(make_place())

    assert stored.id > 0
    assert stored.name == "Газпром"


def test_add_stamps_created_at(repository: SQLitePlaceRepository) -> None:
    stored = repository.add(make_place())

    assert isinstance(stored.created_at, datetime)


def test_get_returns_the_place_for_any_user(repository: SQLitePlaceRepository) -> None:
    stored = repository.add(make_place(user_id=42))

    found = repository.get(stored.id)

    assert found is not None
    assert found.added_by_user_id == 42
    assert found.coordinates.latitude == pytest.approx(55.75)


def test_get_returns_none_for_unknown_id(repository: SQLitePlaceRepository) -> None:
    assert repository.get(999) is None


def test_search_by_category_returns_only_that_category(
    repository: SQLitePlaceRepository,
) -> None:
    repository.add(make_place(name="Газпром", categories=(PlaceCategory.FUEL,)))
    repository.add(make_place(name="Придорожное", categories=(PlaceCategory.RESTAURANT,)))

    results = repository.search(category=PlaceCategory.FUEL)

    assert [place.name for place in results] == ["Газпром"]


def test_search_without_filters_returns_everything(
    repository: SQLitePlaceRepository,
) -> None:
    repository.add(make_place(name="Газпром"))
    repository.add(make_place(name="Лукойл"))

    assert len(repository.search()) == 2


def test_search_respects_limit(repository: SQLitePlaceRepository) -> None:
    for index in range(5):
        repository.add(make_place(name=f"Газпром {index}"))

    assert len(repository.search(limit=2)) == 2


def test_search_by_name_matches_a_substring(repository: SQLitePlaceRepository) -> None:
    repository.add(make_place(name="Кафе У Дороги"))
    repository.add(make_place(name="Газпром"))

    results = repository.search(name="дороги")

    assert [place.name for place in results] == ["Кафе У Дороги"]


def test_search_by_latin_name_finds_a_cyrillic_record(
    repository: SQLitePlaceRepository,
) -> None:
    repository.add(make_place(name="Газпром"))

    results = repository.search(name="gazprom")

    assert [place.name for place in results] == ["Газпром"]


def test_search_by_name_and_category_applies_both(
    repository: SQLitePlaceRepository,
) -> None:
    repository.add(make_place(name="Газпром", categories=(PlaceCategory.FUEL,)))
    repository.add(make_place(name="Газпром кафе", categories=(PlaceCategory.CAFE,)))

    results = repository.search(name="газпром", category=PlaceCategory.CAFE)

    assert [place.name for place in results] == ["Газпром кафе"]


def test_search_by_blank_name_is_treated_as_no_name_filter(
    repository: SQLitePlaceRepository,
) -> None:
    repository.add(make_place(name="Газпром"))

    assert len(repository.search(name="   ")) == 1


def test_nearby_excludes_places_outside_the_radius(
    repository: SQLitePlaceRepository,
) -> None:
    # ~1.1 km north of the origin.
    repository.add(make_place(name="Близко", latitude=55.7600, longitude=37.6100))
    # ~11 km north of the origin.
    repository.add(make_place(name="Далеко", latitude=55.8500, longitude=37.6100))

    results = repository.nearby(
        Coordinates(latitude=55.7500, longitude=37.6100),
        radius_meters=5_000,
    )

    assert [place.name for place in results] == ["Близко"]


def test_nearby_sorts_by_distance(repository: SQLitePlaceRepository) -> None:
    repository.add(make_place(name="Дальше", latitude=55.7700, longitude=37.6100))
    repository.add(make_place(name="Ближе", latitude=55.7510, longitude=37.6100))

    results = repository.nearby(
        Coordinates(latitude=55.7500, longitude=37.6100),
        radius_meters=5_000,
    )

    assert [place.name for place in results] == ["Ближе", "Дальше"]


def test_nearby_can_filter_by_category(repository: SQLitePlaceRepository) -> None:
    repository.add(
        make_place(name="Заправка", latitude=55.7510, categories=(PlaceCategory.FUEL,))
    )
    repository.add(
        make_place(name="Кафе", latitude=55.7511, categories=(PlaceCategory.CAFE,))
    )

    results = repository.nearby(
        Coordinates(latitude=55.7500, longitude=37.6100),
        radius_meters=5_000,
        category=PlaceCategory.CAFE,
    )

    assert [place.name for place in results] == ["Кафе"]


def test_nearby_respects_limit(repository: SQLitePlaceRepository) -> None:
    for index in range(5):
        repository.add(make_place(name=f"Место {index}", latitude=55.7500 + index / 1000))

    results = repository.nearby(
        Coordinates(latitude=55.7500, longitude=37.6100),
        radius_meters=5_000,
        limit=2,
    )

    assert len(results) == 2


def test_nearby_keeps_places_just_inside_the_radius(
    repository: SQLitePlaceRepository,
) -> None:
    # 4997.9 m due north. A bounding box built from a flat 111_320 m per degree
    # reaches only 4994.4 m, so it would drop this place before the exact
    # distance check ever saw it.
    repository.add(make_place(name="Впритык", latitude=55.79494719, longitude=37.6100))

    results = repository.nearby(
        Coordinates(latitude=55.7500, longitude=37.6100),
        radius_meters=5_000,
    )

    assert [place.name for place in results] == ["Впритык"]


def test_nearby_measures_distance_and_not_just_the_bounding_box(
    repository: SQLitePlaceRepository,
) -> None:
    # 6241 m away, but inside the box corner — only the Haversine check rejects it.
    repository.add(make_place(name="Угол", latitude=55.7900, longitude=37.6800))
    repository.add(make_place(name="Рядом", latitude=55.7510, longitude=37.6100))

    results = repository.nearby(
        Coordinates(latitude=55.7500, longitude=37.6100),
        radius_meters=5_000,
    )

    assert [place.name for place in results] == ["Рядом"]


def test_nearby_returns_places_at_the_same_distance(
    repository: SQLitePlaceRepository,
) -> None:
    # Equidistant, so sorting must not fall back to comparing the places themselves.
    repository.add(make_place(name="Север", latitude=55.7600, longitude=37.6100))
    repository.add(make_place(name="Юг", latitude=55.7400, longitude=37.6100))

    results = repository.nearby(
        Coordinates(latitude=55.7500, longitude=37.6100),
        radius_meters=5_000,
    )

    assert {place.name for place in results} == {"Север", "Юг"}


def test_list_by_author_returns_only_that_users_places(
    repository: SQLitePlaceRepository,
) -> None:
    repository.add(make_place(name="Моё", user_id=42))
    repository.add(make_place(name="Чужое", user_id=7))

    results = repository.list_by_author(42)

    assert [place.name for place in results] == ["Моё"]


def test_list_by_author_returns_newest_first(repository: SQLitePlaceRepository) -> None:
    first = repository.add(make_place(name="Первое", user_id=42))
    second = repository.add(make_place(name="Второе", user_id=42))

    results = repository.list_by_author(42)

    assert [place.id for place in results] == [second.id, first.id]


def test_find_duplicates_matches_same_name_within_radius(
    repository: SQLitePlaceRepository,
) -> None:
    repository.add(make_place(name="Газпром", latitude=55.7500, longitude=37.6100))

    duplicates = repository.find_duplicates(
        name="Газпром",
        coordinates=Coordinates(latitude=55.7501, longitude=37.6100),
        radius_meters=200,
    )

    assert [place.name for place in duplicates] == ["Газпром"]


def test_find_duplicates_ignores_same_name_outside_radius(
    repository: SQLitePlaceRepository,
) -> None:
    repository.add(make_place(name="Газпром", latitude=55.7500, longitude=37.6100))

    duplicates = repository.find_duplicates(
        name="Газпром",
        # ~1.1 km away.
        coordinates=Coordinates(latitude=55.7600, longitude=37.6100),
        radius_meters=200,
    )

    assert duplicates == []


def test_find_duplicates_matches_a_containing_name(
    repository: SQLitePlaceRepository,
) -> None:
    repository.add(make_place(name="Газпром", latitude=55.7500, longitude=37.6100))

    duplicates = repository.find_duplicates(
        name="Газпром 24",
        coordinates=Coordinates(latitude=55.7500, longitude=37.6100),
        radius_meters=200,
    )

    assert [place.name for place in duplicates] == ["Газпром"]


def test_find_duplicates_ignores_a_different_name_nearby(
    repository: SQLitePlaceRepository,
) -> None:
    repository.add(make_place(name="Газпром", latitude=55.7500, longitude=37.6100))

    duplicates = repository.find_duplicates(
        name="Лукойл",
        coordinates=Coordinates(latitude=55.7500, longitude=37.6100),
        radius_meters=200,
    )

    assert duplicates == []


def test_find_duplicates_matches_across_alphabets(
    repository: SQLitePlaceRepository,
) -> None:
    repository.add(make_place(name="Газпром", latitude=55.7500, longitude=37.6100))

    duplicates = repository.find_duplicates(
        name="Gazprom",
        coordinates=Coordinates(latitude=55.7500, longitude=37.6100),
        radius_meters=200,
    )

    assert [place.name for place in duplicates] == ["Газпром"]


def test_find_duplicates_matches_a_contained_name(
    repository: SQLitePlaceRepository,
) -> None:
    # The stored name is the longer one this time — matching runs both ways.
    repository.add(make_place(name="Газпром 24", latitude=55.7500, longitude=37.6100))

    duplicates = repository.find_duplicates(
        name="Газпром",
        coordinates=Coordinates(latitude=55.7500, longitude=37.6100),
        radius_meters=200,
    )

    assert [place.name for place in duplicates] == ["Газпром 24"]


def test_find_duplicates_ignores_a_blank_query(
    repository: SQLitePlaceRepository,
) -> None:
    repository.add(make_place(name="Газпром", latitude=55.7500, longitude=37.6100))

    duplicates = repository.find_duplicates(
        name="   ",
        coordinates=Coordinates(latitude=55.7500, longitude=37.6100),
        radius_meters=200,
    )

    assert duplicates == []


def test_find_duplicates_ignores_a_stored_blank_name(
    repository: SQLitePlaceRepository,
) -> None:
    # One row with a blank name must not report itself as everyone's duplicate.
    repository.add(make_place(name="   ", latitude=55.7500, longitude=37.6100))

    duplicates = repository.find_duplicates(
        name="Шиномонтаж",
        coordinates=Coordinates(latitude=55.7500, longitude=37.6100),
        radius_meters=200,
    )

    assert duplicates == []


def test_update_changes_the_name_and_its_search_key(
    repository: SQLitePlaceRepository,
) -> None:
    stored = repository.add(make_place(name="Газпром", user_id=42))

    updated = repository.update(stored.id, user_id=42, name="Лукойл")

    assert updated is not None
    assert updated.name == "Лукойл"
    assert [place.name for place in repository.search(name="лукойл")] == ["Лукойл"]


def test_update_changes_the_category(repository: SQLitePlaceRepository) -> None:
    stored = repository.add(make_place(categories=(PlaceCategory.FUEL,), user_id=42))

    updated = repository.update(stored.id, user_id=42, category=PlaceCategory.CAFE)

    assert updated is not None
    assert updated.category is PlaceCategory.CAFE


def test_update_with_none_leaves_fields_alone(
    repository: SQLitePlaceRepository,
) -> None:
    stored = repository.add(make_place(name="Газпром", note="кругл", user_id=42))

    updated = repository.update(stored.id, user_id=42, category=PlaceCategory.CAFE)

    assert updated is not None
    assert updated.name == "Газпром"
    assert updated.note == "кругл"


def test_update_with_empty_note_clears_it(repository: SQLitePlaceRepository) -> None:
    stored = repository.add(make_place(note="кругл", user_id=42))

    updated = repository.update(stored.id, user_id=42, note="")

    assert updated is not None
    assert updated.note == ""


def test_update_by_another_user_returns_none(
    repository: SQLitePlaceRepository,
) -> None:
    stored = repository.add(make_place(name="Газпром", user_id=42))

    assert repository.update(stored.id, user_id=7, name="Взломано") is None
    unchanged = repository.get(stored.id)
    assert unchanged is not None
    assert unchanged.name == "Газпром"


def test_delete_removes_the_place(repository: SQLitePlaceRepository) -> None:
    stored = repository.add(make_place(user_id=42))

    assert repository.delete(stored.id, user_id=42) is True
    assert repository.get(stored.id) is None


def test_delete_by_another_user_returns_false(
    repository: SQLitePlaceRepository,
) -> None:
    stored = repository.add(make_place(user_id=42))

    assert repository.delete(stored.id, user_id=7) is False
    assert repository.get(stored.id) is not None


def test_update_with_no_fields_returns_the_place_to_its_author(
    repository: SQLitePlaceRepository,
) -> None:
    stored = repository.add(make_place(name="Газпром", user_id=42))

    assert repository.update(stored.id, user_id=42) == stored


def test_update_with_no_fields_by_another_user_returns_none(
    repository: SQLitePlaceRepository,
) -> None:
    stored = repository.add(make_place(user_id=42))

    assert repository.update(stored.id, user_id=7) is None


def test_update_with_no_fields_for_a_missing_place_returns_none(
    repository: SQLitePlaceRepository,
) -> None:
    assert repository.update(999, user_id=42) is None


def test_update_writes_a_blank_name_rather_than_ignoring_it(
    repository: SQLitePlaceRepository,
) -> None:
    # "" means "set the name to empty", the same way note="" clears the note.
    # Rejecting a blank name is the use case layer's job, not the repository's.
    stored = repository.add(make_place(name="Газпром", user_id=42))

    updated = repository.update(stored.id, user_id=42, name="")

    assert updated is not None
    assert updated.name == ""


def test_search_skips_the_places_an_offset_names(repository) -> None:
    for name in ("Ажур", "Берёзка", "Ветерок"):
        repository.add(make_place(name=name))

    first = repository.search(category=PlaceCategory.FUEL, limit=2)
    second = repository.search(category=PlaceCategory.FUEL, limit=2, offset=2)

    assert [place.name for place in first] == ["Ажур", "Берёзка"]
    assert [place.name for place in second] == ["Ветерок"]


def test_an_offset_past_the_end_finds_nothing(repository) -> None:
    repository.add(make_place())

    assert repository.search(limit=10, offset=10) == []
