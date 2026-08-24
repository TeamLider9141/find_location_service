from typing import Protocol

from app.domain.entities.deletion_record import DeletionRecord
from app.domain.entities.place import Place


class DeletionLog(Protocol):
    """Every place that was ever deleted, and by whom. Append-only."""

    def record(self, place: Place, deleted_by: int, source: str) -> None:
        """Write one tombstone. Nothing in the bot ever removes them."""

    def list_recent(self, limit: int = 30) -> list[DeletionRecord]:
        """Return the newest tombstones first."""
