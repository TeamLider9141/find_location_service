from datetime import datetime, timezone

from app.domain.entities.community_place import Place
from app.domain.interfaces.community_places import (
    DEFAULT_DUPLICATE_RADIUS_METERS,
    PlaceRepository,
)
from app.domain.value_objects.category import PlaceCategory
from app.domain.value_objects.coordinates import Coordinates


class AddPlaceUseCase:
    def __init__(self, repository: PlaceRepository) -> None:
        self._repository = repository

    def execute(
        self,
        user_id: int,
        name: str,
        category: PlaceCategory,
        coordinates: Coordinates,
        note: str = "",
    ) -> Place:
        cleaned_name = name.strip()
        if not cleaned_name:
            raise ValueError("name must not be blank")

        return self._repository.add(
            Place(
                id=0,
                added_by_user_id=user_id,
                name=cleaned_name,
                category=category,
                coordinates=coordinates,
                note=note.strip(),
                created_at=datetime.now(timezone.utc),
            )
        )

    def find_duplicates(
        self,
        name: str,
        coordinates: Coordinates,
        radius_meters: int = DEFAULT_DUPLICATE_RADIUS_METERS,
    ) -> list[Place]:
        return self._repository.find_duplicates(
            name=name.strip(),
            coordinates=coordinates,
            radius_meters=radius_meters,
        )


class FindPlacesUseCase:
    def __init__(self, repository: PlaceRepository) -> None:
        self._repository = repository

    def execute(
        self,
        name: str | None = None,
        category: PlaceCategory | None = None,
        limit: int = 10,
    ) -> list[Place]:
        return self._repository.search(name=name, category=category, limit=limit)


class NearbyPlacesUseCase:
    def __init__(self, repository: PlaceRepository) -> None:
        self._repository = repository

    def execute(
        self,
        coordinates: Coordinates,
        radius_meters: int,
        category: PlaceCategory | None = None,
        limit: int = 10,
    ) -> list[Place]:
        return self._repository.nearby(
            coordinates=coordinates,
            radius_meters=radius_meters,
            category=category,
            limit=limit,
        )
