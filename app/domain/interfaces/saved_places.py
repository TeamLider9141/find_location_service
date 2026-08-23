from typing import Protocol

from app.domain.entities.saved_place import SavedPlace
from app.domain.value_objects.category import PlaceCategory


class SavedPlaceRepository(Protocol):
    def add(self, saved_place: SavedPlace) -> SavedPlace:
        """Persist a saved place and return it with its database id."""

    def get(self, user_id: int, saved_place_id: int) -> SavedPlace | None:
        """Return one saved place for a user."""

    def list_by_user(self, user_id: int) -> list[SavedPlace]:
        """Return saved places for one user."""

    def update_category(
        self,
        user_id: int,
        saved_place_id: int,
        category: PlaceCategory,
    ) -> SavedPlace | None:
        """Change saved place category."""

    def delete(self, user_id: int, saved_place_id: int) -> bool:
        """Delete one saved place for a user."""
