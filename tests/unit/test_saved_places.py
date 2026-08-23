from pathlib import Path

from app.application.use_cases.saved_places import (
    AddSavedPlaceUseCase,
    DeleteSavedPlaceUseCase,
    ListSavedPlacesUseCase,
    UpdateSavedPlaceCategoryUseCase,
)
from app.domain.entities.location import Location
from app.domain.value_objects.category import PlaceCategory
from app.domain.value_objects.coordinates import Coordinates
from app.infrastructure.database.sqlite_saved_places import SQLiteSavedPlaceRepository
from app.infrastructure.repositories.in_memory_saved_places import InMemorySavedPlaceRepository


def _location(name: str = "Аэропорт Домодедово") -> Location:
    return Location(
        id="osm:way:123",
        name=name,
        address="Московская область",
        coordinates=Coordinates(latitude=55.4087, longitude=37.9094),
        source="osm",
        source_id="way:123",
    )


def test_add_saved_place_persists_location_with_category() -> None:
    repository = InMemorySavedPlaceRepository()
    use_case = AddSavedPlaceUseCase(repository)

    saved = use_case.execute(user_id=42, location=_location(), category=PlaceCategory.FUEL)

    assert saved.id == 1
    assert saved.user_id == 42
    assert saved.name == "Аэропорт Домодедово"
    assert saved.category == PlaceCategory.FUEL
    assert repository.get(user_id=42, saved_place_id=1) == saved


def test_update_saved_place_category_changes_existing_place() -> None:
    repository = InMemorySavedPlaceRepository()
    saved = AddSavedPlaceUseCase(repository).execute(
        user_id=42,
        location=_location(),
        category=PlaceCategory.FUEL,
    )

    updated = UpdateSavedPlaceCategoryUseCase(repository).execute(
        user_id=42,
        saved_place_id=saved.id,
        category=PlaceCategory.HOTEL,
    )

    assert updated is not None
    assert updated.category == PlaceCategory.HOTEL


def test_delete_saved_place_removes_existing_place() -> None:
    repository = InMemorySavedPlaceRepository()
    saved = AddSavedPlaceUseCase(repository).execute(
        user_id=42,
        location=_location(),
        category=PlaceCategory.FUEL,
    )

    deleted = DeleteSavedPlaceUseCase(repository).execute(user_id=42, saved_place_id=saved.id)

    assert deleted is True
    assert repository.get(user_id=42, saved_place_id=saved.id) is None


def test_list_saved_places_returns_only_user_places_in_insert_order() -> None:
    repository = InMemorySavedPlaceRepository()
    AddSavedPlaceUseCase(repository).execute(
        user_id=42,
        location=_location("First"),
        category=PlaceCategory.FUEL,
    )
    AddSavedPlaceUseCase(repository).execute(
        user_id=7,
        location=_location("Other user"),
        category=PlaceCategory.HOTEL,
    )
    AddSavedPlaceUseCase(repository).execute(
        user_id=42,
        location=_location("Second"),
        category=PlaceCategory.RESTAURANT,
    )

    places = ListSavedPlacesUseCase(repository).execute(user_id=42)

    assert [place.name for place in places] == ["First", "Second"]


def test_sqlite_saved_places_are_persistent(tmp_path: Path) -> None:
    database_path = tmp_path / "places.sqlite3"
    first_repository = SQLiteSavedPlaceRepository(database_path)
    saved = AddSavedPlaceUseCase(first_repository).execute(
        user_id=42,
        location=_location(),
        category=PlaceCategory.RESTAURANT,
    )

    second_repository = SQLiteSavedPlaceRepository(database_path)
    loaded = second_repository.get(user_id=42, saved_place_id=saved.id)

    assert loaded is not None
    assert loaded.name == "Аэропорт Домодедово"
    assert loaded.category == PlaceCategory.RESTAURANT
    assert loaded.coordinates.latitude == 55.4087


def test_sqlite_lists_saved_places_for_one_user(tmp_path: Path) -> None:
    repository = SQLiteSavedPlaceRepository(tmp_path / "places.sqlite3")
    AddSavedPlaceUseCase(repository).execute(user_id=42, location=_location("First"), category=PlaceCategory.FUEL)
    AddSavedPlaceUseCase(repository).execute(user_id=7, location=_location("Other"), category=PlaceCategory.HOTEL)
    AddSavedPlaceUseCase(repository).execute(user_id=42, location=_location("Second"), category=PlaceCategory.CAFE)

    places = ListSavedPlacesUseCase(repository).execute(user_id=42)

    assert [place.name for place in places] == ["First", "Second"]
