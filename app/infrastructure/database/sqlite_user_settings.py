import sqlite3
from contextlib import closing
from pathlib import Path
from sqlite3 import Row

from app.domain.value_objects.user_settings import UserSettings


class SQLiteUserSettingsStore:
    """Per-driver search settings, kept across restarts."""

    def __init__(self, database_path: Path | str) -> None:
        self._database_path = Path(database_path)
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def get(self, user_id: int) -> UserSettings:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT nearby_radius_meters, result_limit FROM user_settings WHERE user_id = ?",
                (user_id,),
            ).fetchone()

        if row is None:
            return UserSettings()

        return UserSettings(
            nearby_radius_meters=int(row["nearby_radius_meters"]),
            result_limit=int(row["result_limit"]),
        )

    def increase_radius(self, user_id: int) -> UserSettings:
        return self._store(user_id, self.get(user_id).stepped_radius(1))

    def decrease_radius(self, user_id: int) -> UserSettings:
        return self._store(user_id, self.get(user_id).stepped_radius(-1))

    def increase_result_limit(self, user_id: int) -> UserSettings:
        return self._store(user_id, self.get(user_id).stepped_result_limit(1))

    def decrease_result_limit(self, user_id: int) -> UserSettings:
        return self._store(user_id, self.get(user_id).stepped_result_limit(-1))

    def _store(self, user_id: int, settings: UserSettings) -> UserSettings:
        with closing(self._connect()) as connection:
            connection.execute(
                """
                INSERT INTO user_settings (user_id, nearby_radius_meters, result_limit)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    nearby_radius_meters = excluded.nearby_radius_meters,
                    result_limit = excluded.result_limit
                """,
                (user_id, settings.nearby_radius_meters, settings.result_limit),
            )
            connection.commit()

        return settings

    def _initialize(self) -> None:
        with closing(self._connect()) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS user_settings (
                    user_id INTEGER PRIMARY KEY,
                    nearby_radius_meters INTEGER NOT NULL,
                    result_limit INTEGER NOT NULL
                )
                """
            )
            connection.commit()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path)
        connection.row_factory = Row
        return connection
