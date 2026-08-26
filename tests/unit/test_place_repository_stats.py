from datetime import datetime

import pytest

from app.domain.entities.place import Place
from app.domain.value_objects.category import PlaceCategory
from app.domain.value_objects.coordinates import Coordinates
from app.infrastructure.database.sqlite_places import SQLitePlaceRepository
from app.infrastructure.repositories.in_memory_places import InMemoryPlaceRepository

# The admin panel reads these through the protocol, so both implementations have
# to answer identically.


@pytest.fixture(params=["memory", "sqlite"])
def repository(request, tmp_path):
    if request.param == "memory":
        return InMemoryPlaceRepository()
    return SQLitePlaceRepository(tmp_path / "places.sqlite3")


def add(repository, name="Газпром", categories=(PlaceCategory.FUEL,), user_id=42) -> Place:
    return repository.add(
        Place(
            id=0,
            added_by_user_id=user_id,
            name=name,
            categories=categories,
            coordinates=Coordinates(latitude=55.75, longitude=37.61),
            note="",
            created_at=datetime(2026, 1, 1),
        )
    )


def test_an_empty_database_counts_zero(repository) -> None:
    assert repository.count() == 0


def test_count_grows_with_every_place(repository) -> None:
    add(repository)
    add(repository, name="Лукойл")

    assert repository.count() == 2


def test_places_added_today_are_counted_as_recent(repository) -> None:
    add(repository)

    assert repository.count_added_since(days=7) == 1


def test_a_zero_day_window_counts_only_today(repository) -> None:
    add(repository)

    assert repository.count_added_since(days=0) == 1


def test_category_counts_are_grouped(repository) -> None:
    add(repository, categories=(PlaceCategory.FUEL,))
    add(repository, name="Кафе Оазис", categories=(PlaceCategory.CAFE,))
    add(repository, name="Лукойл", categories=(PlaceCategory.FUEL,))

    counts = repository.count_by_category()

    assert counts[PlaceCategory.FUEL] == 2
    assert counts[PlaceCategory.CAFE] == 1


def test_categories_nobody_used_are_absent(repository) -> None:
    add(repository, categories=(PlaceCategory.FUEL,))

    assert PlaceCategory.HOTEL not in repository.count_by_category()


def test_top_authors_rank_by_contribution(repository) -> None:
    add(repository, user_id=1)
    add(repository, name="Лукойл", user_id=1)
    add(repository, name="Кафе", user_id=2)

    assert repository.top_authors(limit=10)[0] == (1, 2)


def test_top_authors_respects_the_limit(repository) -> None:
    add(repository, user_id=1)
    add(repository, name="Лукойл", user_id=2)

    assert len(repository.top_authors(limit=1)) == 1


def test_admin_delete_removes_a_place_owned_by_someone_else(repository) -> None:
    # Moderation is the one path that ignores authorship: a wrong or abusive
    # place has to be removable even when its author never comes back.
    stored = add(repository, user_id=1)

    assert repository.delete_any(stored.id) is True
    assert repository.get(stored.id) is None


def test_admin_delete_of_a_missing_place_reports_failure(repository) -> None:
    assert repository.delete_any(999) is False


def test_excluded_authors_places_are_left_out_of_the_counts(repository) -> None:
    # The ordinary admin rung is not shown the super admins' contributions.
    add(repository, name="Газпром", user_id=42)
    add(repository, name="Лукойл", user_id=99)

    counts = repository.count_by_category(exclude_author_ids=(99,))

    assert counts[PlaceCategory.FUEL] == 1


def test_count_by_author_totals_every_contributor(repository) -> None:
    # Ordering the whole user list by contribution needs every author's count,
    # not the top slice top_authors returns.
    add(repository, user_id=1)
    add(repository, name="Лукойл", user_id=1)
    add(repository, name="Кафе", user_id=2)

    assert repository.count_by_author() == {1: 2, 2: 1}


def test_count_by_author_of_an_empty_database_is_empty(repository) -> None:
    assert repository.count_by_author() == {}
