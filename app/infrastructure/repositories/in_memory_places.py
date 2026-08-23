from dataclasses import replace
from datetime import datetime, timezone

from app.application.name_normalization import normalize_name
from app.domain.entities.community_place import Place
from app.domain.interfaces.community_places import DEFAULT_DUPLICATE_RADIUS_METERS
from app.domain.value_objects.category import PlaceCategory
from app.domain.value_objects.coordinates import Coordinates


class InMemoryPlaceRepository:
    """Test double for PlaceRepository. Same contract, no database."""

    def __init__(self) -> None:
        self._places: dict[int, Place] = {}
        self._next_id = 1

    def add(self, place: Place) -> Place:
        # The real repository leaves created_at out of its INSERT, so the column
        # takes CURRENT_TIMESTAMP and whatever the caller passed is discarded.
        # CURRENT_TIMESTAMP is naive UTC with one-second resolution.
        stored = replace(
            place,
            id=self._next_id,
            created_at=datetime.now(timezone.utc).replace(microsecond=0, tzinfo=None),
        )
        self._places[stored.id] = stored
        self._next_id += 1
        return stored

    def get(self, place_id: int) -> Place | None:
        return self._places.get(place_id)

    def search(
        self,
        name: str | None = None,
        category: PlaceCategory | None = None,
        limit: int = 10,
    ) -> list[Place]:
        normalized_name = normalize_name(name) if name is not None else ""
        # Read category.value up front rather than inside the comprehension. The
        # real repository builds its parameters before it queries, so a non-enum
        # category raises there even when nothing would have matched anyway.
        category_value = _category_value(category)
        matches = [
            place
            for place in self._places.values()
            if (not normalized_name or normalized_name in normalize_name(place.name))
            and (category_value is None or place.category.value == category_value)
        ]
        matches.sort(key=lambda place: place.name)
        # SQLite reads a negative LIMIT as "no limit", and a double that quietly
        # truncated instead would hide the difference from the use case tests.
        return matches if limit < 0 else matches[:limit]

    def nearby(
        self,
        coordinates: Coordinates,
        radius_meters: int,
        category: PlaceCategory | None = None,
        limit: int = 10,
    ) -> list[Place]:
        category_value = _category_value(category)
        with_distance = [
            (coordinates.distance_to(place.coordinates), place)
            for place in self._places.values()
            if category_value is None or place.category.value == category_value
        ]
        within = [item for item in with_distance if item[0] <= radius_meters]
        within.sort(key=lambda item: item[0])
        return [place for _, place in within[: max(limit, 0)]]

    def list_by_author(self, user_id: int) -> list[Place]:
        matches = [
            place
            for place in self._places.values()
            if place.added_by_user_id == user_id
        ]
        matches.sort(key=lambda place: place.id, reverse=True)
        return matches

    def find_duplicates(
        self,
        name: str,
        coordinates: Coordinates,
        radius_meters: int = DEFAULT_DUPLICATE_RADIUS_METERS,
    ) -> list[Place]:
        normalized_name = normalize_name(name)
        if not normalized_name:
            return []

        # The stored side needs the same emptiness guard as the incoming one:
        # every string contains the empty string, so one place with a blank name
        # would otherwise be reported as a duplicate of everything near it.
        return [
            place
            for place in self.nearby(coordinates, radius_meters, limit=50)
            if (stored_name := normalize_name(place.name))
            and _names_overlap(normalized_name, stored_name)
        ]

    def update(
        self,
        place_id: int,
        user_id: int,
        name: str | None = None,
        category: PlaceCategory | None = None,
        note: str | None = None,
    ) -> Place | None:
        # The real repository reads category.value while building its UPDATE, so
        # it rejects a non-enum before it ever looks at ownership. Storing the
        # raw value instead would leave a Place whose category is not a
        # PlaceCategory, and every later read of that place would carry it.
        _category_value(category)

        place = self._places.get(place_id)
        if place is None or place.added_by_user_id != user_id:
            return None

        updated = replace(
            place,
            name=place.name if name is None else name,
            category=place.category if category is None else category,
            note=place.note if note is None else note,
        )
        self._places[place_id] = updated
        return updated

    def delete(self, place_id: int, user_id: int) -> bool:
        place = self._places.get(place_id)
        if place is None or place.added_by_user_id != user_id:
            return False

        del self._places[place_id]
        return True


def _category_value(category: PlaceCategory | None) -> str | None:
    return None if category is None else category.value


def _names_overlap(left: str, right: str) -> bool:
    return left in right or right in left
