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
    category: PlaceCategory = PlaceCategory.FUEL,
    note: str = "",
) -> Place:
    return Place(
        id=place_id,
        added_by_user_id=42,
        name=name,
        category=category,
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


def test_every_result_carries_its_own_map_link() -> None:
    # The numbered buttons open a card, but the link in the text is one tap
    # fewer — a driver mid-route does not want a detour through a menu.
    text = format_place_results(
        [
            make_place(place_id=1, name="Газпром"),
            make_place(place_id=2, name="Кафе"),
        ]
    )

    assert text.count("https://www.google.com/maps/search/?api=1&query=") == 2


def test_results_are_numbered_and_show_categories() -> None:
    text = format_place_results(
        [
            make_place(place_id=1, name="Газпром", category=PlaceCategory.FUEL),
            make_place(place_id=2, name="Кафе", category=PlaceCategory.CAFE),
        ]
    )

    assert "1. Газпром" in text
    assert "2. Кафе" in text
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
    text = format_place_results([make_place()])

    assert " m" not in text
    assert "km" not in text


def test_results_include_notes() -> None:
    text = format_place_results([make_place(note="M5, 120 км")])

    assert "M5, 120 км" in text


def test_empty_results_explain_the_database_is_the_only_source() -> None:
    text = format_place_results([])

    assert "topilmadi" in text.lower()
    # The invitation is the point: nothing else fills the database.
    assert "qo'shish" in text.lower()
