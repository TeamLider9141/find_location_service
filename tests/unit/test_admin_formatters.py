from datetime import datetime

from app.application.use_cases.admin import (
    AdminOverview,
    AuthorRanking,
    UserDetail,
    UserRow,
    UsersPage,
)
from app.domain.entities.bot_user import BotUser
from app.domain.entities.place import Place
from app.domain.value_objects.category import PlaceCategory
from app.domain.value_objects.coordinates import Coordinates
from app.presentation.telegram.admin_formatters import (
    format_admin_overview,
    format_broadcast_preview,
    format_broadcast_result,
    format_top_searches,
    format_user_detail,
    format_users_page,
)

STAMP = datetime(2026, 8, 23, 14, 5)


def make_user(user_id: int = 7, full_name: str = "Ali", username: str | None = "ali") -> BotUser:
    return BotUser(
        id=user_id,
        full_name=full_name,
        username=username,
        first_seen_at=STAMP,
        last_seen_at=STAMP,
    )


def make_place(place_id: int = 1, name: str = "Газпром") -> Place:
    return Place(
        id=place_id,
        added_by_user_id=7,
        name=name,
        category=PlaceCategory.FUEL,
        coordinates=Coordinates(latitude=55.75, longitude=37.61),
        note="",
        created_at=STAMP,
    )


def make_overview(**overrides) -> AdminOverview:
    defaults = dict(
        total_places=12,
        places_today=2,
        places_this_week=5,
        total_users=3,
        total_searches=40,
        categories=[(PlaceCategory.FUEL, 8), (PlaceCategory.CAFE, 4)],
        top_authors=[AuthorRanking(user_id=7, full_name="Ali", username="ali", places=8)],
    )
    defaults.update(overrides)
    return AdminOverview(**defaults)


def test_the_overview_shows_the_headline_numbers() -> None:
    text = format_admin_overview(make_overview())

    assert "12" in text
    assert "3" in text
    assert "40" in text


def test_the_overview_lists_categories_with_labels() -> None:
    text = format_admin_overview(make_overview())

    assert "Yoqilg'i" in text or "⛽" in text
    assert "8" in text


def test_the_overview_names_top_authors() -> None:
    text = format_admin_overview(make_overview())

    assert "Ali" in text


def test_an_author_with_no_user_row_is_shown_by_id() -> None:
    overview = make_overview(
        top_authors=[AuthorRanking(user_id=777, full_name=None, username=None, places=3)]
    )

    assert "777" in format_admin_overview(overview)


def test_an_empty_database_reads_as_empty_not_broken() -> None:
    overview = make_overview(
        total_places=0,
        places_today=0,
        places_this_week=0,
        total_users=0,
        total_searches=0,
        categories=[],
        top_authors=[],
    )

    text = format_admin_overview(overview)

    assert "Hali" in text


def test_a_user_page_numbers_rows_from_one() -> None:
    page = UsersPage(
        total=1,
        page=0,
        page_size=5,
        rows=[UserRow(user=make_user(), places=2)],
    )

    text = format_users_page(page)

    assert "1)" in text
    assert "Ali" in text


def test_a_user_page_shows_which_page_it_is() -> None:
    page = UsersPage(total=12, page=1, page_size=5, rows=[UserRow(user=make_user(), places=0)])

    text = format_users_page(page)

    assert "2" in text
    assert "12" in text


def test_an_empty_user_list_says_so() -> None:
    text = format_users_page(UsersPage(total=0, page=0, page_size=5, rows=[]))

    assert "yo'q" in text.lower()


def test_a_user_detail_reports_activity_and_places() -> None:
    detail = UserDetail(user=make_user(), places=[make_place()], searches=9)

    text = format_user_detail(detail)

    assert "@ali" in text
    assert "Газпром" in text
    assert "9" in text


def test_a_user_detail_links_every_place_to_the_map() -> None:
    # The admin checks a suspicious entry by opening it on the map, not by
    # reading raw coordinates.
    detail = UserDetail(user=make_user(), places=[make_place()], searches=0)

    text = format_user_detail(detail)

    assert "https://www.google.com/maps/search/?api=1&query=55.75,37.61" in text


def test_a_user_without_a_username_is_still_readable() -> None:
    detail = UserDetail(user=make_user(username=None), places=[], searches=0)

    text = format_user_detail(detail)

    assert "@" not in text
    assert "7" in text


def test_top_searches_are_numbered_with_their_counts() -> None:
    text = format_top_searches([("газпром", 12), ("кафе", 3)])

    assert "1)" in text
    assert "газпром" in text
    assert "12" in text


def test_no_searches_yet_reads_as_empty() -> None:
    assert "yo'q" in format_top_searches([]).lower()


def test_a_broadcast_preview_shows_the_text_and_the_audience() -> None:
    text = format_broadcast_preview("Salom haydovchilar", recipients=17)

    assert "Salom haydovchilar" in text
    assert "17" in text


def test_a_broadcast_result_reports_both_outcomes() -> None:
    # Blocked bots are the normal case, not an error: the admin needs the split
    # to know the message actually went out.
    text = format_broadcast_result(sent=15, failed=2)

    assert "15" in text
    assert "2" in text
