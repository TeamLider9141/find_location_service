import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from math import asin, cos, degrees, radians, sin
from pathlib import Path
from sqlite3 import Row

from app.application.name_normalization import normalize_name
from app.domain.entities.place import Place
from app.domain.interfaces.places import DEFAULT_DUPLICATE_RADIUS_METERS
from app.domain.value_objects.category import (
    PlaceCategory,
    join_categories,
    split_categories,
)
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
        with closing(self._connect()) as connection:
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
                    join_categories(place.categories),
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
        with closing(self._connect()) as connection:
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
            conditions.append("(',' || category || ',') LIKE ?")
            parameters.append(f"%,{category.value},%")

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        parameters.append(limit)

        with closing(self._connect()) as connection:
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
            conditions.append("(',' || category || ',') LIKE ?")
            parameters.append(f"%,{category.value},%")

        with closing(self._connect()) as connection:
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

    def list_by_author(self, user_id: int) -> list[Place]:
        # Newest first by id, not created_at: CURRENT_TIMESTAMP has one-second
        # resolution, so places added together would tie and order arbitrarily.
        with closing(self._connect()) as connection:
            rows = connection.execute(
                f"""
                SELECT {_COLUMNS} FROM places
                WHERE added_by_user_id = ?
                ORDER BY id DESC
                """,
                (user_id,),
            ).fetchall()

        return [_map_row(row) for row in rows]

    def find_duplicates(
        self,
        name: str,
        coordinates: Coordinates,
        radius_meters: int = DEFAULT_DUPLICATE_RADIUS_METERS,
    ) -> list[Place]:
        normalized_name = normalize_name(name)
        if not normalized_name:
            return []

        candidates = self.nearby(coordinates, radius_meters, limit=_DUPLICATE_SCAN_LIMIT)
        return [
            place
            for place in candidates
            if (stored_name := normalize_name(place.name))
            and _names_overlap(normalized_name, stored_name)
        ]

    def update(
        self,
        place_id: int,
        user_id: int,
        name: str | None = None,
        category: PlaceCategory | None = None,
        note: str | None = None,
        coordinates: Coordinates | None = None,
    ) -> Place | None:
        assignments: list[str] = []
        parameters: list[object] = []

        if coordinates is not None:
            assignments.extend(["latitude = ?", "longitude = ?"])
            parameters.extend([coordinates.latitude, coordinates.longitude])

        if name is not None:
            assignments.extend(["name = ?", "name_normalized = ?"])
            parameters.extend([name, normalize_name(name)])

        if category is not None:
            assignments.append("category = ?")
            parameters.append(join_categories((category,)))

        if note is not None:
            assignments.append("note = ?")
            parameters.append(note)

        if not assignments:
            return self._get_owned(place_id, user_id)

        parameters.extend([place_id, user_id])
        # The author check rides in the WHERE clause, not a separate read then
        # write, so no concurrent request can slip between a check and a write.
        # delete() and _get_owned() do the same.
        with closing(self._connect()) as connection:
            cursor = connection.execute(
                f"""
                UPDATE places SET {', '.join(assignments)}
                WHERE id = ? AND added_by_user_id = ?
                """,
                parameters,
            )
            connection.commit()
            if cursor.rowcount == 0:
                return None

        return self.get(place_id)

    def delete(self, place_id: int, user_id: int) -> bool:
        with closing(self._connect()) as connection:
            cursor = connection.execute(
                "DELETE FROM places WHERE id = ? AND added_by_user_id = ?",
                (place_id, user_id),
            )
            connection.commit()
            return cursor.rowcount > 0

    def delete_any(self, place_id: int) -> bool:
        # No author in the WHERE clause: the admin panel is the only caller, and
        # a place nobody can reach the author of still has to be removable.
        with closing(self._connect()) as connection:
            cursor = connection.execute("DELETE FROM places WHERE id = ?", (place_id,))
            connection.commit()
            return cursor.rowcount > 0

    def count(self) -> int:
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT COUNT(*) AS total FROM places").fetchone()

        return int(row["total"])

    def count_added_since(self, days: int) -> int:
        # created_at is naive UTC written by CURRENT_TIMESTAMP, so the window is
        # measured with SQLite's own clock rather than Python's.
        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS total FROM places
                WHERE created_at >= datetime('now', ?)
                """,
                (f"-{max(days, 0)} days",),
            ).fetchone()

        return int(row["total"])

    def count_by_category(
        self, exclude_author_ids: tuple[int, ...] = ()
    ) -> dict[PlaceCategory, int]:
        # The column holds a comma list, so the splitting happens here rather
        # than in a GROUP BY — a multi-category place counts once per category.
        placeholders = ",".join("?" * len(exclude_author_ids))
        where = f"WHERE added_by_user_id NOT IN ({placeholders})" if exclude_author_ids else ""
        with closing(self._connect()) as connection:
            rows = connection.execute(
                f"SELECT category FROM places {where}",
                exclude_author_ids,
            ).fetchall()

        counts: dict[PlaceCategory, int] = {}
        for row in rows:
            for category in split_categories(str(row["category"])):
                counts[category] = counts.get(category, 0) + 1
        return counts

    def top_authors(self, limit: int = 10) -> list[tuple[int, int]]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT added_by_user_id, COUNT(*) AS total FROM places
                GROUP BY added_by_user_id
                ORDER BY total DESC, added_by_user_id ASC
                LIMIT ?
                """,
                (max(limit, 0),),
            ).fetchall()

        return [(int(row["added_by_user_id"]), int(row["total"])) for row in rows]

    def _get_owned(self, place_id: int, user_id: int) -> Place | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                f"""
                SELECT {_COLUMNS} FROM places
                WHERE id = ? AND added_by_user_id = ?
                """,
                (place_id, user_id),
            ).fetchone()

        return _map_row(row) if row is not None else None

    def _initialize(self) -> None:
        with closing(self._connect()) as connection:
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

    # closing(), not the connection's own context manager: that one commits or
    # rolls back a transaction and leaves the connection open. Every write below
    # commits explicitly, so what is left to manage is the handle itself.
    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path)
        connection.row_factory = Row
        return connection


def _escape_like(value: str) -> str:
    """Neutralize LIKE wildcards so a name containing % or _ still matches literally."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# Only the 50 nearest candidates get name-checked. nearby() sorts by distance
# first, so anything dropped is farther away than 50 other places inside the
# radius — a real duplicate is almost never that far down the list.
_DUPLICATE_SCAN_LIMIT = 50


def _names_overlap(left: str, right: str) -> bool:
    return left in right or right in left


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
        categories=split_categories(str(row["category"])),
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
