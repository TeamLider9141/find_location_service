import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from sqlite3 import Row
from typing import Callable

from app.domain.value_objects.add_access import AddAccessStatus, has_gone_stale


class SQLiteAddAccessRepository:
    """Admin-granted permission to add places, kept across restarts.

    A permission granted before a deploy must survive it: a driver who was
    approved yesterday and is refused today would reasonably conclude the
    admin changed their mind. Each standing is stored with the moment it was
    written, which is what lets an unanswered request go quiet after a day.
    """

    def __init__(
        self, database_path: Path | str, clock: Callable[[], datetime] | None = None
    ) -> None:
        self._database_path = Path(database_path)
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        self._clock = clock if clock is not None else _now
        self._initialize()

    def status(self, user_id: int) -> AddAccessStatus | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT status, changed_at FROM add_access WHERE user_id = ?", (user_id,)
            ).fetchone()

        if row is None:
            return None

        # A request the admins let sit for a day reads as no request at all,
        # rather than leaving the driver waiting on an answer nobody will give.
        status = AddAccessStatus(row["status"])
        if has_gone_stale(status, _parse_timestamp(row["changed_at"]), self._clock()):
            return None

        return status

    def set_status(self, user_id: int, status: AddAccessStatus) -> None:
        with closing(self._connect()) as connection:
            connection.execute(
                """
                INSERT INTO add_access (user_id, status, changed_at)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    status = excluded.status,
                    changed_at = excluded.changed_at
                """,
                (user_id, status.value, self._clock().isoformat(sep=" ")),
            )
            connection.commit()

    def clear(self, user_id: int) -> None:
        with closing(self._connect()) as connection:
            connection.execute("DELETE FROM add_access WHERE user_id = ?", (user_id,))
            connection.commit()

    def statuses(self) -> dict[int, AddAccessStatus]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT user_id, status, changed_at FROM add_access"
            ).fetchall()

        now = self._clock()
        standings = (
            (int(row["user_id"]), AddAccessStatus(row["status"]), row["changed_at"])
            for row in rows
        )
        return {
            user_id: status
            for user_id, status, changed_at in standings
            if not has_gone_stale(status, _parse_timestamp(changed_at), now)
        }

    def _initialize(self) -> None:
        with closing(self._connect()) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS add_access (
                    user_id INTEGER PRIMARY KEY,
                    status TEXT NOT NULL,
                    changed_at TEXT
                )
                """
            )
            # Databases written before standings were timestamped: the column
            # is added and every row dated now, so a request left pending
            # across the deploy gets its full day rather than expiring at once.
            columns = {
                str(row["name"])
                for row in connection.execute("PRAGMA table_info(add_access)").fetchall()
            }
            if "changed_at" not in columns:
                connection.execute("ALTER TABLE add_access ADD COLUMN changed_at TEXT")
            connection.execute(
                "UPDATE add_access SET changed_at = ? WHERE changed_at IS NULL",
                (self._clock().isoformat(sep=" "),),
            )
            connection.commit()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path)
        connection.row_factory = Row
        return connection


def _now() -> datetime:
    """UTC, to the second — the clock every stored timestamp is read against."""
    return datetime.now(timezone.utc).replace(microsecond=0, tzinfo=None)


def _parse_timestamp(value: str | None) -> datetime:
    # An unreadable stamp dates the row to the beginning of time, which retires
    # a pending request rather than pinning a driver to a wait forever.
    if value is None:
        return datetime.min

    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return datetime.min
