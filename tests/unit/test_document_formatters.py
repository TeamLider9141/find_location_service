from datetime import datetime

from app.application.use_cases.documents import DocumentCard, DocumentsPage
from app.domain.entities.place import Place
from app.domain.entities.place_document import PlaceDocument
from app.domain.value_objects.attachment import AttachmentKind
from app.domain.value_objects.category import PlaceCategory
from app.domain.value_objects.coordinates import Coordinates
from app.presentation.telegram.document_formatters import (
    CAPTION_LIMIT,
    NOTE_PREFIX,
    PLACE_GONE_LABEL,
    format_document_caption,
    format_documents_page,
)


def make_place(name: str = "Газпром") -> Place:
    return Place(
        id=1,
        added_by_user_id=42,
        name=name,
        categories=(PlaceCategory.FUEL,),
        coordinates=Coordinates(latitude=55.75, longitude=37.61),
        note="",
        created_at=datetime(2026, 1, 1),
    )


def make_card(
    note: str = "CMR kerak",
    place: Place | None = None,
    file_kind: AttachmentKind | None = None,
    document_id: int = 5,
) -> DocumentCard:
    return DocumentCard(
        document=PlaceDocument(
            id=document_id,
            place_id=1,
            added_by_user_id=42,
            note=note,
            file_id="FILE" if file_kind else None,
            file_kind=file_kind,
            created_at=datetime(2026, 1, 2),
        ),
        place=place,
    )


def page_of(*cards: DocumentCard, total: int | None = None, page: int = 0) -> DocumentsPage:
    return DocumentsPage(
        total=total if total is not None else len(cards),
        page=page,
        page_size=7,
        rows=list(cards),
    )


def test_the_list_numbers_documents_and_links_their_places() -> None:
    text = format_documents_page(page_of(make_card(place=make_place())))

    assert "1)" in text
    assert "Газпром" in text
    assert "maps" in text


def test_numbering_continues_across_pages() -> None:
    text = format_documents_page(
        page_of(make_card(place=make_place()), total=9, page=1)
    )

    assert "8)" in text
    assert "Sahifa 2/2" in text


def test_a_long_note_is_shortened_in_the_list() -> None:
    text = format_documents_page(
        page_of(make_card(note="juda uzun izoh " * 50, place=make_place()))
    )

    assert "…" in text


def test_a_place_name_is_escaped_in_the_list() -> None:
    # Sent as HTML: one "<" in a name would sink the whole message.
    text = format_documents_page(
        page_of(make_card(place=make_place(name="<Газпром>")))
    )

    assert "<Газпром>" not in text
    assert "&lt;Газпром&gt;" in text


def test_an_empty_list_says_so() -> None:
    assert "qo'shilmagan" in format_documents_page(page_of())


def test_the_caption_links_the_place_name_instead_of_a_naked_url() -> None:
    caption = format_document_caption(make_card(place=make_place()))

    assert '<a href="' in caption
    assert "Газпром" in caption
    # The URL lives only inside the anchor — never as a bare line.
    assert "\nhttps://" not in caption
    assert f"{NOTE_PREFIX} CMR kerak" in caption


def test_the_caption_escapes_the_drivers_input() -> None:
    caption = format_document_caption(
        make_card(note="<b>izoh</b>", place=make_place(name="<Газпром>"))
    )

    assert "<Газпром>" not in caption
    assert "<b>izoh</b>" not in caption


def test_the_caption_marks_an_attachment_and_only_then() -> None:
    with_file = format_document_caption(
        make_card(place=make_place(), file_kind=AttachmentKind.PHOTO)
    )
    without = format_document_caption(make_card(place=make_place()))

    assert "📎" in with_file
    # A missing attachment says nothing — the absent file speaks for itself.
    assert "📎" not in without
    assert "Biriktirilmagan" not in without


def test_the_caption_survives_a_deleted_place() -> None:
    caption = format_document_caption(make_card(place=None))

    assert PLACE_GONE_LABEL in caption


def test_the_caption_fits_telegrams_limit() -> None:
    caption = format_document_caption(
        make_card(note="so'z " * 300, place=make_place())
    )

    assert len(caption) <= CAPTION_LIMIT
    assert caption.endswith("…")
