from app.domain.entities.place import Place
from app.domain.interfaces.places import PlacesProvider
from app.domain.value_objects.category import PlaceCategory
from app.domain.value_objects.coordinates import Coordinates


class NearbyPlacesUseCase:
    def __init__(self, places_provider: PlacesProvider) -> None:
        self._places_provider = places_provider

    async def execute(
        self,
        coordinates: Coordinates,
        category: PlaceCategory,
        radius_meters: int = 3000,
        limit: int = 10,
    ) -> list[Place]:
        return await self._places_provider.search_nearby(
            coordinates=coordinates,
            category=category,
            radius_meters=radius_meters,
            limit=limit,
        )
