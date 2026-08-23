from typing import Protocol

from app.domain.entities.place import Place
from app.domain.value_objects.category import PlaceCategory
from app.domain.value_objects.coordinates import Coordinates


class PlacesProvider(Protocol):
    async def search_nearby(
        self,
        coordinates: Coordinates,
        category: PlaceCategory,
        radius_meters: int = 3000,
        limit: int = 10,
    ) -> list[Place]:
        """Search nearby places and return normalized POI results."""
