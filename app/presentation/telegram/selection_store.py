from dataclasses import replace

from app.domain.value_objects.user_settings import (
    MAX_RADIUS_METERS,
    MAX_RESULT_LIMIT,
    MIN_RADIUS_METERS,
    MIN_RESULT_LIMIT,
    RADIUS_STEP_METERS,
    RESULT_LIMIT_STEP,
    UserSettings,
)


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
