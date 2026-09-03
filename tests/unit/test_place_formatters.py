from datetime import datetime

from app.domain.entities.place import Place
from app.domain.value_objects.category import PlaceCategory
from app.domain.value_objects.coordinates import Coordinates
from app.presentation.telegram.formatters import (
    format_place_card,
    format_place_results,
)


def make_place(
    place_id: int = 1,
    name: str = "Газпром",
    categories: tuple[PlaceCategory, ...] = (PlaceCategory.FUEL,),
    note: str = "",
) -> Place:
    return Place(
        id=place_id,
        added_by_user_id=42,
        name=name,
        categories=categories,
        coordinates=Coordinates(latitude=55.75, longitude=37.61),
        note=note,
        created_at=datetime(2026, 1, 1),
    )


def test_place_card_shows_name_category_and_map_link() -> None:
    text = format_place_card(make_place())

    assert "Газпром" in text
    assert "⛽" in text
    assert "55.75,37.61" in text


def test_place_card_includes_a_note_when_present() -> None:
    text = format_place_card(make_place(note="M5, 120 км"))

    assert "M5, 120 км" in text


def test_place_card_omits_the_note_line_when_empty() -> None:
    text = format_place_card(make_place(note=""))

    assert "Izoh" not in text
    assert "📝" not in text


def test_place_card_links_to_the_place_not_the_null_island() -> None:
    # The map link is the whole point of the card: a driver taps it and drives
    # there. Coordinates baked into the query string rather than read off the
    # place would send everyone to the same wrong spot.
    text = format_place_card(
        make_place(name="Лукойл"),
    )

    assert "query=55.75,37.61" in text


def test_every_result_name_is_its_own_map_link() -> None:
    # The name is the link: tapping the line the driver is already reading
    # beats hunting a raw URL under it.
    text = format_place_results(
        [
            make_place(place_id=1, name="Газпром"),
            make_place(place_id=2, name="Кафе"),
        ]
    )

    assert text.count('<a href="https://www.google.com/maps/search/?api=1&query=') == 2
    assert ">Газпром</a>" in text
    assert ">Кафе</a>" in text


def test_a_name_with_html_in_it_cannot_break_the_message() -> None:
    # Names are driver input; an unescaped < or & would make Telegram refuse
    # the whole message, taking every other result down with it.
    text = format_place_results([make_place(name="<Кафе & Бар>")])

    assert "&lt;Кафе &amp; Бар&gt;" in text
    assert "<Кафе" not in text


def test_results_are_numbered_and_show_categories() -> None:
    text = format_place_results(
        [
            make_place(place_id=1, name="Газпром", categories=(PlaceCategory.FUEL,)),
            make_place(place_id=2, name="Кафе", categories=(PlaceCategory.CAFE,)),
        ]
    )

    assert "1. " in text
    assert "2. " in text
    assert "☕" in text


def test_results_show_distance_when_given() -> None:
    text = format_place_results([make_place()], distances_meters=[1234.0])

    assert "1.2 km" in text


def test_results_show_short_distances_in_meters() -> None:
    # Under a kilometre "0.1 km" tells a driver nothing useful.
    text = format_place_results([make_place()], distances_meters=[140.0])

    assert "140 m" in text
    assert "km" not in text


def test_results_pair_each_distance_with_its_own_place() -> None:
    # The numbering and the distance list are two parallel sequences; an
    # off-by-one here sends a driver to the second-nearest place.
    text = format_place_results(
        [
            make_place(place_id=1, name="Ближний"),
            make_place(place_id=2, name="Дальний"),
        ],
        distances_meters=[140.0, 4200.0],
    )

    near, far = text.index("Ближний"), text.index("Дальний")
    assert near < text.index("140 m") < far
    assert far < text.index("4.2 km")


def test_results_without_distances_stay_a_plain_list() -> None:
    import re

    text = format_place_results([make_place()])

    # No distance line at all — "140 m" or "1.2 km" would be an invention.
    assert re.search(r"\d+(\.\d+)? (m|km)\b", text) is None


def test_results_include_notes() -> None:
    text = format_place_results([make_place(note="M5, 120 км")])

    assert "M5, 120 км" in text


def test_empty_results_explain_the_database_is_the_only_source() -> None:
    text = format_place_results([])

    assert "topilmadi" in text.lower()
    # The invitation is the point: nothing else fills the database.
    assert "qo'shish" in text.lower()


def test_every_result_offers_both_navigator_routes() -> None:
    # Our number is an estimate; the links are the navigators' own routes.
    # Plain URLs — they cost nothing and have no relation to any API quota.
    text = format_place_results([make_place()])

    assert 'href="https://yandex.com/maps/?rtext=~55.75,37.61&rtt=auto"' in text
    assert (
        'href="https://www.google.com/maps/dir/?api=1'
        '&destination=55.75,37.61&travelmode=driving"'
    ) in text
    assert "Marshrut:" in text


def make_document(place_id=1, note="Tex passport kerak", file_kind=None):
    from datetime import datetime

    from app.domain.entities.place_document import PlaceDocument

    return PlaceDocument(
        id=1,
        place_id=place_id,
        added_by_user_id=42,
        note=note,
        file_id="F1" if file_kind else None,
        file_kind=file_kind,
        created_at=datetime(2026, 1, 2),
    )


def test_results_show_the_documents_pinned_to_a_place() -> None:
    from app.domain.value_objects.attachment import AttachmentKind

    place = make_place()
    document = make_document(place_id=place.id, file_kind=AttachmentKind.PHOTO)

    text = format_place_results([place], documents_by_place={place.id: [document]})

    assert "📎 Rasm biriktirilgan" in text
    assert "📁 Tex passport kerak" in text


def test_a_place_without_documents_gets_no_document_lines() -> None:
    text = format_place_results([make_place()], documents_by_place={})

    assert "📁" not in text
    assert "📎" not in text


def test_the_place_note_wears_the_speech_mark_in_results() -> None:
    text = format_place_results([make_place(note="M5, 120 км")])

    assert "💬 M5, 120 км" in text


def test_a_note_only_document_shows_no_attachment_line() -> None:
    place = make_place()
    document = make_document(place_id=place.id)

    text = format_place_results([place], documents_by_place={place.id: [document]})

    assert "📁 Tex passport kerak" in text
    assert "📎" not in text


def test_result_attachment_labels_match_the_document_card() -> None:
    # Two copies by necessity — importing would close an import cycle — so a
    # test keeps them in step instead.
    from app.presentation.telegram.document_formatters import ATTACHMENT_LABELS
    from app.presentation.telegram.formatters import RESULT_ATTACHMENT_LABELS

    assert RESULT_ATTACHMENT_LABELS == ATTACHMENT_LABELS


def test_the_list_can_start_numbering_past_one() -> None:
    # Page two carries on from where page one stopped; restarting at 1 would
    # make two different places both "1." in the same conversation.
    text = format_place_results([make_place(name="Ветерок")], start_number=11)

    assert "11. " in text
