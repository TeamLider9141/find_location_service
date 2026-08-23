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
                # Both repositories stamp their own CURRENT_TIMESTAMP and discard
                # whatever we pass here, so this value is never read back. It is
                # naive UTC — not timezone-aware — because that is what every
                # caller actually receives; the field has no default, so a value
                # still has to be supplied.
                created_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )
        )

    def find_duplicates(
        self,
        name: str,
        coordinates: Coordinates,
        radius_meters: int = DEFAULT_DUPLICATE_RADIUS_METERS,
    ) -> list[Place]:
        # The strip here changes nothing on its own — normalize_name strips and
        # collapses whitespace before the repository compares anything. It stays
        # so that every name entering a use case is cleaned the same way.
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


class ListMyPlacesUseCase:
    def __init__(self, repository: PlaceRepository) -> None:
        self._repository = repository

    def execute(self, user_id: int) -> list[Place]:
        return self._repository.list_by_author(user_id)


class GetPlaceUseCase:
    def __init__(self, repository: PlaceRepository) -> None:
        self._repository = repository

    def execute(self, place_id: int) -> Place | None:
        return self._repository.get(place_id)


class UpdatePlaceUseCase:
    def __init__(self, repository: PlaceRepository) -> None:
        self._repository = repository

    def execute(
        self,
        place_id: int,
        user_id: int,
        name: str | None = None,
        category: PlaceCategory | None = None,
        note: str | None = None,
    ) -> Place | None:
        cleaned_name = name
        if name is not None:
            # Same rule as adding one: a place has to keep a name other drivers
            # can search for. Without this a rename could blank the name, and a
            # blank name is the one case find_duplicates has to defend against.
            cleaned_name = name.strip()
            if not cleaned_name:
                raise ValueError("name must not be blank")

        return self._repository.update(
            place_id=place_id,
            user_id=user_id,
            name=cleaned_name,
            category=category,
            # A blank note is not the same as no note: "" clears the text, None
            # leaves whatever is stored alone.
            note=note.strip() if note is not None else None,
        )


class DeletePlaceUseCase:
    def __init__(self, repository: PlaceRepository) -> None:
        self._repository = repository

    def execute(self, place_id: int, user_id: int) -> bool:
        return self._repository.delete(place_id, user_id)
