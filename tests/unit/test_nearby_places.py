from app.application.use_cases.nearby_places import NearbyPlacesUseCase
from app.domain.entities.place import Place
from app.domain.value_objects.category import PlaceCategory
from app.domain.value_objects.coordinates import Coordinates


class RecordingPlacesProvider:
    def __init__(self, places: list[Place]) -> None:
        self.places = places
        self.calls: list[tuple[Coordinates, PlaceCategory, int, int]] = []

    async def search_nearby(
        self,
        coordinates: Coordinates,
        category: PlaceCategory,
        radius_meters: int = 3000,
        limit: int = 10,
    ) -> list[Place]:
        self.calls.append((coordinates, category, radius_meters, limit))
        return self.places


def _place(name: str = "Cafe Driver") -> Place:
    return Place(
        id="osm:node:1",
        name=name,
        category=PlaceCategory.RESTAURANT,
        coordinates=Coordinates(latitude=55.75, longitude=37.61),
        address="Moscow",
        phone=None,
        distance_meters=120.0,
        source="osm",
        source_id="node:1",
    )


async def test_nearby_places_delegates_to_provider() -> None:
    provider = RecordingPlacesProvider([_place()])
    use_case = NearbyPlacesUseCase(provider)
    coordinates = Coordinates(latitude=55.7512, longitude=37.6184)

    places = await use_case.execute(
        coordinates=coordinates,
        category=PlaceCategory.RESTAURANT,
        radius_meters=1500,
        limit=5,
    )

    assert places[0].name == "Cafe Driver"
    assert provider.calls == [(coordinates, PlaceCategory.RESTAURANT, 1500, 5)]
