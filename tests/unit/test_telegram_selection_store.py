from app.domain.entities.location import Location
from app.domain.value_objects.category import PlaceCategory
from app.domain.value_objects.coordinates import Coordinates
from app.presentation.telegram.selection_store import (
    InMemoryAddLocationFlowStore,
    InMemoryLocationSelectionStore,
    InMemoryUserSettingsStore,
)


def _location(name: str) -> Location:
    return Location(
        id=f"osm:node:{name}",
        name=name,
        address="Московская область",
        coordinates=Coordinates(latitude=55.4087, longitude=37.9094),
        source="osm",
        source_id=f"node:{name}",
    )


def test_selection_store_returns_user_location_by_index() -> None:
    store = InMemoryLocationSelectionStore()
    store.save(user_id=42, locations=[_location("first"), _location("second")])

    assert store.get(user_id=42, index=1).name == "second"


def test_selection_store_returns_none_for_missing_or_invalid_selection() -> None:
    store = InMemoryLocationSelectionStore()
    store.save(user_id=42, locations=[_location("first")])

    assert store.get(user_id=42, index=9) is None
    assert store.get(user_id=7, index=0) is None


def test_selection_store_can_clear_user_locations() -> None:
    store = InMemoryLocationSelectionStore()
    store.save(user_id=42, locations=[_location("first")])
    store.save(user_id=7, locations=[_location("other")])

    store.clear(user_id=42)

    assert store.get(user_id=42, index=0) is None
    assert store.get(user_id=7, index=0).name == "other"


def test_add_location_flow_store_tracks_search_and_add_modes() -> None:
    store = InMemoryAddLocationFlowStore()

    store.start_search(user_id=42)

    assert store.is_waiting(user_id=42) is True
    assert store.is_search_mode(user_id=42) is True
    assert store.is_add_mode(user_id=42) is False

    store.start(user_id=42)

    assert store.is_waiting(user_id=42) is True
    assert store.is_add_mode(user_id=42) is True
    assert store.is_search_mode(user_id=42) is False


def test_add_location_flow_store_tracks_realtime_nearby_category() -> None:
    store = InMemoryAddLocationFlowStore()

    store.start_realtime_nearby(user_id=42, category=PlaceCategory.FUEL)

    assert store.is_waiting(user_id=42) is True
    assert store.is_realtime_nearby_mode(user_id=42) is True
    assert store.get_realtime_nearby_category(user_id=42) == PlaceCategory.FUEL

    store.stop(user_id=42)

    assert store.is_realtime_nearby_mode(user_id=42) is False
    assert store.get_realtime_nearby_category(user_id=42) is None

    store.stop(user_id=42)

    assert store.is_waiting(user_id=42) is False
    assert store.is_add_mode(user_id=42) is False
    assert store.is_search_mode(user_id=42) is False


def test_user_settings_store_defaults_to_10_km_and_10_results() -> None:
    store = InMemoryUserSettingsStore()

    settings = store.get(user_id=42)

    assert settings.nearby_radius_meters == 10_000
    assert settings.result_limit == 10


def test_user_settings_store_changes_radius_and_result_limit() -> None:
    store = InMemoryUserSettingsStore()

    store.increase_radius(user_id=42)
    store.decrease_result_limit(user_id=42)

    settings = store.get(user_id=42)
    assert settings.nearby_radius_meters == 15_000
    assert settings.result_limit == 9
