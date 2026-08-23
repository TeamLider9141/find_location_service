from datetime import datetime

from app.application.use_cases.admin import (
    DeletePlaceAsAdminUseCase,
    GetAdminOverviewUseCase,
    GetUserDetailUseCase,
    ListBroadcastRecipientsUseCase,
    ListUsersPageUseCase,
    RecordUserVisitUseCase,
    TopSearchesUseCase,
)
from app.domain.entities.place import Place
from app.domain.value_objects.category import PlaceCategory
from app.domain.value_objects.coordinates import Coordinates
from app.infrastructure.repositories.in_memory_places import InMemoryPlaceRepository
from app.infrastructure.repositories.in_memory_users import InMemoryUserRepository


def add_place(repository, name="Газпром", category=PlaceCategory.FUEL, user_id=42) -> Place:
    return repository.add(
        Place(
            id=0,
            added_by_user_id=user_id,
            name=name,
            category=category,
            coordinates=Coordinates(latitude=55.75, longitude=37.61),
            note="",
            created_at=datetime(2026, 1, 1),
        )
    )


def test_overview_counts_places_and_users() -> None:
    places = InMemoryPlaceRepository()
    users = InMemoryUserRepository()
    add_place(places)
    users.record_seen(42, full_name="Ali", username="ali")

    overview = GetAdminOverviewUseCase(places, users).execute()

    assert (overview.total_places, overview.total_users) == (1, 1)


def test_overview_reports_the_recent_windows() -> None:
    places = InMemoryPlaceRepository()
    add_place(places)

    overview = GetAdminOverviewUseCase(places, InMemoryUserRepository()).execute()

    assert overview.places_today == 1
    assert overview.places_this_week == 1


def test_overview_breaks_places_down_by_category() -> None:
    places = InMemoryPlaceRepository()
    add_place(places, category=PlaceCategory.FUEL)
    add_place(places, name="Кафе", category=PlaceCategory.CAFE)

    overview = GetAdminOverviewUseCase(places, InMemoryUserRepository()).execute()

    assert dict(overview.categories)[PlaceCategory.FUEL] == 1


def test_overview_names_the_biggest_contributors() -> None:
    places = InMemoryPlaceRepository()
    users = InMemoryUserRepository()
    add_place(places, user_id=1)
    add_place(places, name="Лукойл", user_id=1)
    users.record_seen(1, full_name="Ali", username="ali")

    overview = GetAdminOverviewUseCase(places, users).execute()

    assert overview.top_authors[0].places == 2
    assert overview.top_authors[0].full_name == "Ali"


def test_a_contributor_the_bot_never_greeted_still_appears() -> None:
    # Places outlive the users table: rows added before user tracking existed
    # have an author the bot has no name for. Dropping them would understate
    # who contributed.
    places = InMemoryPlaceRepository()
    add_place(places, user_id=777)

    overview = GetAdminOverviewUseCase(places, InMemoryUserRepository()).execute()

    assert overview.top_authors[0].user_id == 777
    assert overview.top_authors[0].full_name is None


def test_overview_counts_searches() -> None:
    users = InMemoryUserRepository()
    users.record_search(1, "газпром")
    users.record_search(2, "кафе")

    overview = GetAdminOverviewUseCase(InMemoryPlaceRepository(), users).execute()

    assert overview.total_searches == 2


def test_user_page_reports_how_many_places_each_added() -> None:
    places = InMemoryPlaceRepository()
    users = InMemoryUserRepository()
    users.record_seen(1, full_name="Ali", username="ali")
    add_place(places, user_id=1)

    page = ListUsersPageUseCase(users, places).execute(page=0, page_size=10)

    assert page.total == 1
    assert page.rows[0].places == 1


def test_user_page_numbers_start_at_zero() -> None:
    users = InMemoryUserRepository()
    for user_id in (1, 2, 3):
        users.record_seen(user_id, full_name=f"U{user_id}", username=None)

    first = ListUsersPageUseCase(users, InMemoryPlaceRepository()).execute(page=0, page_size=2)
    second = ListUsersPageUseCase(users, InMemoryPlaceRepository()).execute(page=1, page_size=2)

    assert len(first.rows) == 2
    assert len(second.rows) == 1


def test_a_negative_page_is_read_as_the_first_page() -> None:
    users = InMemoryUserRepository()
    users.record_seen(1, full_name="Ali", username=None)

    page = ListUsersPageUseCase(users, InMemoryPlaceRepository()).execute(page=-3, page_size=10)

    assert len(page.rows) == 1


def test_user_detail_gathers_places_and_searches() -> None:
    places = InMemoryPlaceRepository()
    users = InMemoryUserRepository()
    users.record_seen(1, full_name="Ali", username="ali")
    add_place(places, user_id=1)
    users.record_search(1, "газпром")

    detail = GetUserDetailUseCase(users, places).execute(1)

    assert detail is not None
    assert detail.user.full_name == "Ali"
    assert len(detail.places) == 1
    assert detail.searches == 1


def test_user_detail_of_a_stranger_is_none() -> None:
    detail = GetUserDetailUseCase(InMemoryUserRepository(), InMemoryPlaceRepository()).execute(9)

    assert detail is None


def test_top_searches_are_ranked() -> None:
    users = InMemoryUserRepository()
    users.record_search(1, "газпром")
    users.record_search(2, "газпром")
    users.record_search(2, "кафе")

    assert TopSearchesUseCase(users).execute(limit=10)[0] == ("газпром", 2)


def test_recording_a_visit_stores_the_user() -> None:
    users = InMemoryUserRepository()

    RecordUserVisitUseCase(users).execute(42, full_name="Ali", username="ali")

    assert users.get(42) is not None


def test_a_blank_name_falls_back_to_the_user_id() -> None:
    # Telegram allows an empty last name and, for some accounts, an empty first
    # name too. A user row with no label at all is unreadable in the panel.
    users = InMemoryUserRepository()

    RecordUserVisitUseCase(users).execute(42, full_name="   ", username=None)

    assert users.get(42).full_name == "42"


def test_admin_delete_removes_someone_elses_place() -> None:
    places = InMemoryPlaceRepository()
    stored = add_place(places, user_id=1)

    assert DeletePlaceAsAdminUseCase(places).execute(stored.id) is True
    assert places.get(stored.id) is None


def test_admin_delete_reports_a_missing_place() -> None:
    assert DeletePlaceAsAdminUseCase(InMemoryPlaceRepository()).execute(404) is False


def test_broadcast_recipients_are_every_known_user() -> None:
    users = InMemoryUserRepository()
    users.record_seen(1, full_name="A", username=None)
    users.record_seen(2, full_name="B", username=None)

    assert sorted(ListBroadcastRecipientsUseCase(users).execute()) == [1, 2]
