from dataclasses import replace

from app.domain.entities.saved_place import SavedPlace
from app.domain.value_objects.category import PlaceCategory


class InMemorySavedPlaceRepository:
    def __init__(self) -> None:
        self._places: dict[int, SavedPlace] = {}
        self._next_id = 1

    def add(self, saved_place: SavedPlace) -> SavedPlace:
        place = replace(saved_place, id=self._next_id)
        self._places[place.id] = place
        self._next_id += 1
        return place

    def get(self, user_id: int, saved_place_id: int) -> SavedPlace | None:
        place = self._places.get(saved_place_id)
        if place is None or place.user_id != user_id:
            return None
        return place

    def list_by_user(self, user_id: int) -> list[SavedPlace]:
        return [place for place in self._places.values() if place.user_id == user_id]

    def update_category(
        self,
        user_id: int,
        saved_place_id: int,
        category: PlaceCategory,
    ) -> SavedPlace | None:
        place = self.get(user_id, saved_place_id)
        if place is None:
            return None

        updated = replace(place, category=category)
        self._places[saved_place_id] = updated
        return updated

    def delete(self, user_id: int, saved_place_id: int) -> bool:
        place = self.get(user_id, saved_place_id)
        if place is None:
            return False

        del self._places[saved_place_id]
        return True
