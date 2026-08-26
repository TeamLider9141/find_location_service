from app.application.use_cases.documents import (
    AddDocumentUseCase,
    GetDocumentUseCase,
    ListDocumentsPageUseCase,
    ListMyDocumentsUseCase,
    NOTE_WORD_LIMIT,
    UpdateDocumentUseCase,
    note_within_limit,
)
from app.application.use_cases.places import AddPlaceUseCase
from app.domain.value_objects.attachment import AttachmentKind
from app.domain.value_objects.category import PlaceCategory
from app.domain.value_objects.coordinates import Coordinates
from app.infrastructure.repositories.in_memory_documents import InMemoryDocumentRepository
from app.infrastructure.repositories.in_memory_places import InMemoryPlaceRepository


def seeded():
    places = InMemoryPlaceRepository()
    place = AddPlaceUseCase(places).execute(
        user_id=42,
        name="Газпром",
        categories=(PlaceCategory.FUEL,),
        coordinates=Coordinates(latitude=55.75, longitude=37.61),
    )
    return InMemoryDocumentRepository(), places, place


def test_a_document_is_pinned_to_its_place() -> None:
    documents, places, place = seeded()

    card = AddDocumentUseCase(documents, places).execute(
        user_id=42, place_id=place.id, note="CMR va invoys kerak"
    )

    assert card is not None
    assert card.place == place
    assert card.document.note == "CMR va invoys kerak"
    assert not card.document.has_attachment


def test_a_document_may_carry_an_attachment() -> None:
    documents, places, place = seeded()

    card = AddDocumentUseCase(documents, places).execute(
        user_id=42,
        place_id=place.id,
        note="Namuna rasmda",
        file_id="FILE123",
        file_kind=AttachmentKind.PHOTO,
    )

    assert card.document.file_id == "FILE123"
    assert card.document.file_kind == AttachmentKind.PHOTO


def test_pinning_to_a_missing_place_is_refused() -> None:
    documents, places, _ = seeded()

    assert (
        AddDocumentUseCase(documents, places).execute(
            user_id=42, place_id=999, note="x"
        )
        is None
    )


def test_the_page_carries_each_documents_place() -> None:
    documents, places, place = seeded()
    add = AddDocumentUseCase(documents, places)
    add.execute(user_id=42, place_id=place.id, note="birinchi")
    add.execute(user_id=7, place_id=place.id, note="ikkinchi")

    page = ListDocumentsPageUseCase(documents, places).execute(page=0)

    assert page.total == 2
    # Newest first, as everywhere else in the bot.
    assert [row.document.note for row in page.rows] == ["ikkinchi", "birinchi"]
    assert all(row.place == place for row in page.rows)


def test_seven_documents_fill_one_page() -> None:
    documents, places, place = seeded()
    add = AddDocumentUseCase(documents, places)
    for index in range(9):
        add.execute(user_id=42, place_id=place.id, note=f"hujjat {index}")

    first = ListDocumentsPageUseCase(documents, places).execute(page=0)
    second = ListDocumentsPageUseCase(documents, places).execute(page=1)

    assert first.page_size == 7
    assert len(first.rows) == 7
    assert len(second.rows) == 2


def test_a_deleted_place_does_not_sink_the_card() -> None:
    documents, places, place = seeded()
    AddDocumentUseCase(documents, places).execute(
        user_id=42, place_id=place.id, note="hali ham o'qiladi"
    )
    places.delete(place.id, user_id=42)

    page = ListDocumentsPageUseCase(documents, places).execute(page=0)

    assert page.rows[0].place is None
    assert page.rows[0].document.note == "hali ham o'qiladi"


def test_my_documents_lists_only_mine() -> None:
    documents, places, place = seeded()
    add = AddDocumentUseCase(documents, places)
    add.execute(user_id=42, place_id=place.id, note="meniki")
    add.execute(user_id=7, place_id=place.id, note="boshqaniki")

    cards = ListMyDocumentsUseCase(documents, places).execute(42)

    assert [card.document.note for card in cards] == ["meniki"]


def test_one_document_opens_with_its_place() -> None:
    documents, places, place = seeded()
    saved = AddDocumentUseCase(documents, places).execute(
        user_id=42, place_id=place.id, note="bitta"
    )

    card = GetDocumentUseCase(documents, places).execute(saved.document.id)

    assert card is not None
    assert card.place == place


def test_a_missing_document_opens_as_none() -> None:
    documents, places, _ = seeded()

    assert GetDocumentUseCase(documents, places).execute(999) is None


def test_the_author_updates_their_note() -> None:
    documents, places, place = seeded()
    saved = AddDocumentUseCase(documents, places).execute(
        user_id=42, place_id=place.id, note="eski"
    )

    card = UpdateDocumentUseCase(documents, places).execute(
        document_id=saved.document.id, user_id=42, note="yangi"
    )

    assert card is not None
    assert card.document.note == "yangi"


def test_a_stranger_is_refused_the_update() -> None:
    documents, places, place = seeded()
    saved = AddDocumentUseCase(documents, places).execute(
        user_id=42, place_id=place.id, note="meniki"
    )

    assert (
        UpdateDocumentUseCase(documents, places).execute(
            document_id=saved.document.id, user_id=7, note="hacked"
        )
        is None
    )


def test_the_note_limit_counts_words() -> None:
    assert note_within_limit("uch so'z bor")
    assert note_within_limit("so'z " * NOTE_WORD_LIMIT)
    assert not note_within_limit("so'z " * (NOTE_WORD_LIMIT + 1))
