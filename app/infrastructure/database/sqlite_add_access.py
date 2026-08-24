import sqlite3
from contextlib import closing
from pathlib import Path
from sqlite3 import Row

from app.domain.value_objects.add_access import AddAccessStatus


class SQLiteAddAccessRepository:
    """Admin-granted permission to add places, kept across restarts.

    A permission granted before a deploy must survive it: a driver who was
    approved yesterday and is refused today would reasonably conclude the
    admin changed their mind.
    """

    def __init__(self, database_path: Path | str) -> None:
        self._database_path = Path(database_path)
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def status(self, user_id: int) -> AddAccessStatus | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT status FROM add_access WHERE user_id = ?", (user_id,)
            ).fetchone()

        return None if row is None else AddAccessStatus(row["status"])

    def set_status(self, user_id: int, status: AddAccessStatus) -> None:
        with closing(self._connect()) as connection:
            connection.execute(
                """
                INSERT INTO add_access (user_id, status)
                VALUES (?, ?)
                ON CONFLICT(user_id) DO UPDATE SET status = excluded.status
                """,
                (user_id, status.value),
            )
            connection.commit()

    def clear(self, user_id: int) -> None:
        with closing(self._connect()) as connection:
            connection.execute("DELETE FROM add_access WHERE user_id = ?", (user_id,))
            connection.commit()

    def _initialize(self) -> None:
        with closing(self._connect()) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS add_access (
                    user_id INTEGER PRIMARY KEY,
                    status TEXT NOT NULL
                )
                """
            )
            connection.commit()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path)
        connection.row_factory = Row
        return connection
