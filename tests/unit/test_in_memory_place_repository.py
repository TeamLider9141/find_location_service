from datetime import datetime

from app.domain.entities.community_place import Place
from app.domain.value_objects.category import PlaceCategory
from app.domain.value_objects.coordinates import Coordinates
from app.infrastructure.repositories.in_memory_places import InMemoryPlaceRepository


def make_place(
    name: str = "Газпром",
    category: PlaceCategory = PlaceCategory.FUEL,
    latitude: float = 55.75,
    longitude: float = 37.61,
    user_id: int = 42,
    note: str = "",
) -> Place:
    return Place(
        id=0,
        added_by_user_id=user_id,
        name=name,
        category=category,
        coordinates=Coordinates(latitude=latitude, longitude=longitude),
        note=note,
        created_at=datetime(2026, 1, 1),
    )


def test_add_assigns_incrementing_ids() -> None:
    repository = InMemoryPlaceRepository()

    first = repository.add(make_place(name="Первое"))
    second = repository.add(make_place(name="Второе"))

    assert (first.id, second.id) == (1, 2)


def test_search_matches_normalized_name() -> None:
    repository = InMemoryPlaceRepository()
    repository.add(make_place(name="Газпром"))

    assert [place.name for place in repository.search(name="gazprom")] == ["Газпром"]


def test_nearby_sorts_by_distance_and_drops_far_places() -> None:
    repository = InMemoryPlaceRepository()
    repository.add(make_place(name="Дальше", latitude=55.7700))
    repository.add(make_place(name="Ближе", latitude=55.7510))
    repository.add(make_place(name="Слишком далеко", latitude=56.5000))

    results = repository.nearby(
        Coordinates(latitude=55.7500, longitude=37.6100),
        radius_meters=5_000,
    )

    assert [place.name for place in results] == ["Ближе", "Дальше"]


def test_delete_by_another_user_returns_false() -> None:
    repository = InMemoryPlaceRepository()
    stored = repository.add(make_place(user_id=42))

    assert repository.delete(stored.id, user_id=7) is False
    assert repository.get(stored.id) is not None


def test_find_duplicates_matches_overlapping_names_in_radius() -> None:
    repository = InMemoryPlaceRepository()
    repository.add(make_place(name="Газпром", latitude=55.7500, longitude=37.6100))

    duplicates = repository.find_duplicates(
        name="Газпром 24",
        coordinates=Coordinates(latitude=55.7500, longitude=37.6100),
        radius_meters=200,
    )

    assert [place.name for place in duplicates] == ["Газпром"]
