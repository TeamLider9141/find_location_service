import sqlite3
from dataclasses import replace
from pathlib import Path
from sqlite3 import Row

from app.domain.entities.saved_place import SavedPlace
from app.domain.value_objects.category import PlaceCategory
from app.domain.value_objects.coordinates import Coordinates


class SQLiteSavedPlaceRepository:
    def __init__(self, database_path: Path | str) -> None:
        self._database_path = Path(database_path)
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def add(self, saved_place: SavedPlace) -> SavedPlace:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO saved_places (
                    user_id, name, category, latitude, longitude,
                    address, source, source_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    saved_place.user_id,
                    saved_place.name,
                    saved_place.category.value,
                    saved_place.coordinates.latitude,
                    saved_place.coordinates.longitude,
                    saved_place.address,
                    saved_place.source,
                    saved_place.source_id,
                ),
            )
            connection.commit()
            return replace(saved_place, id=int(cursor.lastrowid))

    def get(self, user_id: int, saved_place_id: int) -> SavedPlace | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, user_id, name, category, latitude, longitude, address, source, source_id
                FROM saved_places
                WHERE id = ? AND user_id = ?
                """,
                (saved_place_id, user_id),
            ).fetchone()

        return _map_row(row) if row is not None else None

    def list_by_user(self, user_id: int) -> list[SavedPlace]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, user_id, name, category, latitude, longitude, address, source, source_id
                FROM saved_places
                WHERE user_id = ?
                ORDER BY id ASC
                """,
                (user_id,),
            ).fetchall()

        return [_map_row(row) for row in rows]

    def update_category(
        self,
        user_id: int,
        saved_place_id: int,
        category: PlaceCategory,
    ) -> SavedPlace | None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE saved_places
                SET category = ?
                WHERE id = ? AND user_id = ?
                """,
                (category.value, saved_place_id, user_id),
            )
            connection.commit()

        return self.get(user_id, saved_place_id)

    def delete(self, user_id: int, saved_place_id: int) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                DELETE FROM saved_places
                WHERE id = ? AND user_id = ?
                """,
                (saved_place_id, user_id),
            )
            connection.commit()
            return cursor.rowcount > 0

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS saved_places (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    category TEXT NOT NULL,
                    latitude REAL NOT NULL,
                    longitude REAL NOT NULL,
                    address TEXT NOT NULL,
                    source TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.commit()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path)
        connection.row_factory = Row
        return connection


def _map_row(row: Row) -> SavedPlace:
    return SavedPlace(
        id=int(row["id"]),
        user_id=int(row["user_id"]),
        name=str(row["name"]),
        category=PlaceCategory(str(row["category"])),
        coordinates=Coordinates(
            latitude=float(row["latitude"]),
            longitude=float(row["longitude"]),
        ),
        address=str(row["address"]),
        source=str(row["source"]),
        source_id=str(row["source_id"]),
    )
