from dataclasses import dataclass
from datetime import datetime

from app.domain.value_objects.category import PlaceCategory


@dataclass(frozen=True)
class DeletionRecord:
    """One deleted place, kept as it was at the moment it went.

    The row it describes is gone, so this snapshot is the only remaining
    answer to "what was deleted, by whom, and from where".
    """

    id: int
    place_name: str
    categories: tuple[PlaceCategory, ...]
    latitude: float
    longitude: float
    note: str
    added_by_user_id: int
    deleted_by_user_id: int
    # "owner" — the driver removed their own place; "admin" — the panel did.
    source: str
    deleted_at: datetime

    @property
    def category(self) -> PlaceCategory:
        """The first category — for the single-category views."""
        return self.categories[0]
