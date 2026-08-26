from datetime import datetime

import pytest

from app.domain.entities.place_document import PlaceDocument
from app.domain.value_objects.attachment import AttachmentKind
from app.infrastructure.database.sqlite_documents import SQLiteDocumentRepository
from app.infrastructure.repositories.in_memory_documents import InMemoryDocumentRepository

# The document views read these through the protocol, so both implementations
# have to answer identically.


@pytest.fixture(params=["memory", "sqlite"])
def repository(request, tmp_path):
    if request.param == "memory":
        return InMemoryDocumentRepository()
    return SQLiteDocumentRepository(tmp_path / "documents.sqlite3")


def add(
    repository,
    place_id=1,
    user_id=42,
    note="Yuk xati kerak",
    file_id=None,
    file_kind=None,
) -> PlaceDocument:
    return repository.add(
        PlaceDocument(
            id=0,
            place_id=place_id,
            added_by_user_id=user_id,
            note=note,
            file_id=file_id,
            file_kind=file_kind,
            created_at=datetime(2026, 1, 1),
        )
    )


def test_a_saved_document_comes_back_with_an_id(repository) -> None:
    saved = add(repository, note="CMR va invoys")

    assert saved.id > 0
    assert repository.get(saved.id) == saved


def test_a_missing_document_is_none(repository) -> None:
    assert repository.get(999) is None


def test_an_attachment_survives_the_round_trip(repository) -> None:
    saved = add(repository, file_id="ABC123", file_kind=AttachmentKind.PHOTO)

    stored = repository.get(saved.id)
    assert stored is not None
    assert stored.file_id == "ABC123"
    assert stored.file_kind == AttachmentKind.PHOTO
    assert stored.has_attachment


def test_a_note_only_document_has_no_attachment(repository) -> None:
    saved = add(repository)

    stored = repository.get(saved.id)
    assert stored is not None
    assert not stored.has_attachment


def test_the_page_walks_newest_first(repository) -> None:
    first = add(repository, note="birinchi")
    second = add(repository, note="ikkinchi")
    third = add(repository, note="uchinchi")

    total, rows = repository.list_page(offset=0, limit=2)

    assert total == 3
    assert [row.id for row in rows] == [third.id, second.id]

    _, tail = repository.list_page(offset=2, limit=2)
    assert [row.id for row in tail] == [first.id]


def test_an_empty_repository_pages_nothing(repository) -> None:
    assert repository.list_page(offset=0, limit=7) == (0, [])


def test_only_the_authors_documents_are_listed_for_them(repository) -> None:
    mine = add(repository, user_id=1, note="meniki")
    add(repository, user_id=2, note="boshqaniki")
    mine_too = add(repository, user_id=1, note="yana meniki")

    listed = repository.list_by_author(1)

    assert [row.id for row in listed] == [mine_too.id, mine.id]


def test_the_author_may_rewrite_their_note(repository) -> None:
    saved = add(repository, user_id=1)

    updated = repository.update(saved.id, user_id=1, note="yangi izoh")

    assert updated is not None
    assert updated.note == "yangi izoh"
    assert repository.get(saved.id).note == "yangi izoh"


def test_the_author_may_replace_the_attachment(repository) -> None:
    saved = add(repository, user_id=1, file_id="OLD", file_kind=AttachmentKind.PHOTO)

    updated = repository.update(
        saved.id, user_id=1, file_id="NEW", file_kind=AttachmentKind.FILE
    )

    assert updated is not None
    assert updated.file_id == "NEW"
    assert updated.file_kind == AttachmentKind.FILE
    # The note was not touched.
    assert updated.note == saved.note


def test_a_stranger_may_not_edit(repository) -> None:
    saved = add(repository, user_id=1)

    assert repository.update(saved.id, user_id=2, note="hacked") is None
    assert repository.get(saved.id).note == saved.note


def test_updating_a_missing_document_is_none(repository) -> None:
    assert repository.update(999, user_id=1, note="x") is None
