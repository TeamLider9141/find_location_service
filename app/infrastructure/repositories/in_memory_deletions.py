from datetime import datetime, timezone

from app.domain.entities.deletion_record import DeletionRecord
from app.domain.entities.place import Place


class InMemoryDeletionLog:
    def __init__(self) -> None:
        self._records: list[DeletionRecord] = []

    def record(self, place: Place, deleted_by: int, source: str) -> None:
        self._records.append(
            DeletionRecord(
                id=len(self._records) + 1,
                place_name=place.name,
                category=place.category,
                latitude=place.coordinates.latitude,
                longitude=place.coordinates.longitude,
                note=place.note,
                added_by_user_id=place.added_by_user_id,
                deleted_by_user_id=deleted_by,
                source=source,
                deleted_at=datetime.now(timezone.utc).replace(microsecond=0, tzinfo=None),
            )
        )

    def list_recent(self, limit: int = 30) -> list[DeletionRecord]:
        return list(reversed(self._records))[: max(limit, 0)]
