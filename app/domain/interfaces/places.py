from typing import Protocol

from app.domain.entities.place import Place
from app.domain.value_objects.category import PlaceCategory
from app.domain.value_objects.coordinates import Coordinates

DEFAULT_DUPLICATE_RADIUS_METERS = 200


class PlaceRepository(Protocol):
    def add(self, place: Place) -> Place:
        """Persist a place and return it with its database id and created_at."""

    def get(self, place_id: int) -> Place | None:
        """Return one place. Readable by anyone — no author filter."""

    def search(
        self,
        name: str | None = None,
        category: PlaceCategory | None = None,
        limit: int = 10,
    ) -> list[Place]:
        """Return places matching a name fragment and/or a category.

        Both filters are optional. ``name`` matches as a normalized substring.
        """

    def nearby(
        self,
        coordinates: Coordinates,
        radius_meters: int,
        category: PlaceCategory | None = None,
        limit: int = 10,
    ) -> list[Place]:
        """Return places within the radius, nearest first."""

    def list_by_author(self, user_id: int) -> list[Place]:
        """Return every place this user contributed, newest first."""

    def find_duplicates(
        self,
        name: str,
        coordinates: Coordinates,
        radius_meters: int = DEFAULT_DUPLICATE_RADIUS_METERS,
    ) -> list[Place]:
        """Return existing places with an overlapping name inside the radius."""

    def update(
        self,
        place_id: int,
        user_id: int,
        name: str | None = None,
        category: PlaceCategory | None = None,
        note: str | None = None,
        coordinates: Coordinates | None = None,
    ) -> Place | None:
        """Change a place the user contributed.

        ``None`` means "leave this field alone"; an empty string clears the note.
        Returns None when the place does not exist or belongs to someone else.
        """

    def delete(self, place_id: int, user_id: int) -> bool:
        """Delete a place the user contributed. False when not theirs."""

    def delete_any(self, place_id: int) -> bool:
        """Delete a place whoever added it. Moderation only — never a driver path."""

    def count(self) -> int:
        """Return how many places the database holds."""

    def count_added_since(self, days: int) -> int:
        """Return how many places were added within the last ``days`` days."""

    def count_by_category(
        self, exclude_author_ids: tuple[int, ...] = ()
    ) -> dict[PlaceCategory, int]:
        """Return the place count per category. Unused categories are absent.

        ``exclude_author_ids`` leaves those authors' places out of the count —
        the ordinary admin rung is not shown the super admins' contributions.
        """

    def top_authors(self, limit: int = 10) -> list[tuple[int, int]]:
        """Return (user id, places added) pairs, biggest contributor first."""

    def count_by_author(self) -> dict[int, int]:
        """Return how many places every author added. Non-authors are absent.

        Ranking the whole user list needs each user's total, which the top
        slice ``top_authors`` returns cannot give.
        """
