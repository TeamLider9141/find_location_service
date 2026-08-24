from app.domain.value_objects.user_settings import UserSettings


class InMemoryUserSettingsStore:
    def __init__(self) -> None:
        self._settings_by_user_id: dict[int, UserSettings] = {}

    def get(self, user_id: int) -> UserSettings:
        return self._settings_by_user_id.get(user_id, UserSettings())

    def increase_radius(self, user_id: int) -> UserSettings:
        return self._store(user_id, self.get(user_id).stepped_radius(1))

    def decrease_radius(self, user_id: int) -> UserSettings:
        return self._store(user_id, self.get(user_id).stepped_radius(-1))

    def increase_result_limit(self, user_id: int) -> UserSettings:
        return self._store(user_id, self.get(user_id).stepped_result_limit(1))

    def decrease_result_limit(self, user_id: int) -> UserSettings:
        return self._store(user_id, self.get(user_id).stepped_result_limit(-1))

    def _store(self, user_id: int, settings: UserSettings) -> UserSettings:
        self._settings_by_user_id[user_id] = settings
        return settings
