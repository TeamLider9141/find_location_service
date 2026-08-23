from dataclasses import replace

from app.domain.entities.location import Location
from app.domain.value_objects.category import PlaceCategory
from app.domain.value_objects.user_settings import (
    MAX_RADIUS_METERS,
    MAX_RESULT_LIMIT,
    MIN_RADIUS_METERS,
    MIN_RESULT_LIMIT,
    RADIUS_STEP_METERS,
    RESULT_LIMIT_STEP,
    UserSettings,
)


class InMemoryLocationSelectionStore:
    def __init__(self) -> None:
        self._locations_by_user_id: dict[int, list[Location]] = {}

    def save(self, user_id: int, locations: list[Location]) -> None:
        self._locations_by_user_id[user_id] = list(locations)

    def get(self, user_id: int, index: int) -> Location | None:
        locations = self._locations_by_user_id.get(user_id)
        if locations is None or index < 0 or index >= len(locations):
            return None
        return locations[index]

    def clear(self, user_id: int) -> None:
        self._locations_by_user_id.pop(user_id, None)


class InMemoryAddLocationFlowStore:
    def __init__(self) -> None:
        self._modes_by_user_id: dict[int, str] = {}

    def start(self, user_id: int) -> None:
        self.start_add(user_id)

    def start_add(self, user_id: int) -> None:
        self._modes_by_user_id[user_id] = "add"

    def start_search(self, user_id: int) -> None:
        self._modes_by_user_id[user_id] = "search"

    def start_realtime_nearby(self, user_id: int, category: PlaceCategory) -> None:
        self._modes_by_user_id[user_id] = f"nearby:{category.value}"

    def stop(self, user_id: int) -> None:
        self._modes_by_user_id.pop(user_id, None)

    def is_waiting(self, user_id: int) -> bool:
        return user_id in self._modes_by_user_id

    def is_add_mode(self, user_id: int) -> bool:
        return self._modes_by_user_id.get(user_id) == "add"

    def is_search_mode(self, user_id: int) -> bool:
        return self._modes_by_user_id.get(user_id) == "search"

    def is_realtime_nearby_mode(self, user_id: int) -> bool:
        mode = self._modes_by_user_id.get(user_id)
        return mode is not None and mode.startswith("nearby:")

    def get_realtime_nearby_category(self, user_id: int) -> PlaceCategory | None:
        mode = self._modes_by_user_id.get(user_id)
        if mode is None or not mode.startswith("nearby:"):
            return None

        try:
            return PlaceCategory(mode.removeprefix("nearby:"))
        except ValueError:
            return None


class InMemoryUserSettingsStore:
    def __init__(self) -> None:
        self._settings_by_user_id: dict[int, UserSettings] = {}

    def get(self, user_id: int) -> UserSettings:
        return self._settings_by_user_id.get(user_id, UserSettings())

    def increase_radius(self, user_id: int) -> UserSettings:
        return self._change_radius(user_id, RADIUS_STEP_METERS)

    def decrease_radius(self, user_id: int) -> UserSettings:
        return self._change_radius(user_id, -RADIUS_STEP_METERS)

    def increase_result_limit(self, user_id: int) -> UserSettings:
        return self._change_result_limit(user_id, RESULT_LIMIT_STEP)

    def decrease_result_limit(self, user_id: int) -> UserSettings:
        return self._change_result_limit(user_id, -RESULT_LIMIT_STEP)

    def _change_radius(self, user_id: int, delta: int) -> UserSettings:
        current = self.get(user_id)
        radius = _clamp(
            current.nearby_radius_meters + delta,
            MIN_RADIUS_METERS,
            MAX_RADIUS_METERS,
        )
        return self._store(user_id, replace(current, nearby_radius_meters=radius))

    def _change_result_limit(self, user_id: int, delta: int) -> UserSettings:
        current = self.get(user_id)
        limit = _clamp(current.result_limit + delta, MIN_RESULT_LIMIT, MAX_RESULT_LIMIT)
        return self._store(user_id, replace(current, result_limit=limit))

    def _store(self, user_id: int, settings: UserSettings) -> UserSettings:
        self._settings_by_user_id[user_id] = settings
        return settings


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))
