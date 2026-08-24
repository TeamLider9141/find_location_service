from datetime import datetime

from app.application.use_cases.admin import (
    AdminPlacesByCategoryUseCase,
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
from app.infrastructure.repositories.in_memory_deletions import InMemoryDeletionLog
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


def test_recording_a_visit_tells_whether_the_user_is_new() -> None:
    # The middleware announces first visits to the admins, so "was this the
    # first" has to survive the trip through the use case.
    users = InMemoryUserRepository()
    record = RecordUserVisitUseCase(users)

    assert record.execute(42, full_name="Ali", username=None) is True
    assert record.execute(42, full_name="Ali", username=None) is False


def test_a_blank_name_falls_back_to_the_user_id() -> None:
    # Telegram allows an empty last name and, for some accounts, an empty first
    # name too. A user row with no label at all is unreadable in the panel.
    users = InMemoryUserRepository()

    RecordUserVisitUseCase(users).execute(42, full_name="   ", username=None)

    assert users.get(42).full_name == "42"


def test_admin_delete_removes_someone_elses_place() -> None:
    places = InMemoryPlaceRepository()
    stored = add_place(places, user_id=1)

    assert (
        DeletePlaceAsAdminUseCase(places, InMemoryDeletionLog()).execute(
            stored.id, deleted_by=100
        )
        is True
    )
    assert places.get(stored.id) is None


def test_admin_delete_reports_a_missing_place() -> None:
    assert (
        DeletePlaceAsAdminUseCase(InMemoryPlaceRepository(), InMemoryDeletionLog()).execute(
            404, deleted_by=100
        )
        is False
    )


def test_broadcast_recipients_are_every_known_user() -> None:
    users = InMemoryUserRepository()
    users.record_seen(1, full_name="A", username=None)
    users.record_seen(2, full_name="B", username=None)

    assert sorted(ListBroadcastRecipientsUseCase(users).execute()) == [1, 2]


def test_places_in_a_category_are_grouped_by_their_author() -> None:
    places = InMemoryPlaceRepository()
    users = InMemoryUserRepository()
    users.record_seen(1, full_name="Bobur", username=None)
    users.record_seen(2, full_name="Anvar", username="anvar")
    add_place(places, user_id=1, name="Газпром")
    add_place(places, user_id=1, name="Лукойл")
    add_place(places, user_id=2, name="Татнефть")

    groups = AdminPlacesByCategoryUseCase(places, users).execute(PlaceCategory.FUEL)

    # Ordered by the name the admin reads, places alphabetical inside a group.
    assert [(group.author_id, [place.name for place in group.places]) for group in groups] == [
        (2, ["Татнефть"]),
        (1, ["Газпром", "Лукойл"]),
    ]
    assert groups[0].user.username == "anvar"


def test_an_excluded_authors_places_stay_out_of_the_grouping() -> None:
    places = InMemoryPlaceRepository()
    add_place(places, user_id=1, name="Газпром")
    add_place(places, user_id=99, name="Лукойл")

    groups = AdminPlacesByCategoryUseCase(places, InMemoryUserRepository()).execute(
        PlaceCategory.FUEL, exclude_author_ids=(99,)
    )

    assert [group.author_id for group in groups] == [1]


def test_an_author_tracking_never_saw_is_grouped_by_id() -> None:
    places = InMemoryPlaceRepository()
    add_place(places, user_id=7, name="Газпром")

    groups = AdminPlacesByCategoryUseCase(places, InMemoryUserRepository()).execute(
        PlaceCategory.FUEL
    )

    assert groups[0].user is None
    assert groups[0].author_id == 7
