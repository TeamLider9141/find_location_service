import sqlite3
from dataclasses import dataclass
from datetime import datetime
from math import asin, cos, degrees, radians, sin
from pathlib import Path
from sqlite3 import Row

from app.application.name_normalization import normalize_name
from app.domain.entities.community_place import Place
from app.domain.value_objects.category import PlaceCategory
from app.domain.value_objects.coordinates import Coordinates

_COLUMNS = """
    id, added_by_user_id, name, category, latitude, longitude, note, created_at
"""

_EARTH_RADIUS_METERS = 6_371_000
_BOX_MARGIN = 1.001


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

        normalized_name = normalize_name(name) if name is not None else ""
        if normalized_name:
            conditions.append("name_normalized LIKE ? ESCAPE '\\'")
            parameters.append(f"%{_escape_like(normalized_name)}%")

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

    def nearby(
        self,
        coordinates: Coordinates,
        radius_meters: int,
        category: PlaceCategory | None = None,
        limit: int = 10,
    ) -> list[Place]:
        box = _bounding_box(coordinates, radius_meters)
        conditions = [
            "latitude BETWEEN ? AND ?",
            "longitude BETWEEN ? AND ?",
        ]
        parameters: list[object] = [
            box.min_latitude,
            box.max_latitude,
            box.min_longitude,
            box.max_longitude,
        ]

        if category is not None:
            conditions.append("category = ?")
            parameters.append(category.value)

        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT {_COLUMNS} FROM places WHERE {' AND '.join(conditions)}",
                parameters,
            ).fetchall()

        within_radius = [
            (coordinates.distance_to(place.coordinates), place)
            for place in (_map_row(row) for row in rows)
        ]
        within_radius = [item for item in within_radius if item[0] <= radius_meters]
        within_radius.sort(key=lambda item: item[0])
        return [place for _, place in within_radius[: max(limit, 0)]]

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


def _escape_like(value: str) -> str:
    """Neutralize LIKE wildcards so a name containing % or _ still matches literally."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@dataclass(frozen=True)
class _BoundingBox:
    min_latitude: float
    max_latitude: float
    min_longitude: float
    max_longitude: float


def _bounding_box(coordinates: Coordinates, radius_meters: int) -> _BoundingBox:
    """A rectangle that contains the radius circle, with a small safety margin.

    This is a cheap prefilter — the exact Haversine check runs in Python
    afterwards — so the box may be too large but must never be too small.
    That is why it measures on the same sphere as ``Coordinates.distance_to``:
    a flat metres-per-degree constant comes out slightly narrower than Haversine
    measures and silently drops places that are genuinely inside the radius.

    The box does not wrap the antimeridian; a search centred near +/-180
    longitude is clipped rather than continued on the other side. That costs
    nothing for the drivers this bot serves.
    """
    angular_radius = radius_meters * _BOX_MARGIN / _EARTH_RADIUS_METERS
    latitude_delta = degrees(angular_radius)

    # Longitude degrees shrink towards the poles, so the same distance spans
    # more of them the further north you are. Close enough to a pole the circle
    # covers every longitude, which is what a sine of 1 or more means.
    longitude_sine = sin(angular_radius) / max(cos(radians(coordinates.latitude)), 1e-9)
    longitude_delta = (
        180.0 if longitude_sine >= 1 else degrees(asin(longitude_sine))
    )

    return _BoundingBox(
        min_latitude=max(coordinates.latitude - latitude_delta, -90.0),
        max_latitude=min(coordinates.latitude + latitude_delta, 90.0),
        min_longitude=max(coordinates.longitude - longitude_delta, -180.0),
        max_longitude=min(coordinates.longitude + longitude_delta, 180.0),
    )


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
