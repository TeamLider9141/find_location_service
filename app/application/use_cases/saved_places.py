from app.domain.entities.location import Location
from app.domain.entities.saved_place import SavedPlace
from app.domain.interfaces.saved_places import SavedPlaceRepository
from app.domain.value_objects.category import PlaceCategory


class AddSavedPlaceUseCase:
    def __init__(self, repository: SavedPlaceRepository) -> None:
        self._repository = repository

    def execute(self, user_id: int, location: Location, category: PlaceCategory) -> SavedPlace:
        return self._repository.add(
            SavedPlace(
                id=0,
                user_id=user_id,
                name=location.name,
                category=category,
                coordinates=location.coordinates,
                address=location.address,
                source=location.source,
                source_id=location.source_id,
            )
        )


class ListSavedPlacesUseCase:
    def __init__(self, repository: SavedPlaceRepository) -> None:
        self._repository = repository

    def execute(self, user_id: int) -> list[SavedPlace]:
        return self._repository.list_by_user(user_id)


class UpdateSavedPlaceCategoryUseCase:
    def __init__(self, repository: SavedPlaceRepository) -> None:
        self._repository = repository

    def execute(
        self,
        user_id: int,
        saved_place_id: int,
        category: PlaceCategory,
    ) -> SavedPlace | None:
        return self._repository.update_category(user_id, saved_place_id, category)


class DeleteSavedPlaceUseCase:
    def __init__(self, repository: SavedPlaceRepository) -> None:
        self._repository = repository

    def execute(self, user_id: int, saved_place_id: int) -> bool:
        return self._repository.delete(user_id, saved_place_id)
