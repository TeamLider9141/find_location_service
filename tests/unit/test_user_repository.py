from datetime import datetime

import pytest

from app.infrastructure.database.sqlite_users import SQLiteUserRepository
from app.infrastructure.repositories.in_memory_users import InMemoryUserRepository

# Both implementations answer the same questions, and the admin panel reads them
# through the protocol, so every test here runs against both.


@pytest.fixture(params=["memory", "sqlite"])
def repository(request, tmp_path):
    if request.param == "memory":
        return InMemoryUserRepository()
    return SQLiteUserRepository(tmp_path / "users.sqlite3")


def test_an_unseen_user_is_unknown(repository) -> None:
    assert repository.get(42) is None


def test_record_seen_stores_the_user(repository) -> None:
    repository.record_seen(42, full_name="Ali Valiev", username="ali")

    user = repository.get(42)

    assert user is not None
    assert (user.id, user.full_name, user.username) == (42, "Ali Valiev", "ali")


def test_record_seen_stamps_both_timestamps(repository) -> None:
    repository.record_seen(42, full_name="Ali", username=None)

    user = repository.get(42)

    assert user is not None
    assert isinstance(user.first_seen_at, datetime)
    assert isinstance(user.last_seen_at, datetime)


def test_seeing_a_user_again_keeps_the_first_visit(repository) -> None:
    # first_seen_at answers "when did this driver join"; overwriting it on every
    # message would make every user look new.
    repository.record_seen(42, full_name="Ali", username="ali")
    first_seen = repository.get(42).first_seen_at

    repository.record_seen(42, full_name="Ali Valiev", username="alivaliev")
    user = repository.get(42)

    assert user.first_seen_at == first_seen
    assert (user.full_name, user.username) == ("Ali Valiev", "alivaliev")


def test_a_user_without_a_username_is_stored(repository) -> None:
    repository.record_seen(42, full_name="Ali", username=None)

    assert repository.get(42).username is None


def test_count_reports_distinct_users(repository) -> None:
    repository.record_seen(1, full_name="A", username=None)
    repository.record_seen(2, full_name="B", username=None)
    repository.record_seen(1, full_name="A", username=None)

    assert repository.count() == 2


def test_list_page_returns_the_total_and_the_slice(repository) -> None:
    for user_id in range(1, 6):
        repository.record_seen(user_id, full_name=f"User {user_id}", username=None)

    total, page = repository.list_page(offset=0, limit=2)

    assert total == 5
    assert len(page) == 2


def test_list_page_walks_without_repeating(repository) -> None:
    for user_id in range(1, 6):
        repository.record_seen(user_id, full_name=f"User {user_id}", username=None)

    _, first = repository.list_page(offset=0, limit=2)
    _, second = repository.list_page(offset=2, limit=2)

    assert {user.id for user in first}.isdisjoint({user.id for user in second})


def test_list_page_past_the_end_is_empty(repository) -> None:
    repository.record_seen(1, full_name="A", username=None)

    total, page = repository.list_page(offset=50, limit=10)

    assert (total, page) == (1, [])


def test_all_ids_lists_every_user_for_a_broadcast(repository) -> None:
    repository.record_seen(1, full_name="A", username=None)
    repository.record_seen(2, full_name="B", username=None)

    assert sorted(repository.all_ids()) == [1, 2]


def test_searches_are_counted_per_user(repository) -> None:
    repository.record_search(42, "газпром")
    repository.record_search(42, "лукойл")
    repository.record_search(7, "кафе")

    assert repository.search_count(42) == 2


def test_total_searches_counts_every_user(repository) -> None:
    repository.record_search(1, "газпром")
    repository.record_search(2, "кафе")

    assert repository.total_searches() == 2


def test_top_searches_rank_by_repetition(repository) -> None:
    for _ in range(3):
        repository.record_search(1, "газпром")
    repository.record_search(2, "кафе")

    assert repository.top_searches(limit=10)[0] == ("газпром", 3)


def test_top_searches_respects_the_limit(repository) -> None:
    for query in ("a", "b", "c"):
        repository.record_search(1, query)

    assert len(repository.top_searches(limit=2)) == 2


def test_the_same_query_from_two_users_counts_twice(repository) -> None:
    # The ranking answers "what do drivers look for", not "how many drivers", so
    # repeats from one user and from many both count.
    repository.record_search(1, "газпром")
    repository.record_search(2, "газпром")

    assert repository.top_searches(limit=10) == [("газпром", 2)]


def test_a_blank_query_is_not_logged(repository) -> None:
    repository.record_search(1, "   ")

    assert repository.top_searches(limit=10) == []
    assert repository.search_count(1) == 0
