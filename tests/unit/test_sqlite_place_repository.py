from datetime import datetime

import pytest

from app.domain.entities.community_place import Place
from app.domain.value_objects.category import PlaceCategory
from app.domain.value_objects.coordinates import Coordinates
from app.infrastructure.database.sqlite_places import SQLitePlaceRepository


@pytest.fixture
def repository(tmp_path) -> SQLitePlaceRepository:
    return SQLitePlaceRepository(tmp_path / "places.sqlite3")


def make_place(
    name: str = "Газпром",
    category: PlaceCategory = PlaceCategory.FUEL,
    latitude: float = 55.75,
    longitude: float = 37.61,
    user_id: int = 42,
    note: str = "",
) -> Place:
    return Place(
        id=0,
        added_by_user_id=user_id,
        name=name,
        category=category,
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
    repository.add(make_place(name="Газпром", category=PlaceCategory.FUEL))
    repository.add(make_place(name="Придорожное", category=PlaceCategory.RESTAURANT))

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
    repository.add(make_place(name="Газпром", category=PlaceCategory.FUEL))
    repository.add(make_place(name="Газпром кафе", category=PlaceCategory.CAFE))

    results = repository.search(name="газпром", category=PlaceCategory.CAFE)

    assert [place.name for place in results] == ["Газпром кафе"]


def test_search_by_blank_name_is_treated_as_no_name_filter(
    repository: SQLitePlaceRepository,
) -> None:
    repository.add(make_place(name="Газпром"))

    assert len(repository.search(name="   ")) == 1
