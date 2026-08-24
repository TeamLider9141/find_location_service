import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
from sqlite3 import Row

from app.domain.entities.deletion_record import DeletionRecord
from app.domain.entities.place import Place
from app.domain.value_objects.category import PlaceCategory


class SQLiteDeletionLog:
    """Tombstones for deleted places, in the same file as everything else."""

    def __init__(self, database_path: Path | str) -> None:
        self._database_path = Path(database_path)
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def record(self, place: Place, deleted_by: int, source: str) -> None:
        with closing(self._connect()) as connection:
            connection.execute(
                """
                INSERT INTO deletion_log (
                    place_name, category, latitude, longitude, note,
                    added_by_user_id, deleted_by_user_id, source
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    place.name,
                    place.category.value,
                    place.coordinates.latitude,
                    place.coordinates.longitude,
                    place.note,
                    place.added_by_user_id,
                    deleted_by,
                    source,
                ),
            )
            connection.commit()

    def list_recent(self, limit: int = 30) -> list[DeletionRecord]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT id, place_name, category, latitude, longitude, note,
                       added_by_user_id, deleted_by_user_id, source, deleted_at
                FROM deletion_log
                ORDER BY id DESC
                LIMIT ?
                """,
                (max(limit, 0),),
            ).fetchall()

        return [_map_record(row) for row in rows]

    def _initialize(self) -> None:
        with closing(self._connect()) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS deletion_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    place_name TEXT NOT NULL,
                    category TEXT NOT NULL,
                    latitude REAL NOT NULL,
                    longitude REAL NOT NULL,
                    note TEXT NOT NULL,
                    added_by_user_id INTEGER NOT NULL,
                    deleted_by_user_id INTEGER NOT NULL,
                    source TEXT NOT NULL,
                    deleted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.commit()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path)
        connection.row_factory = Row
        return connection


def _map_record(row: Row) -> DeletionRecord:
    return DeletionRecord(
        id=int(row["id"]),
        place_name=str(row["place_name"]),
        category=PlaceCategory(str(row["category"])),
        latitude=float(row["latitude"]),
        longitude=float(row["longitude"]),
        note=str(row["note"]),
        added_by_user_id=int(row["added_by_user_id"]),
        deleted_by_user_id=int(row["deleted_by_user_id"]),
        source=str(row["source"]),
        deleted_at=datetime.fromisoformat(str(row["deleted_at"])),
    )
