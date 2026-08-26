from dataclasses import replace
from datetime import datetime, timezone

from app.domain.entities.place_document import PlaceDocument
from app.domain.value_objects.attachment import AttachmentKind


class InMemoryDocumentRepository:
    def __init__(self) -> None:
        self._documents: dict[int, PlaceDocument] = {}
        self._next_id = 1

    def add(self, document: PlaceDocument) -> PlaceDocument:
        stored = replace(
            document,
            id=self._next_id,
            created_at=datetime.now(timezone.utc).replace(microsecond=0, tzinfo=None),
        )
        self._documents[stored.id] = stored
        self._next_id += 1
        return stored

    def get(self, document_id: int) -> PlaceDocument | None:
        return self._documents.get(document_id)

    def list_page(self, offset: int, limit: int) -> tuple[int, list[PlaceDocument]]:
        ordered = self._newest_first(self._documents.values())
        start = max(offset, 0)
        return len(ordered), ordered[start : start + max(limit, 0)]

    def list_by_author(self, user_id: int) -> list[PlaceDocument]:
        return self._newest_first(
            document
            for document in self._documents.values()
            if document.added_by_user_id == user_id
        )

    def count_by_place(self) -> dict[int, int]:
        counts: dict[int, int] = {}
        for document in self._documents.values():
            counts[document.place_id] = counts.get(document.place_id, 0) + 1
        return counts

    def list_for_places(self, place_ids: tuple[int, ...]) -> dict[int, list[PlaceDocument]]:
        wanted = set(place_ids)
        grouped: dict[int, list[PlaceDocument]] = {}
        for document in self._newest_first(self._documents.values()):
            if document.place_id in wanted:
                grouped.setdefault(document.place_id, []).append(document)
        return grouped

    def update(
        self,
        document_id: int,
        user_id: int,
        note: str | None = None,
        file_id: str | None = None,
        file_kind: AttachmentKind | None = None,
    ) -> PlaceDocument | None:
        existing = self._documents.get(document_id)
        if existing is None or existing.added_by_user_id != user_id:
            return None

        changes: dict = {}
        if note is not None:
            changes["note"] = note
        # Replaced as a pair: a file id without its kind could not be sent back.
        if file_id is not None and file_kind is not None:
            changes["file_id"] = file_id
            changes["file_kind"] = file_kind

        updated = replace(existing, **changes)
        self._documents[document_id] = updated
        return updated

    def delete(self, document_id: int, user_id: int) -> bool:
        existing = self._documents.get(document_id)
        if existing is None or existing.added_by_user_id != user_id:
            return False

        del self._documents[document_id]
        return True

    @staticmethod
    def _newest_first(documents) -> list[PlaceDocument]:
        # Ties break on the id, the same ORDER BY the SQL uses.
        return sorted(documents, key=lambda item: (item.created_at, item.id), reverse=True)
