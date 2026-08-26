from typing import Protocol

from app.domain.entities.place_document import PlaceDocument
from app.domain.value_objects.attachment import AttachmentKind


class DocumentRepository(Protocol):
    """Documents pinned to places, shared with every driver."""

    def add(self, document: PlaceDocument) -> PlaceDocument:
        """Persist a document and return it with its database id and created_at."""

    def get(self, document_id: int) -> PlaceDocument | None:
        """Return one document. Readable by anyone — no author filter."""

    def list_page(self, offset: int, limit: int) -> tuple[int, list[PlaceDocument]]:
        """Return the total count and one page, newest first."""

    def list_by_author(self, user_id: int) -> list[PlaceDocument]:
        """Return every document this user contributed, newest first."""

    def count_by_place(self) -> dict[int, int]:
        """Return how many documents each place carries. Bare places are absent.

        Read whole so the place picker can rank hundreds of places without a
        count query each.
        """

    def list_for_places(self, place_ids: tuple[int, ...]) -> dict[int, list[PlaceDocument]]:
        """Return the documents of each listed place, newest first per place.

        One read for a whole results page; places without documents are simply
        absent from the answer.
        """

    def update(
        self,
        document_id: int,
        user_id: int,
        note: str | None = None,
        file_id: str | None = None,
        file_kind: AttachmentKind | None = None,
    ) -> PlaceDocument | None:
        """Change a document the user contributed.

        ``None`` means "leave this field alone"; the attachment is replaced as
        a pair — a file id without its kind could not be sent back. Returns
        None when the document does not exist or belongs to someone else.
        """
