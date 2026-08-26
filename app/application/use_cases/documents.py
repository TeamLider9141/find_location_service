"""What documents a place asks for, and who may pin them.

Reading is open to everyone, like the places themselves. Writing rides on the
same right as adding places: the admin's nod, checked at the handlers.
"""

from dataclasses import dataclass
from datetime import datetime

from app.domain.entities.place import Place
from app.domain.entities.place_document import PlaceDocument
from app.domain.interfaces.documents import DocumentRepository
from app.domain.interfaces.places import PlaceRepository
from app.domain.value_objects.attachment import AttachmentKind

DOCUMENTS_PAGE_SIZE = 7

# The note describes which papers a place asks for — a listing, not an essay.
NOTE_WORD_LIMIT = 200


def note_within_limit(note: str) -> bool:
    return len(note.split()) <= NOTE_WORD_LIMIT


@dataclass(frozen=True)
class DocumentCard:
    """One document with the place it is pinned to.

    ``place`` is None when the place was deleted after the pin: the note may
    still be worth reading, so the card survives its address.
    """

    document: PlaceDocument
    place: Place | None


@dataclass(frozen=True)
class DocumentsPage:
    total: int
    page: int
    page_size: int
    rows: list[DocumentCard]


class AddDocumentUseCase:
    def __init__(self, documents: DocumentRepository, places: PlaceRepository) -> None:
        self._documents = documents
        self._places = places

    def execute(
        self,
        user_id: int,
        place_id: int,
        note: str,
        file_id: str | None = None,
        file_kind: AttachmentKind | None = None,
    ) -> DocumentCard | None:
        """Pin a document to a place. None when the place is gone.

        Checked at the moment of writing: the place was picked from a list
        that may have aged while the note was being typed.
        """
        place = self._places.get(place_id)
        if place is None:
            return None

        saved = self._documents.add(
            PlaceDocument(
                id=0,
                place_id=place_id,
                added_by_user_id=user_id,
                note=note,
                file_id=file_id,
                file_kind=file_kind,
                created_at=datetime.min,  # the repository stamps the real moment
            )
        )
        return DocumentCard(document=saved, place=place)


class DocumentsForPlacesUseCase:
    """The documents behind one page of search results, in one read."""

    def __init__(self, documents: DocumentRepository) -> None:
        self._documents = documents

    def execute(self, place_ids: tuple[int, ...]) -> dict[int, list[PlaceDocument]]:
        if not place_ids:
            return {}
        return self._documents.list_for_places(place_ids)


class CountDocumentsByPlaceUseCase:
    """How many documents each place carries — what ranks the place picker."""

    def __init__(self, documents: DocumentRepository) -> None:
        self._documents = documents

    def execute(self) -> dict[int, int]:
        return self._documents.count_by_place()


class ListDocumentsPageUseCase:
    def __init__(self, documents: DocumentRepository, places: PlaceRepository) -> None:
        self._documents = documents
        self._places = places

    def execute(self, page: int, page_size: int = DOCUMENTS_PAGE_SIZE) -> DocumentsPage:
        safe_page = max(page, 0)
        safe_size = max(page_size, 1)
        total, documents = self._documents.list_page(
            offset=safe_page * safe_size, limit=safe_size
        )

        return DocumentsPage(
            total=total,
            page=safe_page,
            page_size=safe_size,
            rows=[self._card(document) for document in documents],
        )

    def _card(self, document: PlaceDocument) -> DocumentCard:
        return DocumentCard(document=document, place=self._places.get(document.place_id))


class ListMyDocumentsUseCase:
    def __init__(self, documents: DocumentRepository, places: PlaceRepository) -> None:
        self._documents = documents
        self._places = places

    def execute(self, user_id: int) -> list[DocumentCard]:
        return [
            DocumentCard(document=document, place=self._places.get(document.place_id))
            for document in self._documents.list_by_author(user_id)
        ]


class GetDocumentUseCase:
    def __init__(self, documents: DocumentRepository, places: PlaceRepository) -> None:
        self._documents = documents
        self._places = places

    def execute(self, document_id: int) -> DocumentCard | None:
        document = self._documents.get(document_id)
        if document is None:
            return None
        return DocumentCard(document=document, place=self._places.get(document.place_id))


class UpdateDocumentUseCase:
    def __init__(self, documents: DocumentRepository, places: PlaceRepository) -> None:
        self._documents = documents
        self._places = places

    def execute(
        self,
        document_id: int,
        user_id: int,
        note: str | None = None,
        file_id: str | None = None,
        file_kind: AttachmentKind | None = None,
    ) -> DocumentCard | None:
        """Change a document the user contributed; None refuses a stranger."""
        updated = self._documents.update(
            document_id, user_id, note=note, file_id=file_id, file_kind=file_kind
        )
        if updated is None:
            return None
        return DocumentCard(document=updated, place=self._places.get(updated.place_id))
