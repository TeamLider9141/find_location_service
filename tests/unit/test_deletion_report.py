from datetime import datetime

from app.application.use_cases.admin import DeletionRow
from app.domain.entities.bot_user import BotUser
from app.domain.entities.deletion_record import DeletionRecord
from app.domain.value_objects.category import PlaceCategory
from app.presentation.telegram.deletion_report import render_deletion_report

STAMP = datetime(2026, 8, 23, 14, 5)


def make_row(
    name: str = "Газпром",
    deleted_by: BotUser | None = None,
    source: str = "owner",
) -> DeletionRow:
    return DeletionRow(
        record=DeletionRecord(
            id=1,
            place_name=name,
            category=PlaceCategory.FUEL,
            latitude=55.75,
            longitude=37.61,
            note="",
            added_by_user_id=42,
            deleted_by_user_id=7,
            source=source,
            deleted_at=STAMP,
        ),
        deleted_by=deleted_by,
        added_by=None,
    )


def test_the_report_is_a_full_page_with_one_row_per_deletion() -> None:
    page = render_deletion_report([make_row(), make_row("Лукойл")])

    assert page.startswith("<!doctype html>")
    assert page.count("<tr><td>") == 2
    assert "Газпром" in page
    assert "Лукойл" in page
    assert "2 ta yozuv" in page


def test_the_place_links_to_the_map_and_the_time_is_tashkent() -> None:
    page = render_deletion_report([make_row()])

    assert "https://www.google.com/maps/search/?api=1&amp;query=55.75,37.61" in page
    # 14:05 UTC is 19:05 in Tashkent.
    assert "19:05" in page


def test_names_are_escaped_before_the_table() -> None:
    # A stray tag here would corrupt the whole page, not one message.
    page = render_deletion_report([make_row(name="<script>alert(1)</script>")])

    assert "<script>" not in page
    assert "&lt;script&gt;" in page


def test_an_unknown_deleter_is_shown_by_id() -> None:
    page = render_deletion_report([make_row(source="admin")])

    assert "<td>7</td>" in page
    assert "admin panel orqali" in page


def test_an_empty_journal_still_renders() -> None:
    page = render_deletion_report([])

    assert "0 ta yozuv" in page
    assert "<tbody>" in page
