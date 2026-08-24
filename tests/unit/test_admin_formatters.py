from datetime import datetime

from app.application.use_cases.admin import (
    AdminOverview,
    AuthorPlaces,
    DeletionRow,
    AuthorRanking,
    UserDetail,
    UserRow,
    UsersPage,
)
from app.domain.entities.bot_user import BotUser
from app.domain.entities.deletion_record import DeletionRecord
from app.domain.entities.place import Place
from app.domain.value_objects.category import PlaceCategory
from app.domain.value_objects.coordinates import Coordinates
from app.presentation.telegram.admin_formatters import (
    format_admin_overview,
    format_admin_places,
    format_broadcast_preview,
    format_broadcast_result,
    format_deletion_log,
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
        categories=(PlaceCategory.FUEL,),
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


def test_activity_stamps_are_shown_in_tashkent_time() -> None:
    # Stored in UTC; the admin reads the time their own watch shows. The STAMP
    # above is 14:05 UTC, which is 19:05 in Tashkent.
    detail = UserDetail(user=make_user(), places=[], searches=0)

    text = format_user_detail(detail)

    assert "19:05" in text
    assert "14:05" not in text


def test_user_detail_entries_are_separated_by_a_blank_line() -> None:
    # Names arrive with their own newlines inside; without a separator the
    # entries read as one solid block.
    detail = UserDetail(
        user=make_user(),
        places=[make_place(), make_place(2, "Лукойл")],
        searches=0,
    )

    text = format_user_detail(detail)

    assert "\n\n2)" in text
    assert not text.endswith("\n")


def test_a_user_detail_makes_every_place_name_the_map_link() -> None:
    # The admin checks a suspicious entry by opening it on the map; the name
    # itself is the link, not a raw URL under it.
    detail = UserDetail(user=make_user(), places=[make_place()], searches=0)

    text = format_user_detail(detail)

    assert '<a href="https://www.google.com/maps/search/?api=1&query=55.75,37.61">' in text
    assert ">Газпром</a>" in text


def test_a_user_detail_with_html_in_the_name_cannot_break() -> None:
    # Names are user input; one "<" would make Telegram refuse the message.
    detail = UserDetail(
        user=make_user(full_name="<Ali>"),
        places=[make_place(name="<Кафе & Бар>")],
        searches=0,
    )

    text = format_user_detail(detail)

    assert "&lt;Ali&gt;" in text
    assert "&lt;Кафе &amp; Бар&gt;" in text


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


def test_admin_places_number_the_authors_with_their_links() -> None:
    groups = [
        AuthorPlaces(author_id=7, user=make_user(), places=[make_place()]),
        AuthorPlaces(author_id=9, user=None, places=[make_place(2, "Лукойл")]),
    ]

    text = format_admin_places(PlaceCategory.FUEL, groups)

    assert "2 ta" in text
    assert "1) Ali (@ali)" in text
    # The name itself carries the link, not a raw URL under it.
    assert '<a href="https://www.google.com/maps/search/?api=1&query=55.75,37.61">' in text
    assert ">Газпром</a>" in text
    # An author tracking never saw is labelled by id, not dropped.
    assert "2) 9" in text


def test_an_empty_category_says_so() -> None:
    assert "yo'q" in format_admin_places(PlaceCategory.HOTEL, []).lower()


def test_a_huge_category_is_cut_with_a_tail_note() -> None:
    # Telegram cuts messages at 4096 characters; the formatter cuts first and
    # says how much it left out.
    groups = [
        AuthorPlaces(
            author_id=7,
            user=make_user(),
            places=[make_place(place_id, f"Joy {place_id:03d}") for place_id in range(40)],
        )
    ]

    text = format_admin_places(PlaceCategory.FUEL, groups)

    assert text.count("📍") == 30
    assert "yana 10 ta joy" in text


def test_the_deletion_journal_reads_as_a_numbered_list() -> None:
    record = DeletionRecord(
        id=1,
        place_name="Газпром",
        categories=(PlaceCategory.FUEL,),
        latitude=55.75,
        longitude=37.61,
        note="",
        added_by_user_id=42,
        deleted_by_user_id=7,
        source="owner",
        deleted_at=STAMP,
    )
    rows = [DeletionRow(record=record, deleted_by=make_user(), added_by=None)]

    text = format_deletion_log(rows)

    assert "1)" in text
    assert "egasi o'chirdi" in text
    assert '<a href="https://www.google.com/maps/search/?api=1&query=55.75,37.61">' in text
    assert "Ali (@ali)" in text
    # The author was never tracked, so the id stands in for the name.
    assert "42" in text


def test_an_admin_deletion_is_labelled_as_such() -> None:
    record = DeletionRecord(
        id=1,
        place_name="Газпром",
        categories=(PlaceCategory.FUEL,),
        latitude=55.75,
        longitude=37.61,
        note="",
        added_by_user_id=42,
        deleted_by_user_id=100,
        source="admin",
        deleted_at=STAMP,
    )

    text = format_deletion_log([DeletionRow(record=record, deleted_by=None, added_by=None)])

    assert "admin panel orqali" in text


def test_an_empty_journal_says_so() -> None:
    assert "bo'sh" in format_deletion_log([]).lower()
