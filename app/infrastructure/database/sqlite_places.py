import sqlite3
from datetime import datetime
from pathlib import Path
from sqlite3 import Row

from app.application.name_normalization import normalize_name
from app.domain.entities.community_place import Place
from app.domain.value_objects.category import PlaceCategory
from app.domain.value_objects.coordinates import Coordinates

_COLUMNS = """
    id, added_by_user_id, name, category, latitude, longitude, note, created_at
"""


class SQLitePlaceRepository:
    def __init__(self, database_path: Path | str) -> None:
        self._database_path = Path(database_path)
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def add(self, place: Place) -> Place:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO places (
                    added_by_user_id, name, name_normalized, category,
                    latitude, longitude, note
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    place.added_by_user_id,
                    place.name,
                    normalize_name(place.name),
                    place.category.value,
                    place.coordinates.latitude,
                    place.coordinates.longitude,
                    place.note,
                ),
            )
            connection.commit()
            place_id = int(cursor.lastrowid)

        stored = self.get(place_id)
        if stored is None:  # pragma: no cover - insert just succeeded
            raise RuntimeError("inserted place disappeared")
        return stored

    def get(self, place_id: int) -> Place | None:
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT {_COLUMNS} FROM places WHERE id = ?",
                (place_id,),
            ).fetchone()

        return _map_row(row) if row is not None else None

    def search(
        self,
        name: str | None = None,
        category: PlaceCategory | None = None,
        limit: int = 10,
    ) -> list[Place]:
        conditions: list[str] = []
        parameters: list[object] = []

        if category is not None:
            conditions.append("category = ?")
            parameters.append(category.value)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        parameters.append(limit)

        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT {_COLUMNS} FROM places {where} ORDER BY name ASC LIMIT ?",
                parameters,
            ).fetchall()

        return [_map_row(row) for row in rows]

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS places (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    added_by_user_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    name_normalized TEXT NOT NULL,
                    category TEXT NOT NULL,
                    latitude REAL NOT NULL,
                    longitude REAL NOT NULL,
                    note TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_places_category ON places(category)"
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_places_name_normalized
                ON places(name_normalized)
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_places_author ON places(added_by_user_id)"
            )
            connection.commit()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path)
        connection.row_factory = Row
        return connection


def _map_row(row: Row) -> Place:
    return Place(
        id=int(row["id"]),
        added_by_user_id=int(row["added_by_user_id"]),
        name=str(row["name"]),
        category=PlaceCategory(str(row["category"])),
        coordinates=Coordinates(
            latitude=float(row["latitude"]),
            longitude=float(row["longitude"]),
        ),
        note=str(row["note"]),
        created_at=_parse_timestamp(str(row["created_at"])),
    )


def _parse_timestamp(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return datetime.min
